"""Argentina: CCL implícito por empresa, dispersión y sesiones BYMA/NY.

El CCL implícito usa la equivalencia configurada: precio local × acciones por
ADR, dividido por el precio del ADR. En diario se usan cierres de la misma
sesión; en intradía solo velas de 15m dentro de la ventana común BYMA–NYSE,
calculada con zonas horarias reales.
"""
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

BA = ZoneInfo("America/Argentina/Buenos_Aires")
NY = ZoneInfo("America/New_York")


def _minutes(clock):
    hour, minute = str(clock).split(":")
    return int(hour) * 60 + int(minute)


def session_window(now, session):
    """Apertura y cierre de la sesión en UTC, con horario de verano real."""
    now = pd.to_datetime(now, utc=True)
    day = now.tz_convert(ZoneInfo(session["timezone"])).date()
    opening = pd.Timestamp(f"{day} {session['open']}", tz=ZoneInfo(session["timezone"])).tz_convert("UTC")
    closing = pd.Timestamp(f"{day} {session['close']}", tz=ZoneInfo(session["timezone"])).tz_convert("UTC")
    return opening, closing


def common_window(now, byma, nyse):
    """Solape real BYMA–NYSE. El cambio de hora de EE.UU. lo ajusta solo."""
    byma_open, byma_close = session_window(now, byma)
    nyse_open, nyse_close = session_window(now, nyse)
    start, end = max(byma_open, nyse_open), min(byma_close, nyse_close)
    return (start, end) if end > start else (None, None)


def latest_window(now, byma, nyse, days_back=10):
    """Ventana común del día más reciente; se retrocede hasta un día con datos."""
    for offset in range(days_back + 1):
        day = pd.to_datetime(now, utc=True) - pd.Timedelta(days=offset)
        start, end = common_window(day, byma, nyse)
        if start is not None:
            return start, end
    return None, None


def session_four_hour(bars, session, now=None):
    """Velas de cuatro horas dentro de la sesión, agregadas desde la escala menor."""
    if bars.empty:
        return bars
    tz = ZoneInfo(session["timezone"])
    local = bars.timestamp.dt.tz_convert(tz)
    minute_of_day = local.dt.hour * 60 + local.dt.minute
    segments = [(_minutes(part.split("-")[0]), _minutes(part.split("-")[1])) for part in session["four_hour"]]
    slot = pd.Series(-1, index=bars.index, dtype=int)
    for index, (opening, closing) in enumerate(segments):
        slot[(minute_of_day >= opening) & (minute_of_day < closing)] = index
    keep = slot >= 0
    if not keep.any():
        return bars.iloc[:0].copy()
    frame = bars[keep].assign(slot=slot[keep])
    frame["bucket"] = frame.session + "|" + frame.slot.astype(str)
    grouped = frame.groupby("bucket", sort=True).agg(open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"), volume=("volume", "sum"),
        session=("session", "last"), slot=("slot", "last"), closed=("closed", "all"))
    def edges(bucket):
        day, number = bucket.split("|")
        opening, closing = segments[int(number)]
        zone = ZoneInfo(session["timezone"])
        return (pd.Timestamp(f"{day} {opening // 60:02d}:{opening % 60:02d}", tz=zone).tz_convert("UTC"),
                pd.Timestamp(f"{day} {closing // 60:02d}:{closing % 60:02d}", tz=zone).tz_convert("UTC"))
    grouped["timestamp"] = [edges(bucket)[0] for bucket in grouped.index]
    grouped["bar_end"] = [edges(bucket)[1] for bucket in grouped.index]
    result = grouped.reset_index(drop=True).sort_values("timestamp").reset_index(drop=True)
    limit = pd.Timestamp.now(tz="UTC") if now is None else pd.to_datetime(now, utc=True)
    result["closed"] = result.closed & (result.bar_end <= limit)
    return result


def ccl_series(local, adr, ratio, key="session"):
    """CCL implícito sobre cierres de la MISMA clave: sesión diaria o marca de tiempo."""
    a = local.set_index(key).close.astype(float)
    b = adr.set_index(key).close.astype(float)
    idx = a.index.intersection(b.index)
    values = (a.loc[idx] * ratio / b.loc[idx])
    return values[values > 0].sort_index()


def median_reading(history, window=50, change_sessions=5):
    """Mediana, cambio en cinco ruedas y separación por desvío muestral."""
    if history.empty:
        return {"median": None, "change_5": None, "distance_std": None, "last_session": None, "sessions": 0}
    last = float(history.iloc[-1])
    mean = float(history.tail(window).mean())
    deviation = float(history.tail(window).std(ddof=1))
    change = None
    if len(history) > change_sessions:
        previous = float(history.iloc[-change_sessions - 1])
        change = (last / previous - 1) * 100 if previous else None
    return {"median": last, "change_5": change,
            "distance_std": (last - mean) / deviation if deviation else None,
            "last_session": str(history.index[-1]), "sessions": len(history)}


