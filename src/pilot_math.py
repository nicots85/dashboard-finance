"""Lecturas adicionales del piloto, compartidas por pantalla e historial."""
import numpy as np
import pandas as pd

from src.indices_math import ratio_analysis


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
    return fields, history
