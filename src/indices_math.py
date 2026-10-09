"""C2: cálculos independientes del piloto. No modifica los motores anteriores."""
from functools import lru_cache
import warnings
import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
import statsmodels.api as sm
from statsmodels.tsa.stattools import coint
from statsmodels.tsa.vector_ar.vecm import coint_johansen

SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
ALIGNMENT_LEGEND = "Alineación significa que varias escalas coinciden en dirección. No es una orden de compra o venta."


def utc_now(now=None):
    return pd.Timestamp.now(tz="UTC") if now is None else pd.to_datetime(now, utc=True)


@lru_cache(maxsize=256)
def schedule(name, start, end):
    return mcal.get_calendar(name).schedule(start_date=start, end_date=end)


def trading_segments(name, start, end, regular=False):
    sch = schedule("NYSE" if regular else name, str(start)[:10], str(end)[:10])
    segments = []
    for day, row in sch.iterrows():
        opening, closing = row.market_open, row.market_close
        b0, b1 = row.get("break_start"), row.get("break_end")
        if pd.notna(b0) and pd.notna(b1) and b1 > b0:
            segments += [(opening, b0, str(day.date())), (b1, closing, str(day.date()))]
        else:
            segments.append((opening, closing, str(day.date())))
    return segments


def daily_timezone(symbol, calendar_name):
    return "America/New_York" if symbol.endswith("=F") else str(mcal.get_calendar(calendar_name).tz)


def prepare_bars(df, symbol, tf, calendar_name, now=None, regular=False):
    """Ruedas reales, fin de bloques parciales, y última recepción provisional."""
    now = utc_now(now)
    if df.empty:
        return df.assign(session=pd.Series(dtype=str), bar_end=pd.Series(dtype="datetime64[ns, UTC]"), closed=pd.Series(dtype=bool))
    out = df.copy().sort_values("timestamp").drop_duplicates("timestamp")
    out["timestamp"] = pd.to_datetime(out.timestamp, utc=True)
    if tf == "1D":
        days = out.timestamp.dt.tz_convert(daily_timezone(symbol, calendar_name)).dt.date
        days = pd.Series(days.to_numpy(), index=out.index)
        if symbol.endswith("=F"):
            days = days.map(lambda d: d + pd.Timedelta(days=1) if d.weekday() == 6 else d)
        sch = schedule(calendar_name, str(min(days)), str(max(days)))
        closes = {d.date(): row.market_close for d, row in sch.iterrows()}
        out["session"] = days.astype(str)
        out["bar_end"] = pd.to_datetime(days.map(closes), utc=True)
        out = out.dropna(subset=["bar_end", "close"])
    else:
        start = out.timestamp.min() - pd.Timedelta(days=3)
        end = out.timestamp.max() + pd.Timedelta(days=3)
        segments = trading_segments(calendar_name, start, end, regular)
        if not segments:
            return out.iloc[:0].assign(session="", bar_end=now, closed=False)
        intervals = pd.IntervalIndex.from_tuples([(a, b) for a, b, _ in segments], closed="left")
        pos = intervals.get_indexer(out.timestamp)
        out = out.loc[pos >= 0].copy()
        pos = pos[pos >= 0]
        out["session"] = [segments[p][2] for p in pos]
        limit = pd.Series([segments[p][1] for p in pos], index=out.index)
        proposed = out.timestamp + pd.Timedelta(seconds=SECONDS[tf])
        out["bar_end"] = proposed.where(proposed <= limit, limit)
    out["closed"] = out.bar_end <= now
    out["receipt_verified"] = False
    if "updated_at" in out:
        verified = out.updated_at.astype(str).str.contains("T", regex=False)
        received = pd.to_datetime(out.updated_at, utc=True, errors="coerce", format="mixed")
        out["receipt_verified"] = verified
        # Una vela que se recibió abierta no se da por final solo porque pasó el reloj.
        out.loc[verified & (received < out.bar_end), "closed"] = False
    return out.reset_index(drop=True)


def market_minutes_between(start, end, calendar_name):
    start, end = pd.to_datetime(start, utc=True), pd.to_datetime(end, utc=True)
    if end <= start:
        return 0.0
    total = 0.0
    for a, b, _ in trading_segments(calendar_name, start, end):
        left, right = max(a, start), min(b, end)
        if right > left:
            total += (right - left).total_seconds() / 60
    return total


