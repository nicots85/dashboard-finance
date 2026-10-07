"""
trends.py — Matriz de Tendencias Multi-Temporalidad (Semáforo).
Evalúa la dirección (alcista / bajista / lateral) en 1m, 5m, 15m, 1h, 4h y 1D.
Mapea a color:
  - alcista -> verde (🟢)
  - bajista -> rojo (🔴)
  - lateral -> gris (⚪)
  - sin datos / insuficiente -> '-' (⚪)
"""

from typing import Dict, Any, List, Optional
import pandas as pd
from src.calc.regime import get_latest_market_regime
from src.data.four_hour import market_results, prepare_stored

ALL_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1D"]


def compute_multi_timeframe_trends(
    symbol: str,
    dfs_by_tf: Dict[str, pd.DataFrame],
    regime_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Dada una colección de DataFrames indexados por temporalidad para un activo,
    devuelve un resumen con la dirección y color del semáforo para cada temporalidad.
    """
    result = {
        "symbol": symbol,
        "trends": {},
        "colors": {},
    }

    color_map = {
        "alcista": "verde",
        "bajista": "rojo",
        "alcista (débil)": "verde claro",
        "bajista (débil)": "rojo claro",
        "lateral": "gris",
        "sin datos": "sin datos",
    }

    for tf in ALL_TIMEFRAMES:
        df = dfs_by_tf.get(tf)
        if df is None or df.empty or len(df) < 30:
            result["trends"][tf] = "sin datos"
            result["colors"][tf] = "gris"
        else:
            if tf == "4h":
                df = prepare_stored(df, symbol)
                df = df[df.closed]
            reg = market_results(df, {"regime": regime_config or {}})[0] if tf == "4h" else get_latest_market_regime(df, config=regime_config)
            direction = reg["direction"]
            result["trends"][tf] = direction
            result["colors"][tf] = color_map.get(direction, "gris")

    return result
