"""
cointegration.py — Análisis de Cointegración para pares de activos con test de Engle-Granger.

¿POR QUÉ NO SE APLICA EN 1m / 5m / 15m?
-----------------------------------------------------------------------------------------
En temporalidades ultra-cortas (1m a 15m), las series de precios están dominadas por
el "ruido de microestructura" del mercado:
  1. Asincronía de ejecución: los dos activos rara vez se transan en el milisegundo exacto,
     generando retrasos artificiales (efecto lead-lag espurio).
  2. Rebote de punta compradora/vendedora (Bid-Ask Bounce): el precio oscila entre el bid
     y el ask aunque el valor de equilibrio no haya cambiado.
  3. Violación del supuesto de no-estacionariedad integrada I(1): a nivel intradiario
     muy rápido, las correlaciones se distorsionan drásticamente y generan falsos positivos
     de cointegración que colapsan en trading real.
Por ende, la cointegración estadística solo es válida y robusta en escalas operativas
superiores: 1h, 4h y 1D.
-----------------------------------------------------------------------------------------

Métricas calculadas:
  - p-valor del test de Engle-Granger sobre precios en logaritmo natural.
  - Beta (ratio de cobertura óptimo por MCO: ln(y) = beta * ln(x) + alpha).
  - Spread = ln(y) - beta * ln(x).
  - Z-score actual del spread.
  - Vida media de reversión a la media (Ornstein-Uhlenbeck: half_life = -ln(2) / lambda).
  - Porcentaje de cointegración en ventanas móviles recientes.
"""

from typing import Dict, Any, Optional, Tuple, List
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint
import statsmodels.api as sm


def align_pair_series(
    df_y: pd.DataFrame,
    df_x: pd.DataFrame,
) -> Tuple[pd.Series, pd.Series, pd.DatetimeIndex]:
    """Alinea dos series por timestamp UTC mediante inner join y extrae los precios de cierre en log."""
    if df_y.empty or df_x.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float), pd.DatetimeIndex([])

    s_y = df_y.set_index("timestamp")["close"].dropna()
    s_x = df_x.set_index("timestamp")["close"].dropna()

    combined = pd.concat([s_y, s_x], axis=1, join="inner").dropna()
    combined.columns = ["y", "x"]

    # Descartar valores no positivos antes de log
    valid = combined[(combined["y"] > 0) & (combined["x"] > 0)]
    if len(valid) < 30:
        return pd.Series(dtype=float), pd.Series(dtype=float), pd.DatetimeIndex([])

    log_y = np.log(valid["y"])
    log_x = np.log(valid["x"])
    return log_y, log_x, valid.index


def compute_half_life(spread: pd.Series) -> Optional[float]:
    """Calcula la vida media de reversión a la media usando el modelo Ornstein-Uhlenbeck (AR(1))."""
    if len(spread) < 20:
        return None

    # delta_spread = -lambda * spread_{t-1} + error
    spread_lag = spread.shift(1).dropna()
    delta_spread = spread.diff().dropna()

    # Alinear
    common_idx = spread_lag.index.intersection(delta_spread.index)
    if len(common_idx) < 15:
        return None

    X = sm.add_constant(spread_lag.loc[common_idx])
    y = delta_spread.loc[common_idx]

    try:
        model = sm.OLS(y, X).fit()
        beta_lag = model.params.iloc[1]

        # Si beta_lag >= 0 no hay reversión a la media (la serie explota o es random walk)
        if beta_lag >= 0:
            return None

        # half_life = -ln(2) / lambda donde lambda = beta_lag
        half_life = -np.log(2) / beta_lag
        return float(half_life)
    except Exception:
        return None


def evaluate_pair_cointegration(
    df_y: pd.DataFrame,
    df_x: pd.DataFrame,
    window_size: int = 250,
    p_value_threshold: float = 0.05,
    rolling_windows_eval: int = 20,
) -> Dict[str, Any]:
    """
    Evalúa la cointegración de un par de activos.
    """
    empty_result = {
        "is_cointegrated": False,
        "p_value": None,
        "beta": None,
        "z_spread": None,
        "half_life": None,
        "pct_coint_windows": 0.0,
        "aligned_bars": 0,
        "timestamp": None,
        "calc_status": "no_calculable",
        "error_message": "No hay al menos 30 velas coincidentes, válidas y positivas para el par.",
    }

    log_y, log_x, timestamps = align_pair_series(df_y, df_x)
    total_len = len(log_y)

    if total_len < 30:
        return empty_result
    empty_result["timestamp"] = timestamps[-1]
    empty_result["aligned_bars"] = total_len

    # Si hay menos velas que window_size, usamos todo lo que haya
    eval_len = min(window_size, total_len)
    y_window = log_y.iloc[-eval_len:]
    x_window = log_x.iloc[-eval_len:]

    try:
        # 1. Test de Cointegración de Engle-Granger
        score, p_value, _ = coint(y_window, x_window)
        if not np.isfinite(p_value):
            raise ValueError("El test devolvió un p-valor no calculable, no un resultado negativo.")

        # 2. Regresión OLS para Beta (Ratio de cobertura)
        X = sm.add_constant(x_window)
        ols_res = sm.OLS(y_window, X).fit()
        alpha = ols_res.params.iloc[0]
        beta = ols_res.params.iloc[1]

        # 3. Spread y Z-score del Spread
        spread = y_window - (beta * x_window + alpha)
        spread_mean = spread.mean()
        spread_std = spread.std()
        z_spread = (spread.iloc[-1] - spread_mean) / spread_std if spread_std > 0 else 0.0

        # 4. Vida Media (Half-Life)
        half_life = compute_half_life(spread)

        # 5. Estabilidad en ventanas móviles recientes
        coint_count = 0
        tested_windows = 0
        step = 5  # cada 5 velas retrocedemos para evaluar estabilidad

        for i in range(rolling_windows_eval):
            end_idx = total_len - (i * step)
            start_idx = end_idx - eval_len
            if start_idx < 0:
                break
            y_sub = log_y.iloc[start_idx:end_idx]
            x_sub = log_x.iloc[start_idx:end_idx]
            try:
                _, p_sub, _ = coint(y_sub, x_sub)
                tested_windows += 1
                if p_sub < p_value_threshold:
                    coint_count += 1
            except Exception:
                continue

        pct_stable = (coint_count / tested_windows * 100.0) if tested_windows > 0 else 0.0
        is_coint = bool(p_value < p_value_threshold)

        return {
            "is_cointegrated": is_coint,
            "p_value": float(p_value),
            "beta": float(beta),
            "z_spread": float(z_spread),
            "half_life": float(half_life) if half_life is not None else None,
            "pct_coint_windows": round(pct_stable, 1),
            "aligned_bars": total_len,
            "timestamp": timestamps[-1],
            "calc_status": "ok",
            "error_message": None,
        }

    except Exception as e:
        return {**empty_result, "error_message": f"No se pudo calcular la cointegración: {e}"}
