"""Lecturas de sesión de Equity compartidas por pantalla e historial."""
import numpy as np
import pandas as pd

from src.data.four_hour import prepare_stored
from src.indices_math import prepare_bars, aggregate_regular_hours, relative_performance


def session_for(pilot, symbol):
    """Sesión configurada por activo; None conserva el horario de Nueva York."""
    sessions = (pilot or {}).get("sessions") or {}
    if not sessions:
        return None
    return sessions.get((pilot.get("asset_session") or {}).get(symbol, "default"))


def session_label(pilot, symbol):
    spec = session_for(pilot, symbol)
    return spec.get("label") if spec else "NYSE 09:30–16:00 Nueva York"


def regular_stock_bars(raw, symbol, tf, now, session=None):
    if session is None:
        if tf == "4h":
            bars = prepare_stored(raw, symbol, now, "NYSE")
            # La vista principal no acepta la 4h vieja ni premercado como sesión.
            if len(bars):
                local = bars.timestamp.dt.tz_convert("America/New_York")
                times = local.dt.strftime("%H:%M")
                bars = bars[bars.source.eq("session_4h_us") & times.isin(["09:30", "13:30"])]
            return bars.reset_index(drop=True)
        base = "5m" if tf == "1h" else tf
        bars = prepare_bars(raw, symbol, base, "NYSE", now, regular=True)
        return aggregate_regular_hours(bars, now) if tf == "1h" else bars
    from src.argentina_math import session_four_hour
    if tf == "4h":
        # La 4h de sesión se arma desde las velas horarias de la propia
        # sesión (dos años de historia); nunca se usa la del proveedor,
        # que no respeta la apertura ni el cierre del mercado.
        return session_four_hour(prepare_bars(raw, symbol, "1h", session["calendar"], now), session, now)
    base = "5m" if tf == "1h" else tf
    bars = prepare_bars(raw, symbol, base, session["calendar"], now)
    return aggregate_regular_hours(bars, now, session["calendar"]) if tf == "1h" else bars


def equity_indicators(rows, daily, frames, benchmark, pilot):
    sectors, megas = pilot["sectors"], pilot["mega_caps"]
    sector_series = {s: daily[s].set_index("session").close for s in sectors}
    common = pd.concat([v.rename(s) for s, v in sector_series.items()] + [benchmark.rename("benchmark")],
                       axis=1, join="inner").replace([np.inf, -np.inf], np.nan).dropna().sort_index()
    common = common[(common > 0).all(axis=1)]
    performance = relative_performance({s: common[s] for s in sectors}, common["benchmark"], pilot["relative_strength_sessions"])
    valid = performance.dropna(subset=["relative_pp"]).sort_values("relative_pp", ascending=False)
    start = str(common.index[-pilot["relative_strength_sessions"]-1]) if len(common) > pilot["relative_strength_sessions"] else None
    directions = {r["symbol"]: r["direction"] for r in rows}
    distance_rows = [r for r in rows if r["distance_std"] is not None]
    stretched = max(distance_rows, key=lambda r: abs(r["distance_std"]), default=None)
    kpis = {"sector_up": sum(directions[s].startswith("alcista") for s in sectors),
            "sector_down": sum(directions[s].startswith("bajista") for s in sectors), "sector_total": len(sectors),
            "mega_up": sum(directions[s].startswith("alcista") for s in megas),
            "mega_down": sum(directions[s].startswith("bajista") for s in megas), "mega_total": len(megas),
            "leader": valid.iloc[0].to_dict() if len(valid) else None,
            "laggard": valid.iloc[-1].to_dict() if len(valid) else None,
            "start_session": start, "last_session": str(common.index[-1]) if len(common) else None,
            "stretched": stretched}
    heat = []
    for symbol in sectors:
        row = {"symbol": symbol}
        for tf in ["1m", "5m", "15m", "1h", "4h", "1D"]:
            closed = frames[(symbol, tf)]
            closed = closed[closed.closed]
            ema = closed.close.ewm(span=50, adjust=False, min_periods=50).mean()
            row[tf] = float((closed.close.iloc[-1] / ema.iloc[-1] - 1) * 100) if len(closed) and pd.notna(ema.iloc[-1]) else None
        heat.append(row)
    heatmap = pd.DataFrame(heat).sort_values("1D", ascending=False, na_position="last")
    return {"kpis": kpis, "sector_performance": performance, "heatmap": heatmap}
