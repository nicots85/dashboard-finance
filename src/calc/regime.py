"""
regime.py — Cálculo del Régimen de Mercado (Dirección + Volatilidad).
Utiliza:
  - Dirección: Pendiente de EMA (por defecto 50) y fuerza con ADX (por defecto 14).
               Si ADX < 20 -> 'lateral'. Si ADX >= 20 -> 'alcista' si EMA sube, 'bajista' si baja.
  - Volatilidad: Percentil histórico de ATR (14) en ventana móvil de 250 velas.
                 < 25% -> 'baja vol', > 75% -> 'alta vol', resto -> 'normal vol'.
  - Etiqueta combinada: ej. 'alcista / baja vol'.
"""

from typing import Dict, Any, Optional
import numpy as np
import pandas as pd


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calcula el Average True Range (ATR) de Wilder."""
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder smoothing (RMA o ewm con alpha = 1/period)
    atr = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return atr


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calcula el Average Directional Index (ADX) clásico de Welles Wilder."""
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)

    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    alpha = 1.0 / period
    atr = tr.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    plus_dm_s = pd.Series(plus_dm, index=df.index).ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    minus_dm_s = pd.Series(minus_dm, index=df.index).ewm(alpha=alpha, min_periods=period, adjust=False).mean()

    # Prevenir división por cero
    atr_safe = atr.replace(0, np.nan)
    plus_di = 100.0 * (plus_dm_s / atr_safe)
    minus_di = 100.0 * (minus_dm_s / atr_safe)

    di_sum = plus_di + minus_di
    di_diff = (plus_di - minus_di).abs()
    dx = 100.0 * (di_diff / di_sum.replace(0, np.nan))
    adx = dx.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    return adx