def freshness(bars, tf, calendar_name, now=None):
    now = utc_now(now)
    closed = bars[bars.closed] if "closed" in bars else bars.iloc[:0]
    if closed.empty:
        return {"stale": True, "label": "Sin cierre comprobable", "market_minutes": None}
    last = closed.iloc[-1]
    if tf == "1D":
        sch = schedule(calendar_name, str((now - pd.Timedelta(days=20)).date()), str(now.date()))
        completed = sch[sch.market_close <= now]
        expected = str(completed.index[-1].date()) if len(completed) else last.session
        missing = int(((sch.index.astype(str).str[:10] > last.session) & (sch.market_close <= now)).sum())
        return {"stale": last.session < expected, "label": f"⚠ Faltan {missing} ruedas" if last.session < expected else "Última rueda disponible",
                "market_minutes": None, "last_data": last.bar_end, "session": last.session}
    minutes = market_minutes_between(last.bar_end, now, calendar_name)
    threshold = max(20, 2 * SECONDS[tf] / 60)
    age = max(0, (now - last.bar_end).total_seconds() / 60)
    human = f"{int(age)} min" if age < 60 else f"{int(age / 60)} h" if age < 2880 else f"{int(age / 1440)} días"
    return {"stale": minutes > threshold, "label": ("⚠ " if minutes > threshold else "") + f"hace {human}",
            "market_minutes": minutes, "last_data": last.bar_end, "session": last.session}


def alignment(directions):
    """No cuenta ausentes/atrasados. Distingue débiles de confirmados."""
    valid = {tf: d for tf, d in directions.items() if d in {"alcista", "bajista", "alcista (débil)", "bajista (débil)", "lateral"}}
    up = sum(d.startswith("alcista") for d in valid.values())
    down = sum(d.startswith("bajista") for d in valid.values())
    weak = sum("débil" in d for d in valid.values())
    count, missing = len(valid), 6 - len(valid)
    if not count:
        label = "Sin escalas disponibles"
    elif up == down:
        label = f"Mixta: {up} ↑ / {down} ↓ de {count}"
    else:
        best, arrow = (up, "↑") if up > down else (down, "↓")
        label = f"{best} de {count} disponibles {arrow}"
    if missing:
        label += f"; falta{'n' if missing != 1 else ''} {missing}"
    if weak:
        label += f" ({weak} débiles)"
    groups = {}
    for name, tfs in [("Corto plazo", ["1m", "5m", "15m"]), ("Intradía", ["1h", "4h"]), ("Diario", ["1D"])]:
        group = [valid[tf] for tf in tfs if tf in valid]
        groups[name] = {"available": len(group), "total": len(tfs), "up": sum(d.startswith("alcista") for d in group),
                        "down": sum(d.startswith("bajista") for d in group), "weak": sum("débil" in d for d in group)}
    return {"label": label, "available": count, "up": up, "down": down, "weak": weak, "missing": missing,
            "score": max(up, down) / count if count else -1, "groups": groups}


def daily_means(bars):
    out = bars[bars.closed].copy()
    out["ema50"] = out.close.ewm(span=50, adjust=False, min_periods=50).mean()
    out["ema200"] = out.close.ewm(span=200, adjust=False, min_periods=200).mean()
    deviation = out.close - out.ema50
    out["distance_pct"] = deviation / out.ema50 * 100
    out["distance_std"] = deviation / out.close.rolling(50, min_periods=50).std().replace(0, np.nan)
    return out


def relative_performance(series, benchmark, sessions=20):
    rows = []
    for symbol, data in series.items():
        pair = pd.concat([data.rename("asset"), benchmark.rename("benchmark")], axis=1, join="inner").dropna().sort_index()
        if len(pair) <= sessions or (pair.tail(sessions + 1) <= 0).any().any():
            rows.append({"symbol": symbol, "relative_pp": None, "return_pct": None, "benchmark_pct": None, "last_session": None})
            continue
        window = pair.tail(sessions + 1)
        asset_return = (window.asset.iloc[-1] / window.asset.iloc[0] - 1) * 100
        bench_return = (window.benchmark.iloc[-1] / window.benchmark.iloc[0] - 1) * 100
        rows.append({"symbol": symbol, "relative_pp": float(asset_return - bench_return), "return_pct": float(asset_return),
                     "benchmark_pct": float(bench_return), "last_session": str(window.index[-1])})
    return pd.DataFrame(rows)


