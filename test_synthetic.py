"""
test_synthetic.py — Pruebas automáticas con datos sintéticos conocidos.
Verifica:
 1. Tendencia alcista perfecta: genera velas crecientes constantes -> debe dar 'alcista'.
 2. Rango plano perfecto: genera velas oscilando en un canal estrecho -> debe dar 'lateral'.
 3. Z-score extremo: inyecta un salto de 4 desvíos -> debe marcar 'is_extreme = True'.
 4. Cointegración sintética: dos series ligadas por y = 2*x + e_estacionario -> debe dar 'is_cointegrated = True'.
"""

import sys
import numpy as np
import pandas as pd

from src.calc.regime import get_latest_market_regime
from src.calc.zscore import get_latest_zscore
from src.calc.cointegration import evaluate_pair_cointegration


def test_uptrend_synthetic():
    """Genera 200 velas con tendencia alcista perfecta constante."""
    dates = pd.date_range("2025-01-01", periods=200, freq="D", tz="UTC")
    closes = np.linspace(100, 300, 200)
    highs = closes + 2.0
    lows = closes - 2.0
    opens = closes - 0.5

    df = pd.DataFrame({
        "timestamp": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": 1000.0,
    })

    reg = get_latest_market_regime(df)
    assert reg["direction"] == "alcista", f"Fallo: se esperaba 'alcista', se obtuvo '{reg['direction']}'"
    print("✅ Test 1 (Tendencia alcista sintética): OK -> Clasificado como 'alcista'")


def test_lateral_synthetic():
    """Genera 200 velas oscilando en un rango plano muy estrecho con ruido blanco (sin tendencia)."""
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=200, freq="D", tz="UTC")
    # Serie plana con fluctuaciones aleatorias puras alrededor de 100
    closes = 100.0 + np.random.uniform(-0.1, 0.1, 200)
    highs = closes + np.random.uniform(0.1, 0.2, 200)
    lows = closes - np.random.uniform(0.1, 0.2, 200)
    opens = closes - np.random.uniform(-0.05, 0.05, 200)

    df = pd.DataFrame({
        "timestamp": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": 1000.0,
    })

    reg = get_latest_market_regime(df)
    assert reg["direction"] == "lateral", f"Fallo: se esperaba 'lateral', se obtuvo '{reg['direction']}'"
    print("✅ Test 2 (Rango lateral sintético): OK -> Clasificado como 'lateral'")


def test_zscore_extreme_synthetic():
    """Genera una serie estable y al final agrega un salto brusco hacia arriba."""
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=200, freq="D", tz="UTC")
    closes = 100.0 + np.random.normal(0, 0.5, 200)
    # Gran salto en la última vela
    closes[-1] = 120.0
    highs = closes + 0.5
    lows = closes - 0.5
    opens = closes - 0.1

    df = pd.DataFrame({
        "timestamp": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": 1000.0,
    })

    z = get_latest_zscore(df)
    assert z["is_extreme"] is True, f"Fallo: se esperaba is_extreme=True, se obtuvo {z['is_extreme']}"
    assert z["z_atr"] > 2.0, f"Fallo: se esperaba z_atr > 2.0, se obtuvo {z['z_atr']}"
    print(f"✅ Test 3 (Z-Score extremo sintético): OK -> z={z['z_atr']:.2f}, Extremo={z['is_extreme']}")


def test_cointegration_synthetic():
    """Genera dos series I(1) cointegradas por construcción (y = 1.5 * x + ruido_estacionario)."""
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=250, freq="D", tz="UTC")
    # Random walk para x
    steps = np.random.normal(0, 1, 250)
    x = 100.0 + np.cumsum(steps)
    # Ruido estacionario AR(1)
    stationary_noise = np.zeros(250)
    for t in range(1, 250):
        stationary_noise[t] = 0.5 * stationary_noise[t - 1] + np.random.normal(0, 0.5)

    y = 1.5 * x + stationary_noise

    df_x = pd.DataFrame({
        "timestamp": dates,
        "open": x,
        "high": x + 1,
        "low": x - 1,
        "close": x,
        "volume": 1000.0,
    })
    df_y = pd.DataFrame({
        "timestamp": dates,
        "open": y,
        "high": y + 1,
        "low": y - 1,
        "close": y,
        "volume": 1000.0,
    })

    res = evaluate_pair_cointegration(df_y, df_x)
    assert res["is_cointegrated"] is True, f"Fallo: se esperaba cointegrado=True, p={res['p_value']}"
    print(f"✅ Test 4 (Cointegración sintética): OK -> Cointegrado={res['is_cointegrated']}, p-valor={res['p_value']:.4f}, beta={res['beta']:.2f}")


def test_weak_trend_synthetic():
    """Serie plana con salto fuerte al final: ADX no reacciona -> 'alcista (débil)'."""
    np.random.seed(7)
    dates = pd.date_range("2025-01-01", periods=200, freq="D", tz="UTC")
    closes = 100.0 + np.random.uniform(-0.1, 0.1, 200)
    closes[-1] = 108.0  # salto brusco en la última vela
    highs = closes + np.random.uniform(0.1, 0.2, 200)
    lows = closes - np.random.uniform(0.1, 0.2, 200)
    opens = closes - np.random.uniform(-0.05, 0.05, 200)
    highs[-1] = closes[-1] + 0.2
    lows[-1] = closes[-1] - 0.5
    opens[-1] = closes[-2]

    df = pd.DataFrame({
        "timestamp": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": 1000.0,
    })

    reg = get_latest_market_regime(df)
    assert reg["direction"] == "alcista", f"Fallo: se esperaba 'alcista', se obtuvo '{reg['direction']}' (adx={reg['adx']})"
    assert reg["strength"] == "débil", f"Fallo: se esperaba 'débil', se obtuvo '{reg['strength']}' (adx={reg['adx']})"
    print(f"✅ Test 5 (Salto fuerte en serie plana): OK -> '{reg['direction']} {reg['strength']}' (ADX={reg['adx']:.1f})")


def main():
    print("\n" + "=" * 65)
    print("🧪 EJECUTANDO PRUEBAS AUTOMÁTICAS CON DATOS SINTÉTICOS")
    print("=" * 65)
    test_uptrend_synthetic()
    test_lateral_synthetic()
    test_zscore_extreme_synthetic()
    test_cointegration_synthetic()
    test_weak_trend_synthetic()
    print("=" * 65)
    print("🎯 TODAS LAS PRUEBAS SINTÉTICAS PASARON CON ÉXITO.\n")


if __name__ == "__main__":
    main()
