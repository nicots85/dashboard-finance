"""
src/calc — Módulo de cálculos cuantitativos de dashboard-finance.
"""

from src.calc.regime import (
    calculate_atr,
    calculate_adx,
    compute_market_regime_history,
    get_latest_market_regime,
)
from src.calc.trends import compute_multi_timeframe_trends
from src.calc.zscore import compute_zscore_history, get_latest_zscore
from src.calc.cointegration import evaluate_pair_cointegration, align_pair_series
from src.calc.macro import analyze_fred_series

__all__ = [
    "calculate_atr",
    "calculate_adx",
    "compute_market_regime_history",
    "get_latest_market_regime",
    "compute_multi_timeframe_trends",
    "compute_zscore_history",
    "get_latest_zscore",
    "evaluate_pair_cointegration",
    "align_pair_series",
    "analyze_fred_series",
]