def ratio_analysis(y, x, window=50):
    """Ratio sobre cierres comunes positivos; media simple y desvío muestral."""
    y = pd.to_numeric(y, errors="coerce")
    x = pd.to_numeric(x, errors="coerce")
    y = y[~y.index.duplicated(keep="last")]
    x = x[~x.index.duplicated(keep="last")]
    pair = pd.concat([y.rename("y"), x.rename("x")], axis=1, join="inner").astype(float).dropna().sort_index()
    pair = pair[np.isfinite(pair).all(axis=1) & (pair > 0).all(axis=1)]
    out = pd.DataFrame({"ratio": pair.y / pair.x})
    out["mean"] = out.ratio.rolling(window, min_periods=window).mean()
    std = out.ratio.rolling(window, min_periods=window).std(ddof=1).replace(0, np.nan)
    out["distance_pct"] = (out.ratio / out["mean"] - 1) * 100
    out["distance_std"] = (out.ratio - out["mean"]) / std
    return out


def session_vwap(bars):
    """Precio típico y volumen del MISMO instrumento. Varianza ponderada poblacional."""
    if "symbol" in bars and bars.symbol.nunique() > 1:
        raise ValueError("El VWAP requiere precio y volumen de un único instrumento.")
    out = bars.copy()
    valid = np.isfinite(out[["high", "low", "close", "volume"]]).all(axis=1) & (out.volume > 0)
    price = (out.high + out.low + out.close) / 3
    weight = out.volume.where(valid, 0.0)
    anchor = price.where(valid).groupby(out.session).transform("first")
    shifted = price - anchor
    weighted = (shifted * weight).where(valid, 0.0)
    weighted2 = (shifted.pow(2) * weight).where(valid, 0.0)
    total = weight.groupby(out.session).cumsum().replace(0, np.nan)
    mean_shift = weighted.groupby(out.session).cumsum() / total
    out["vwap"] = anchor + mean_shift
    variance = weighted2.groupby(out.session).cumsum() / total - mean_shift.pow(2)
    out["sigma"] = np.sqrt(variance.clip(lower=0))
    out["volume_valid"] = valid
    out["distance_pct"] = (out.close / out.vwap - 1) * 100
    out["distance_bands"] = (out.close - out.vwap) / out.sigma.replace(0, np.nan)
    for factor in [1, 2]:
        out[f"upper{factor}"] = out.vwap + factor * out.sigma
        out[f"lower{factor}"] = out.vwap - factor * out.sigma
    return out


def select_range(bars, tf, defaults, now=None, start=None, end=None):
    if bars.empty:
        return bars, {"available": 0, "visible": 0, "short_history": True}
    endpoint = min(utc_now(now), bars.bar_end.max()) if end is None else pd.to_datetime(end, utc=True)
    config = defaults[tf]
    if start is not None:
        begin = pd.to_datetime(start, utc=True)
    elif "sessions" in config:
        sessions = bars.session.drop_duplicates().tolist()
        chosen = sessions[-config["sessions"]:]
        begin = bars.loc[bars.session.isin(chosen), "timestamp"].min()
    else:
        begin = endpoint - pd.DateOffset(months=config["months"]) if "months" in config else endpoint - pd.DateOffset(years=config["years"])
    visible = bars[(bars.timestamp >= begin) & (bars.timestamp <= endpoint)]
    short = bars.timestamp.min() > begin if "sessions" not in config else bars.session.nunique() < config["sessions"]
    return visible, {"available": len(bars), "visible": len(visible), "short_history": bool(short), "requested_start": begin,
                     "start": visible.timestamp.min(), "end": visible.bar_end.max(), "sessions": visible.session.nunique()}


