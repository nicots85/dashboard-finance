"""
zscore.py — Dispersión ajustada por volatilidad (Z-Score por ATR y por Desvío Estándar).
Fórmulas:
  - z_atr = (cierre - EMA) / ATR
  - z_std = (cierre - SMA) / STD
Determina zonas extremas (|z| > 2) y el percentil histórico del z actual.
"""

from typing import Dict, Any, Optional
import numpy as np
import pandas as pd
from src.calc.regime import calculate_atr


def compute_zscore_history(
    df: pd.DataFrame,
    mean_type: str = "ema",
    period: int = 50,
    atr_period: int = 14,
    std_period: int = 50,
    extreme_threshold: float = 2.0,
    percentile_window: int = 250,
) -> pd.DataFrame:
    """
    Calcula la serie histórica de z-score normalizado por ATR y por Desvío Estándar.
    Retorna el DataFrame con columnas:
      ['z_mean', 'z_atr', 'z_std', 'is_extreme', 'z_percentile']
    """
    if len(df) < max(period, atr_period, std_period) + 5:
        out = df.copy()
        out["z_mean"] = np.nan
        out["z_atr"] = np.nan
        out["z_std"] = np.nan
        out["is_extreme"] = False
        out["z_percentile"] = np.nan
        return out

    out = df.copy()

    # 1. Media central (EMA o SMA)
    if mean_type.lower() == "ema":
        mean = out["close"].ewm(span=period, adjust=False).mean()
    else:
        mean = out["close"].rolling(window=period, min_periods=period).mean()
    out["z_mean"] = mean

    # 2. ATR
    atr = calculate_atr(out, period=atr_period)
    atr_safe = atr.replace(0, np.nan)

    # 3. Desvío Estándar
    std = out["close"].rolling(window=std_period, min_periods=std_period).std()
    std_safe = std.replace(0, np.nan)

    # 4. Cálculo de z-scores
    deviation = out["close"] - mean
    out["z_atr"] = deviation / atr_safe
    out["z_std"] = deviation / std_safe

    # 5. Detección de zonas extremas
    out["is_extreme"] = out["z_atr"].abs() > extreme_threshold

    # 6. Percentil histórico del z-score en ventana móvil
    def rolling_pct(x):
        if len(x) < 10 or pd.isna(x.iloc[-1]):
            return np.nan
        val = x.iloc[-1]
        valid = x.dropna()
        return (valid <= val).mean() * 100.0

    out["z_percentile"] = out["z_atr"].rolling(window=percentile_window, min_periods=20).apply(rolling_pct, raw=False)

    return out


def get_latest_zscore(
    df: pd.DataFrame,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Calcula y devuelve las métricas de Z-Score para la última vela de un activo."""
    if config is None:
        config = {}

    mean_type = config.get("mean_type", "ema")
    period = config.get("period", 50)
    atr_period = config.get("atr_period", 14)
    std_period = config.get("std_period", 50)
    extreme_th = config.get("extreme_threshold", 2.0)
    pct_window = config.get("percentile_window", 250)

    if df.empty or len(df) < 20:
        return {
            "z_atr": None,
            "z_std": None,
            "is_extreme": False,
            "z_percentile": None,
            "mean": None,
            "close": None,
            "timestamp": None,
        }

    if len(df) < max(period, atr_period, std_period) + 5:
        return {"z_atr": None, "z_std": None, "is_extreme": False, "z_percentile": None,
                "mean": None, "close": float(df["close"].iloc[-1]) if pd.notna(df["close"].iloc[-1]) else None,
                "timestamp": df["timestamp"].iloc[-1]}
    mean = df["close"].ewm(span=period, adjust=False).mean() if mean_type.lower() == "ema" else df["close"].rolling(period, min_periods=period).mean()
    atr = calculate_atr(df, atr_period).replace(0, np.nan)
    std = df["close"].rolling(std_period, min_periods=std_period).std().replace(0, np.nan)
    z_atr = (df["close"] - mean) / atr
    za = z_atr.iloc[-1]
    zs = ((df["close"] - mean) / std).iloc[-1]
    recent = z_atr.tail(pct_window).dropna()
    pct = (recent <= za).mean() * 100 if len(recent) >= 20 and pd.notna(za) else np.nan
    return {
        "z_atr": float(za) if pd.notna(za) else None,
        "z_std": float(zs) if pd.notna(zs) else None,
        "is_extreme": bool(abs(za) > extreme_th) if pd.notna(za) else False,
        "z_percentile": float(pct) if pd.notna(pct) else None,
        "mean": float(mean.iloc[-1]) if pd.notna(mean.iloc[-1]) else None,
        "close": float(df["close"].iloc[-1]) if pd.notna(df["close"].iloc[-1]) else None,
        "timestamp": df["timestamp"].iloc[-1],
    }
