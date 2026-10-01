"""
generate_charts.py — Genera los gráficos PNG de verificación para ^NDX y BTC/USDT en 1D:
 1. Precio + EMA 50 + sombreado de fondo según el régimen de mercado (verde=alcista, rojo=bajista, gris=lateral).
 2. Z-Score normalizado por ATR + líneas de advertencia extrema (+2 y -2).
Se guardan en la carpeta output/.
"""

import os
import matplotlib
matplotlib.use("Agg")  # Backend no interactivo para guardar imágenes limpias
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np

from src.data import DatabaseManager
from src.calc.regime import compute_market_regime_history
from src.calc.zscore import compute_zscore_history


def plot_regime_and_zscore(symbol: str, output_name: str, db: DatabaseManager, last_n_bars: int = 250):
    """Genera dos gráficos: 1) Precio con régimen coloreado, 2) Z-score con umbrales."""
    df = db.load_candles(symbol, "1D")
    if df.empty or len(df) < 50:
        print(f"⚠️  No hay suficientes datos para graficar {symbol}")
        return

    # Cálculos históricos
    df_reg = compute_market_regime_history(df)
    df_z = compute_zscore_history(df)

    # Filtrar últimas N velas para que el gráfico sea nítido y legible
    sub_reg = df_reg.tail(last_n_bars).copy().reset_index(drop=True)
    sub_z = df_z.tail(last_n_bars).copy().reset_index(drop=True)

    dates = pd.to_datetime(sub_reg["timestamp"])

    # -------------------------------------------------------------
    # Gráfico 1: Precio + EMA + Sombreado de Régimen
    # -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(12, 6), dpi=150)
    fig.patch.set_facecolor("#121212")
    ax.set_facecolor("#181818")

    # Línea de precio y EMA
    ax.plot(dates, sub_reg["close"], label="Precio de Cierre", color="#E0E0E0", linewidth=1.5)
    ax.plot(dates, sub_reg["ema"], label="EMA 50", color="#FFB300", linewidth=1.8, linestyle="--")

    # Pintar zonas de fondo según el régimen
    # alcista -> verde tenue (#1b5e20), bajista -> rojo tenue (#b71c1c), lateral -> gris (#424242)
    color_map = {
        "alcista": "#2e7d32",
        "bajista": "#c62828",
        "lateral": "#616161",
    }

    # Sombreado continuo
    for i in range(len(sub_reg) - 1):
        direction = sub_reg.loc[i, "direction"]
        c = color_map.get(direction, "#616161")
        d_start = dates.iloc[i]
        d_end = dates.iloc[i + 1]
        ax.axvspan(d_start, d_end, color=c, alpha=0.18, linewidth=0)

    ax.set_title(f"{symbol} (1D) — Régimen de Mercado (EMA 50 + ADX 14)", color="#FFFFFF", fontsize=14, pad=12, fontweight="bold")
    ax.set_xlabel("Fecha (UTC)", color="#CCCCCC", fontsize=10)
    ax.set_ylabel("Precio", color="#CCCCCC", fontsize=10)
    ax.tick_params(colors="#CCCCCC")
    ax.grid(True, color="#2C2C2C", linestyle=":", alpha=0.7)
    ax.legend(facecolor="#222222", edgecolor="#444444", labelcolor="#FFFFFF", loc="upper left")

    # Formatear eje X
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))

    out_reg_path = os.path.join("output", f"{output_name}_regime_1d.png")
    plt.tight_layout()
    plt.savefig(out_reg_path, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()
    print(f"📊 Gráfico de régimen guardado: {out_reg_path}")

    # -------------------------------------------------------------
    # Gráfico 2: Z-Score (Dispersión por ATR) + Umbrales +/- 2
    # -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(12, 5), dpi=150)
    fig.patch.set_facecolor("#121212")
    ax.set_facecolor("#181818")

    z_vals = sub_z["z_atr"]
    ax.plot(dates, z_vals, label="Z-Score (ATR)", color="#29B6F6", linewidth=1.5)

    # Líneas de umbral
    ax.axhline(0, color="#757575", linestyle="-", linewidth=1, alpha=0.8)
    ax.axhline(2.0, color="#EF5350", linestyle="--", linewidth=1.2, label="Zona Sobrecompra (+2.0)")
    ax.axhline(-2.0, color="#66BB6A", linestyle="--", linewidth=1.2, label="Zona Sobreventa (-2.0)")

    # Resaltar puntos extremos
    extremes = sub_z[sub_z["is_extreme"]]
    if not extremes.empty:
        ex_dates = pd.to_datetime(extremes["timestamp"])
        ax.scatter(ex_dates, extremes["z_atr"], color="#FF5252", s=40, zorder=5, label="Extremo (|z| > 2)")

    ax.set_title(f"{symbol} (1D) — Dispersión Normalizada por Volatilidad (Z-Score ATR)", color="#FFFFFF", fontsize=14, pad=12, fontweight="bold")
    ax.set_xlabel("Fecha (UTC)", color="#CCCCCC", fontsize=10)
    ax.set_ylabel("Z-Score", color="#CCCCCC", fontsize=10)
    ax.tick_params(colors="#CCCCCC")
    ax.grid(True, color="#2C2C2C", linestyle=":", alpha=0.7)
    ax.legend(facecolor="#222222", edgecolor="#444444", labelcolor="#FFFFFF", loc="upper left")

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))

    out_z_path = os.path.join("output", f"{output_name}_zscore_1d.png")
    plt.tight_layout()
    plt.savefig(out_z_path, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()
    print(f"📊 Gráfico de z-score guardado: {out_z_path}")


def main():
    print("\n" + "=" * 65)
    print("📈 GENERANDO GRÁFICOS PNG DE VERIFICACIÓN EN output/")
    print("=" * 65)

    db = DatabaseManager()

    # 1. Nasdaq 100 (^NDX)
    plot_regime_and_zscore("^NDX", "ndx", db, last_n_bars=300)

    # 2. Bitcoin (BTC/USDT)
    plot_regime_and_zscore("BTC/USDT", "btc", db, last_n_bars=300)

    print("=" * 65)
    print("✅ Todos los gráficos fueron generados con éxito en la carpeta output/.\n")


if __name__ == "__main__":
    main()