def aggregate_4h(hourly, timezone="UTC", open_times=None, calendar_name=None, now=None):
    """Agrupa sin modificar las velas guardadas. Configuración validable de plataforma."""
    times = open_times or ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00"]
    minutes = sorted(int(t[:2]) * 60 + int(t[3:]) for t in times)
    if len(minutes) != 6 or any((minutes[(i+1) % 6] - minutes[i]) % 1440 != 240 for i in range(6)):
        raise ValueError("El horario 4h debe tener seis aperturas separadas por cuatro horas.")
    if hourly.empty:
        return hourly
    index = pd.to_datetime(hourly.timestamp, utc=True).dt.tz_convert(timezone)
    shifted = index - pd.Timedelta(minutes=minutes[0])
    # floor en zona de plataforma: UTC provisional no tiene horas ambiguas.
    buckets = shifted.dt.floor("4h", ambiguous="infer", nonexistent="shift_forward") + pd.Timedelta(minutes=minutes[0])
    frame = hourly.assign(bucket=buckets.dt.tz_convert("UTC"))
    result = frame.groupby("bucket", sort=True).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum"), bar_end=("bar_end", "max"), closed=("closed", "all"), session=("session", "last"))
    result.index.name = "timestamp"
    result = result.reset_index()
    if calendar_name:
        expected = result.timestamp + pd.Timedelta(hours=4)
        segments = trading_segments(calendar_name, result.timestamp.min() - pd.Timedelta(days=3), expected.max() + pd.Timedelta(days=3))
        starts = np.array([a.value for a, _, _ in segments], dtype=np.int64)
        ends = np.array([b.value for _, b, _ in segments], dtype=np.int64)
        observed = pd.DatetimeIndex(result.bar_end).as_unit("ns").asi8
        limits = pd.DatetimeIndex(expected).as_unit("ns").asi8
        positions = np.searchsorted(ends, observed, side="right")
        remaining = (positions < len(segments)) & (starts[np.minimum(positions, len(segments)-1)] < limits)
        result["bar_end"] = pd.to_datetime(np.where(remaining, limits, observed), utc=True)
        result["closed"] = result.closed & (result.bar_end <= utc_now(now))
    return result