def compute_market_regime_history(
    df: pd.DataFrame,
    ema_period: int = 50,
    adx_period: int = 14,
    adx_threshold_lateral: float = 20.0,
    atr_period: int = 14,
    atr_percentile_window: int = 250,
    volatility_low_pct: float = 25.0,
    volatility_high_pct: float = 75.0,
    weak_trend_z: float = 2.0,
    config: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    """
    Calcula el régimen de mercado para toda la serie histórica de un activo.
    Retorna el DataFrame original con columnas adicionales:
      ['ema', 'adx', 'atr', 'atr_percentile', 'direction', 'volatility', 'regime']
    """
    if len(df) < max(ema_period, adx_period, atr_period) + 5:
        # Datos insuficientes
        out = df.copy()
        out["ema"] = np.nan
        out["adx"] = np.nan
        out["atr"] = np.nan
        out["atr_percentile"] = np.nan
        out["direction"] = "sin datos"
        out["strength"] = "sin datos"
        out["volatility"] = "sin datos"
        out["regime"] = "sin datos"
        return out

    out = df.copy()

    # 1. EMA y Pendiente
    ema = out["close"].ewm(span=ema_period, adjust=False).mean()
    out["ema"] = ema
    # Pendiente: diferencia de EMA respecto a la vela anterior (o suavizado a 3 velas)
    ema_slope = ema.diff()

    # 2. ADX
    adx = calculate_adx(out, period=adx_period)
    out["adx"] = adx

    # ATR (se necesita antes para el z-ATR de la regla 'débil')
    atr = calculate_atr(out, period=atr_period)
    out["atr"] = atr

    # 3. Clasificación de Dirección (Alt 1)
    # Dirección = signo de la pendiente de la EMA, con zona "plana" cuando
    # la pendiente es pequeña (umbral relativo al ATR)
    atr_safe = atr.replace(0, np.nan)
    z_atr = (out["close"] - ema) / atr_safe
    out["z_atr"] = z_atr
    slope_threshold = 0.05 * atr_safe  # 5% del ATR como umbral de "plana"

    conditions_dir = [
        (ema_slope > slope_threshold),
        (ema_slope < -slope_threshold),
    ]
    choices_dir = ["alcista", "bajista"]
    out["direction"] = np.select(conditions_dir, choices_dir, default="lateral")

    # 4. Clasificación de Fuerza (Alt 3: histéresis en fuerza)
    # Fuerza = ADX en tres niveles con histéresis de 2 puntos
    conditions_strength = [
        (adx < adx_threshold_lateral),  # débil
        (adx > 25),  # fuerte
    ]
    choices_strength = ["débil", "fuerte"]
    strength_raw = np.select(conditions_strength, choices_strength, default="media")
    
    # Aplicar histéresis si está habilitada
    if config and config.get("strength_hysteresis", False):
        strength = strength_raw.copy()
        for i in range(1, len(df)):
            prev = strength[i-1]
            curr_raw = strength_raw[i]
            if prev == "débil" and curr_raw == "media":
                # Para pasar de débil a media, exigir ADX >= 20 + 2
                if adx.iloc[i] < adx_threshold_lateral + 2:
                    strength[i] = "débil"
            elif prev == "media":
                if curr_raw == "débil":
                    # Para pasar de media a débil, exigir ADX < 20 - 2
                    if adx.iloc[i] >= adx_threshold_lateral - 2:
                        strength[i] = "media"
                elif curr_raw == "fuerte":
                    # Para pasar de media a fuerte, exigir ADX > 25 + 2
                    if adx.iloc[i] <= 25 + 2:
                        strength[i] = "media"
            elif prev == "fuerte" and curr_raw == "media":
                # Para pasar de fuerte a media, exigir ADX <= 25 - 2
                if adx.iloc[i] > 25 - 2:
                    strength[i] = "fuerte"
        out["strength"] = strength
    else:
        out["strength"] = strength_raw

    # Percentil móvil del ATR respecto a su ventana histórica
    def rolling_pct(x):
        if len(x) < 10 or pd.isna(x.iloc[-1]):
            return np.nan
        val = x.iloc[-1]
        valid = x.dropna()
        return (valid <= val).mean() * 100.0

    # Usar rolling sobre ATR
    atr_percentile = atr.rolling(window=atr_percentile_window, min_periods=20).apply(rolling_pct, raw=False)
    out["atr_percentile"] = atr_percentile

    # 5. Clasificación de Volatilidad
    conditions_vol = [
        atr_percentile < volatility_low_pct,
        atr_percentile > volatility_high_pct,
    ]
    choices_vol = ["baja vol", "alta vol"]
    out["volatility"] = np.select(conditions_vol, choices_vol, default="normal vol")

    # Si hay NaN en los primeros períodos
    out.loc[out["adx"].isna() | out["ema"].isna(), "direction"] = "sin datos"
    out.loc[out["atr_percentile"].isna(), "volatility"] = "normal vol"

    # 6. Etiqueta combinada (Alt 1)
    out["regime"] = out["direction"] + " " + out["strength"] + " / " + out["volatility"]
    out.loc[out["direction"] == "sin datos", "regime"] = "sin datos"

    return out


def get_latest_market_regime(
    df: pd.DataFrame,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Calcula y devuelve el régimen exclusivamente para la última vela de un activo."""
    if config is None:
        config = {}

    ema_p = config.get("ema_period", 50)
    adx_p = config.get("adx_period", 14)
    adx_th = config.get("adx_threshold_lateral", 20.0)
    atr_p = config.get("atr_period", 14)
    atr_win = config.get("atr_percentile_window", 250)
    vol_low = config.get("volatility_low_pct", 25.0)
    vol_high = config.get("volatility_high_pct", 75.0)
    weak_z = config.get("weak_trend_z", 2.0)

    if df.empty or len(df) < 20:
        return {
            "direction": "sin datos",
            "strength": "sin datos",
            "volatility": "sin datos",
            "regime": "sin datos",
            "adx": None,
            "atr": None,
            "atr_percentile": None,
            "ema": None,
            "close": None,
            "timestamp": None,
        }

    # Misma fórmula sobre TODA la historia, sin calcular percentiles de cada
    # vela anterior cuando solo se necesita el último (fundamental para 1m).
    if len(df) < max(ema_p, adx_p, atr_p) + 5:
        return {"direction": "sin datos", "strength": "sin datos", "volatility": "sin datos", "regime": "sin datos",
                "adx": None, "atr": None, "atr_percentile": None, "ema": None,
                "close": float(df["close"].iloc[-1]) if pd.notna(df["close"].iloc[-1]) else None,
                "timestamp": df["timestamp"].iloc[-1]}
    ema = df["close"].ewm(span=ema_p, adjust=False).mean()
    atr = calculate_atr(df, atr_p)
    adx = calculate_adx(df, adx_p).iloc[-1]
    slope = ema.diff().iloc[-1]
    z = (df["close"].iloc[-1] - ema.iloc[-1]) / atr.iloc[-1] if atr.iloc[-1] else np.nan
    recent_atr = atr.tail(atr_win).dropna()
    pct = (recent_atr <= atr.iloc[-1]).mean() * 100 if len(recent_atr) >= 20 and pd.notna(atr.iloc[-1]) else np.nan
    if pd.isna(adx) or pd.isna(ema.iloc[-1]):
        direction = "sin datos"
        strength = "sin datos"
    else:
        slope_threshold = 0.05 * atr.iloc[-1]
        if slope > slope_threshold:
            direction = "alcista"
        elif slope < -slope_threshold:
            direction = "bajista"
        else:
            direction = "lateral"
        if adx < adx_th:
            strength = "débil"
        elif adx > 25:
            strength = "fuerte"
        else:
            strength = "media"
    volatility = "baja vol" if pct < vol_low else "alta vol" if pct > vol_high else "normal vol"
    return {
        "direction": direction, "strength": strength, "volatility": volatility,
        "regime": "sin datos" if direction == "sin datos" else direction + " " + strength + " / " + volatility,
        "adx": float(adx) if pd.notna(adx) else None,
        "atr": float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else None,
        "atr_percentile": float(pct) if pd.notna(pct) else None,
        "ema": float(ema.iloc[-1]) if pd.notna(ema.iloc[-1]) else None,
        "close": float(df["close"].iloc[-1]) if pd.notna(df["close"].iloc[-1]) else None,
        "timestamp": df["timestamp"].iloc[-1],
    }