def dispersion(companies, threshold_pct, symbols=None, yellow_pct=None):
    """Desvío de cada empresa contra la mediana de ese mismo día.

    Dos niveles de aviso configurables: amarillo (primer nivel) y naranja
    (segundo nivel, igual al umbral anterior). Guardan la clave anterior.
    """
    amber = float(yellow_pct) if yellow_pct is not None else float(threshold_pct)
    if companies.empty:
        return []
    median = companies.median(axis=1)
    rows = []
    for name in companies.columns:
        history = companies[name].dropna()
        local = (symbols or {}).get(name)
        if history.empty:
            rows.append({"company": name, "local": local, "ccl": None, "vs_median_pct": None,
                         "highlight": False, "alert": None})
            continue
        value = float(history.iloc[-1])
        reference = float(median.loc[history.index[-1]])
        difference = (value / reference - 1) * 100 if reference else None
        away = difference is not None and abs(difference) > threshold_pct
        soft = difference is not None and abs(difference) > amber if difference is not None else False
        rows.append({"company": name, "local": local, "ccl": value, "vs_median_pct": difference,
                     "highlight": bool(away), "alert": "naranja" if away else ("amarillo" if soft else None)})
    return rows


def dispersion_reference(companies, window=126, threshold=2.0, yellow=None):
    """Dispersión real reciente: sirve para calibrar el umbral, no para ocultarlo."""
    if companies.empty:
        return {"sessions": 0}
    median = companies.median(axis=1)
    deviation = (companies.div(median, axis=0) - 1).mul(100).abs().stack()
    deviation = deviation[np.isfinite(deviation)].dropna().tail(window)
    if deviation.empty:
        return {"sessions": 0}
    counts = {"above_threshold": int((deviation > threshold).sum()),
              "above_threshold_share": float((deviation > threshold).mean() * 100)}
    if yellow is not None:
        counts.update({"above_yellow": int((deviation > yellow).sum()),
                       "above_yellow_share": float((deviation > yellow).mean() * 100)})
    return {"sessions": int(len(deviation)), "median": float(deviation.median()),
            "p90": float(deviation.quantile(0.9)), "p95": float(deviation.quantile(0.95)),
            "p99": float(deviation.quantile(0.99)), "max": float(deviation.max()), **counts}


def argentina_indicators(frames, rows, pilot, pares, equivalencias, now, intraday_minutes=15):
    """CCL diario e intradía, dispersión, conteo local y mayor separación."""
    local_assets = pilot["local_assets"]
    daily, intraday, window = {}, {}, (None, None)
    for pair in pares:
        ratio = equivalencias.get(pair["adr"])
        if not ratio:
            continue
        local_bars = frames.get((pair["local"], "1D"))
        adr_bars = frames.get((pair["adr"], "1D"))
        if local_bars is None or adr_bars is None:
            continue
        daily[pair["nombre"]] = ccl_series(local_bars, adr_bars, ratio)
        base = f"{intraday_minutes}m"
        local_intra = frames.get((pair["local"], base))
        adr_intra = frames.get((pair["adr"], base))
        if local_intra is None or adr_intra is None:
            continue
        for offset in range(11):
            day = pd.to_datetime(now, utc=True) - pd.Timedelta(days=offset)
            start, end = common_window(day, pilot["sessions"]["byma"], pilot["sessions"]["nyse"])
            if start is None:
                continue
            usable_local = local_intra[(local_intra.bar_end > start) & (local_intra.bar_end <= end)]
            usable_adr = adr_intra[(adr_intra.bar_end > start) & (adr_intra.bar_end <= end)]
            if usable_local.empty or usable_adr.empty:
                continue
            series = ccl_series(usable_local, usable_adr, ratio, key="bar_end")
            series = series[series.index <= end]
            if len(series):
                intraday[pair["nombre"]] = series
                window = (start, end)
                break
    companies = pd.DataFrame(daily).sort_index()
    companies = companies.dropna(how="all")
    threshold = pilot.get("dispersion_threshold_pct", 5.0)
    yellow = pilot.get("dispersion_yellow_pct", max(threshold / 2.0, 0.5))
    local_rows = [row for row in rows if row["symbol"] in local_assets]
    stretched_rows = [row for row in local_rows if row["distance_std"] is not None]
    return {
        "ccl_by_company": dispersion(companies, threshold, {pair["nombre"]: pair["local"] for pair in pares}, yellow),
        "dispersion_reference": dispersion_reference(companies, pilot.get("dispersion_window", 126), threshold, yellow),
        "dispersion_window": pilot.get("dispersion_window", 126),
        "dispersion_yellow_pct": yellow,
        "median": median_reading(companies.median(axis=1).dropna(),
                                 pilot.get("ccl_window", 50), pilot.get("ccl_change_sessions", 5)),
        "dispersion_threshold_pct": threshold,
        "ccl_sessions": int(len(companies)),
        "ccl_change_sessions": pilot.get("ccl_change_sessions", 5),
        "ccl_window": pilot.get("ccl_window", 50),
        "local_up": sum(row["direction"].startswith("alcista") for row in local_rows),
        "local_down": sum(row["direction"].startswith("bajista") for row in local_rows),
        "local_total": len(local_rows),
        "stretched": max(stretched_rows, key=lambda row: abs(row["distance_std"]), default=None),
        "intraday_window": {"start": window[0].isoformat() if window[0] is not None else None,
                            "end": window[1].isoformat() if window[1] is not None else None,
                            "timeframe": f"{intraday_minutes}m"},
        "intraday_ccl": {name: {"last": float(series.iloc[-1]), "timestamp": series.index[-1].isoformat(),
                                "bars": int(len(series))} for name, series in intraday.items()},
        "intraday_median": median_reading(pd.DataFrame(intraday).median(axis=1).dropna(),
                                          pilot.get("ccl_window", 50), pilot.get("ccl_change_sessions", 5))
                          if intraday else {"median": None, "change_5": None, "distance_std": None,
                                            "last_session": None, "sessions": 0},
    }