def aggregate_regular_hours(bars, now=None):
    """Horas desde 09:30 NY, usando velas pequeñas; no corta una hora de Yahoo."""
    if bars.empty:
        return bars
    sch = schedule("NYSE", bars.session.iloc[0], bars.session.iloc[-1])
    openings = {str(day.date()): row.market_open for day, row in sch.iterrows()}
    closings = {str(day.date()): row.market_close for day, row in sch.iterrows()}
    start = pd.to_datetime(bars.session.map(openings), utc=True)
    slot = ((bars.timestamp - start).dt.total_seconds() // 3600).astype(int)
    buckets = start + pd.to_timedelta(slot, unit="h")
    result = bars.assign(bucket=buckets).groupby("bucket", sort=True).agg(open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"), volume=("volume", "sum"), session=("session", "last"), closed=("closed", "all"))
    result.index.name = "timestamp"
    result = result.reset_index()
    end = result.timestamp + pd.Timedelta(hours=1)
    limit = pd.to_datetime(result.session.map(closings), utc=True)
    result["bar_end"] = end.where(end <= limit, limit)
    result["closed"] = result.closed & (result.bar_end <= utc_now(now))
    return result


def unexpected_gaps(bars, tf, calendar_name):
    if len(bars) < 2:
        return []
    gaps = []
    if tf == "1D":
        sch = schedule(calendar_name, bars.session.iloc[0], bars.session.iloc[-1])
        missing = [str(d.date()) for d in sch.index if str(d.date()) not in set(bars.session)]
        return [f"Falta la rueda {day}." for day in missing]
    for a, b in zip(bars.itertuples(), bars.iloc[1:].itertuples()):
        if b.timestamp <= a.bar_end:
            continue
        minutes = market_minutes_between(a.bar_end, b.timestamp, calendar_name)
        if minutes >= SECONDS[tf] / 60 * .9:
            gaps.append(f"Sin velas entre {a.bar_end.isoformat()} y {b.timestamp.isoformat()} con mercado abierto.")
    return gaps


def _pair_test(logs, diff_lags=1):
    y, x = logs.iloc[:, 0], logs.iloc[:, 1]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", np.exceptions.ComplexWarning)
        p_yx, p_xy = float(coint(y, x)[1]), float(coint(x, y)[1])
        joh = coint_johansen(logs.to_numpy(), det_order=0, k_ar_diff=diff_lags)
    if not np.isfinite([p_yx, p_xy]).all() or np.max(np.abs(joh.eig.imag)) > 1e-8:
        raise ValueError("El test no devolvió valores válidos.")
    rank = 0
    for i in range(2):
        if joh.lr1[i] > joh.cvt[i, 1]:
            rank += 1
        else:
            break
    return {"p_yx": p_yx, "p_xy": p_xy, "johansen_rank": rank}


def pair_analysis(y, x, cfg):
    """Solo 1D: cinco bloques disjuntos; comparación principal con beta larga fija."""
    pair = pd.concat([y.rename("y"), x.rename("x")], axis=1, join="inner").dropna().sort_index()
    pair = pair[(pair > 0).all(axis=1)]
    window, blocks = cfg["primary_window"], cfg["required_blocks"]
    if len(pair) < window * blocks:
        return {"state": "no calculable", "reason": "Historia insuficiente para evaluar estabilidad", "bars": len(pair), "blocks": len(pair) // window}
    try:
        logs = np.log(pair)
        primary = _pair_test(logs.tail(window), cfg["johansen_diff_lags"])
        contrast = _pair_test(logs.tail(cfg["contrast_window"]), cfg["johansen_diff_lags"])
        evidence = []
        for i in range(blocks):
            end = len(logs) - i * window
            result = _pair_test(logs.iloc[end-window:end], cfg["johansen_diff_lags"])
            evidence.append(result["p_yx"] < cfg["p_threshold"] and result["p_xy"] < cfg["p_threshold"])
        confirms = sum(evidence)
        current = primary["p_yx"] < cfg["p_threshold"] and primary["p_xy"] < cfg["p_threshold"]
        agrees = contrast["p_yx"] < cfg["p_threshold"] and contrast["p_xy"] < cfg["p_threshold"]
        if current and agrees and primary["johansen_rank"] == contrast["johansen_rank"] == 1 and confirms >= cfg["stable_blocks"]:
            state = "estable"
        elif confirms or current or agrees or min(primary["p_yx"], primary["p_xy"], contrast["p_yx"], contrast["p_xy"]) < cfg["p_threshold"] or primary["johansen_rank"] == 1 or contrast["johansen_rank"] == 1:
            state = "intermitente"
        else:
            state = "sin relación"
        fit = sm.OLS(logs.y, sm.add_constant(logs.x)).fit()
        alpha, beta = map(float, fit.params.iloc[:2])
        spread = logs.y - beta * logs.x
        short = spread.tail(cfg["short_spread_window"])
        std_long, std_short = spread.std(), short.std()
        if std_long <= 0 or std_short <= 0:
            raise ValueError("La diferencia no tiene dispersión válida para compararla.")
        rolling = []
        ends = list(range(window, len(logs) + 1, cfg["rolling_step"]))
        if ends[-1] != len(logs):
            ends.append(len(logs))
        for end in ends:
            sample = logs.iloc[end-window:end]
            rolling.append({"date": sample.index[-1], "p_yx": float(coint(sample.y, sample.x)[1]), "p_xy": float(coint(sample.x, sample.y)[1])})
        return {"state": state, "reason": "Sin relación confirmada en el período analizado" if state == "sin relación" else "",
                "bars": len(pair), "blocks": len(pair) // window, "confirmed_blocks": int(confirms), "evaluated_blocks": blocks,
                "primary": primary, "contrast": contrast, "beta": beta, "alpha": alpha, "spread": spread,
                "mean_long": float(spread.mean()), "std_long": float(std_long), "mean_short": float(short.mean()),
                "std_short": float(std_short), "z_short": float((spread.iloc[-1] - short.mean()) / std_short),
                "z_long": float((spread.iloc[-1] - spread.mean()) / std_long), "rolling": pd.DataFrame(rolling),
                "start": str(pair.index[0]), "end": str(pair.index[-1])}
    except Exception as exc:
        return {"state": "no calculable", "reason": str(exc), "bars": len(pair), "blocks": len(pair) // window}
