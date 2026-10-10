"""Lecturas adicionales del piloto, compartidas por pantalla e historial."""
import numpy as np
import pandas as pd

from src.indices_math import ratio_analysis, session_vwap, SECONDS


def common_performance(series, sessions=20):
    """Rendimientos de TODOS los activos sobre exactamente las mismas ruedas."""
    columns = [pd.to_numeric(values, errors="coerce").rename(symbol)
               for symbol, values in series.items()]
    common = pd.concat(columns, axis=1, join="inner").sort_index() if columns else pd.DataFrame()
    common = common.replace([np.inf, -np.inf], np.nan).dropna()
    common = common[(common > 0).all(axis=1)]
    rows = []
    for symbol in series:
        enough = len(common) > sessions
        window = common.tail(sessions + 1)
        rows.append({"symbol": symbol,
                     "return_pct": float((window[symbol].iloc[-1] / window[symbol].iloc[0] - 1) * 100) if enough else None,
                     "start_session": str(window.index[0]) if enough else None,
                     "last_session": str(window.index[-1]) if enough else None,
                     "common_sessions": len(common), "return_sessions": sessions})
    return pd.DataFrame(rows)


def ratio_reading(daily, spec):
    y, x = spec["y"], spec["x"]
    history = ratio_analysis(daily[y].set_index("session").close,
                             daily[x].set_index("session").close, spec["window"])
    fields = {"pair": f"{y}/{x}", "y": y, "x": x, "label": spec["label"],
              "window": spec["window"], "last_session": str(history.index[-1]) if len(history) else None}
    for field in ("ratio", "mean", "distance_pct", "distance_std"):
        value = history[field].iloc[-1] if len(history) else None
        fields[field] = float(value) if value is not None and pd.notna(value) else None
    if spec.get("percentile_window"):
        valid = history.distance_std.dropna()
        history["percentile"] = valid.rolling(spec["percentile_window"], min_periods=20).rank(method="max", pct=True).reindex(history.index) * 100
        value = history.percentile.iloc[-1] if len(history) else None
        fields["percentile"] = float(value) if value is not None and pd.notna(value) else None
        fields["percentile_window"] = spec["percentile_window"]
        for key, symbol in (("y_exchange", y), ("x_exchange", x)):
            fields[key] = str(daily[symbol].source.iloc[-1]) if "source" in daily[symbol] and len(daily[symbol]) else None
    return fields, history


def select_exchange(raw, expected, requested=None):
    """Una sola exchange por serie; nunca atribuir ni mezclar volumen ajeno."""
    if raw.empty:
        return raw.copy(), {"exchange": None, "expected": expected, "sources": [], "changed": False}
    if "source" not in raw:
        return raw.iloc[:0].copy(), {"exchange": None, "expected": expected, "sources": [], "changed": True}
    ordered = raw.sort_values("timestamp")
    source = ordered.source.fillna("").astype(str).str.lower()
    observed = source[source != ""].drop_duplicates().tolist()
    actual = requested or source.iloc[-1]
    info = {"exchange": actual or None, "expected": expected, "sources": observed,
            "changed": len(observed) > 1 or actual != expected}
    if not actual:
        return ordered.iloc[:0].copy(), info
    return ordered[source == actual].assign(source=actual).copy(), info


def crypto_vwap_readings(frames, symbols, minimum_coverage=0.95):
    """Distancias en la MISMA sesión UTC y corte común de velas terminadas."""
    chosen = {}
    for symbol in symbols:
        for tf in ("1m", "5m", "15m", "1h"):
            frame = frames.get((symbol, tf))
            if frame is not None and len(frame[frame.closed]):
                closed = frame[frame.closed]
                if "source" not in closed or closed.source.nunique() != 1:
                    raise ValueError("El VWAP cripto requiere una única exchange identificada.")
                chosen[symbol] = (tf, closed)
                break
    if not chosen:
        return {}
    endpoint = min(frame.bar_end.max() for _, frame in chosen.values())
    common_ends = None
    for _, frame in chosen.values():
        ends = pd.DatetimeIndex(frame.loc[(frame.bar_end <= endpoint) &
                                         (frame.bar_end > endpoint - pd.Timedelta(days=2)), "bar_end"])
        common_ends = ends if common_ends is None else common_ends.intersection(ends)
    if common_ends is None or common_ends.empty:
        return {}
    endpoint = common_ends.max()
    # Un cierre exactamente a medianoche pertenece a la última vela del día
    # anterior. La vela nueva de las 00:00 todavía no terminó.
    day_start = (endpoint - pd.Timedelta(nanoseconds=1)).normalize()
    results = {}
    for symbol, (tf, frame) in chosen.items():
        source = frame[(frame.timestamp >= day_start) & (frame.bar_end <= endpoint)].copy()
        if source.empty:
            continue
        vw = session_vwap(source)
        expected = max(1, int((endpoint - day_start).total_seconds() / SECONDS[tf]))
        coverage = float(vw.volume_valid.sum() / expected)
        last = vw.iloc[-1]
        usable = coverage >= minimum_coverage and source.timestamp.iloc[0] == day_start and pd.notna(last.vwap)
        results[symbol] = {"exchange": str(source.source.iloc[-1]), "session": str(day_start.date()),
                           "asof": last.bar_end.isoformat(), "common_cutoff": endpoint.isoformat(), "base_tf": tf,
                           "price": float(last.close), "vwap": float(last.vwap) if pd.notna(last.vwap) else None,
                           "sigma": float(last.sigma) if pd.notna(last.sigma) else None,
                           "distance_pct": float(last.distance_pct) if pd.notna(last.distance_pct) else None,
                           "distance_bands": float(last.distance_bands) if pd.notna(last.distance_bands) else None,
                           "volume_coverage": coverage, "usable": bool(usable)}
    return results


def crypto_kpis(rows, alignments, ratios, vwaps):
    aligned = max(alignments, key=lambda s: alignments[s]["score"], default=None)
    if aligned and not alignments[aligned]["available"]:
        aligned = None
    valid = {s: v for s, v in vwaps.items() if v["usable"] and v["distance_pct"] is not None}
    furthest = max(valid, key=lambda s: abs(valid[s]["distance_pct"]), default=None)
    return {"up": sum(r["direction"].startswith("alcista") for r in rows),
            "down": sum(r["direction"].startswith("bajista") for r in rows), "total": len(rows),
            "most_aligned": aligned, "alignment": alignments.get(aligned),
            "eth_btc": ratios.get("ETH/BTC"), "sol_btc": ratios.get("SOL/BTC"),
            "furthest_vwap": {"symbol": furthest, **valid[furthest]} if furthest else None}


def pair_coverage(frames, pairs, pilot):
    rows = []
    for pair in pairs:
        for tf in pilot["cointegration_scales"]:
            values, exchanges = [], []
            for symbol in (pair["y"], pair["x"]):
                frame = frames[(symbol, tf)]
                closed = frame[frame.closed]
                values.append(closed.set_index("session" if tf == "1D" else "timestamp").close.rename(symbol))
                exchanges.append(str(closed.source.iloc[-1]) if len(closed) else None)
            common = pd.concat(values, axis=1, join="inner").dropna()
            common = common[(common > 0).all(axis=1)]
            size = pilot["cointegration"]["primary_window"]
            required = pilot["cointegration"]["required_blocks"]
            rows.append({"y": pair["y"], "x": pair["x"], "tf": tf, "bars": len(common),
                         "blocks": len(common) // size, "block_size": size, "required_blocks": required,
                         "enough": len(common) >= size * required, "exchanges": exchanges,
                         "last_common": str(common.index.max()) if len(common) else None})
    return rows
