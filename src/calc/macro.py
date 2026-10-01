"""
macro.py — Métricas y análisis fundamental de series de la Reserva Federal (FRED).
Calcula:
  - Nivel actual.
  - Cambio a 1 mes (absoluto y porcentual).
  - Percentil histórico en ventana de 10 años.
"""

from typing import Dict, Any, Optional
import pandas as pd
import numpy as np


def analyze_fred_series(
    df: pd.DataFrame,
    change_days: int = 30,
    percentile_years: int = 10,
) -> Dict[str, Any]:
    """
    Analiza una serie de FRED entregando nivel actual, cambio a 1 mes y percentil histórico.
    """
    if df.empty or len(df) < 5:
        return {
            "current_value": None,
            "change_1m": None,
            "pct_change_1m": None,
            "percentile": None,
            "timestamp": None,
        }

    s = df.sort_values("timestamp").dropna(subset=["value"]).reset_index(drop=True)
    latest_row = s.iloc[-1]
    latest_val = float(latest_row["value"])
    latest_ts = latest_row["timestamp"]

    # 1. Cambio a 1 mes (~30 días hacia atrás)
    target_dt = latest_ts - pd.Timedelta(days=change_days)
    prior_rows = s[s["timestamp"] <= target_dt]

    if not prior_rows.empty:
        prior_val = float(prior_rows.iloc[-1]["value"])
        change_1m = latest_val - prior_val
        pct_change_1m = (change_1m / abs(prior_val) * 100.0) if prior_val != 0 else 0.0
    else:
        # Si la historia es menor a 30 días, comparar con el primer dato disponible
        prior_val = float(s.iloc[0]["value"])
        change_1m = latest_val - prior_val
        pct_change_1m = (change_1m / abs(prior_val) * 100.0) if prior_val != 0 else 0.0

    # 2. Percentil histórico en los últimos X años
    earliest_cutoff = latest_ts - pd.Timedelta(days=int(percentile_years * 365.25))
    hist_window = s[s["timestamp"] >= earliest_cutoff]["value"]

    if len(hist_window) > 10:
        percentile = (hist_window <= latest_val).mean() * 100.0
    else:
        percentile = (s["value"] <= latest_val).mean() * 100.0

    return {
        "current_value": round(latest_val, 4),
        "change_1m": round(change_1m, 4),
        "pct_change_1m": round(pct_change_1m, 2),
        "percentile": round(percentile, 1),
        "timestamp": latest_ts,
    }
