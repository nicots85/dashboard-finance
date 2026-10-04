#!/usr/bin/env python3
"""
app/main.py — Interfaz Streamlit de dashboard-finance.
Pestaña completa: ÍNDICES. Las demás secciones quedan "En construcción"
y reutilizan la misma función genérica render_seccion().

Correr:
  Mac/Linux:   streamlit run app/main.py
  Windows:     streamlit run app/main.py
"""

import os
import sys
import sqlite3
import subprocess
from datetime import datetime

import pandas as pd
import streamlit as st
import yaml
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.data import DatabaseManager  # noqa: E402
from src.calc import (  # noqa: E402
    compute_market_regime_history,
    compute_zscore_history,
    compute_multi_timeframe_trends,
)

DB_PATH = os.path.join(ROOT, "data", "finance.db")
ALL_TF = ["1m", "5m", "15m", "1h", "4h", "1D"]

EMOJI_MAP = {
    "alcista": "🟢",
    "bajista": "🔴",
    "alcista (débil)": "🟩",
    "bajista (débil)": "🟥",
    "lateral": "⚪",
    "sin datos": "▫️",
}

st.set_page_config(page_title="Dashboard Financiero", layout="wide")


# ----------------------------------------------------------------------
# Utilidades de configuración
# ----------------------------------------------------------------------
@st.cache_data(ttl=3600)
def cargar_configs():
    with open(os.path.join(ROOT, "config", "assets.yaml"), encoding="utf-8") as f:
        assets = yaml.safe_load(f)
    with open(os.path.join(ROOT, "config", "pairs.yaml"), encoding="utf-8") as f:
        pairs = yaml.safe_load(f)
    return assets, pairs


def query(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Datos cacheados
# ----------------------------------------------------------------------
@st.cache_data(ttl=900)
def obtener_semaforos(activos_key, activos):
    """Semáforo multi-temporalidad por activo (se cachea 15 min)."""
    db = DatabaseManager()
    out = {}
    for sym in activos:
        dfs = {}
        for tf in ALL_TF:
            df = db.load_candles(sym, tf)
            if not df.empty:
                dfs[tf] = df
        out[sym] = compute_multi_timeframe_trends(sym, dfs)
    return out


@st.cache_data(ttl=900)
def obtener_ultimos_calculos():
    """Última fila de régimen y z-score por (symbol, timeframe) desde SQLite."""
    reg = query(
        """SELECT r.* FROM calc_regimes r
           JOIN (SELECT symbol, timeframe, MAX(timestamp) AS mt
                 FROM calc_regimes GROUP BY symbol, timeframe) m
           ON r.symbol=m.symbol AND r.timeframe=m.timeframe AND r.timestamp=m.mt"""
    )
    z = query(
        """SELECT z.* FROM calc_zscores z
           JOIN (SELECT symbol, timeframe, MAX(timestamp) AS mt
                 FROM calc_zscores GROUP BY symbol, timeframe) m
           ON z.symbol=m.symbol AND z.timeframe=m.timeframe AND z.timestamp=m.mt"""
    )
    return reg, z


@st.cache_data(ttl=900)
def obtener_cointegracion(seccion, pares):
    rows = []
    for p in pares:
        key = f"{p['y']}/{p['x']}"
        df = query(
            """SELECT c.* FROM calc_cointegration c
               JOIN (SELECT pair, timeframe, MAX(timestamp) AS mt
                     FROM calc_cointegration GROUP BY pair, timeframe) m
               ON c.pair=m.pair AND c.timeframe=m.timeframe AND c.timestamp=m.mt
               WHERE c.pair = ?""",
            (key,),
        )
        for _, r in df.iterrows():
            rows.append({
                "Par": p.get("nombre", key),
                "TF": r["timeframe"],
                "Cointegrado": "✅ cointegrado" if r["is_cointegrated"] else "❌ no cointegrado",
                "p-valor": r["p_value"],
                "Beta": r["beta"],
                "Z-spread": f"{r['z_spread']:+.2f}" if (r["is_cointegrated"] and r["z_spread"] is not None) else "-",
                "Vida media (velas)": r["half_life"],
                "Estabilidad %": r["pct_coint_windows"],
            })
    return pd.DataFrame(rows)


@st.cache_data(ttl=900)
def obtener_macro():
    df = query(
        """SELECT m.* FROM calc_macro m
           JOIN (SELECT series_id, MAX(timestamp) AS mt FROM calc_macro GROUP BY series_id) mm
           ON m.series_id=mm.series_id AND m.timestamp=mm.mt"""
    )
    return df.set_index("series_id")


def ultima_actualizacion():
    try:
        df = query("SELECT MAX(updated_at) AS u FROM candles")
        return df["u"].iloc[0]
    except Exception:
        return None


# ----------------------------------------------------------------------
# Gráfico detallado
# ----------------------------------------------------------------------
@st.cache_data(ttl=900)
def obtener_historia(symbol, tf, limite=500):
    db = DatabaseManager()
    df = db.load_candles(symbol, tf)
    if df.empty:
        return df
    return df.tail(limite).reset_index(drop=True)


def grafico_detalle(symbol, tf):
    df = obtener_historia(symbol, tf)
    if df.empty or len(df) < 60:
        st.warning("No hay suficientes datos para este activo/temporalidad.")
        return
    hist = compute_market_regime_history(df)
    z = compute_zscore_history(df)

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3],
        vertical_spacing=0.05, subplot_titles=(f"{symbol} {tf} — precio y EMA 50", "Z-score (ATR)"),
    )

    # Fondo por régimen
    color_reg = {"alcista": "rgba(46,204,113,0.15)", "bajista": "rgba(231,76,60,0.15)",
                 "alcista (débil)": "rgba(46,204,113,0.08)", "bajista (débil)": "rgba(231,76,60,0.08)",
                 "lateral": "rgba(150,150,150,0.10)", "sin datos": "rgba(255,255,255,0)"}
    # relleno por tramos
    start = hist["timestamp"].iloc[0]
    prev = hist["direction"].iloc[0]
    for i in range(1, len(hist)):
        if hist["direction"].iloc[i] != prev or i == len(hist) - 1:
            fig.add_vrect(
                x0=start, x1=hist["timestamp"].iloc[i],
                fillcolor=color_reg.get(prev, "rgba(0,0,0,0)"), line_width=0, layer="below",
            )
            start = hist["timestamp"].iloc[i]
            prev = hist["direction"].iloc[i]

    fig.add_trace(go.Candlestick(
        x=df["timestamp"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name="Precio",
    ), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["timestamp"], y=hist["ema"], name="EMA 50",
                             line=dict(color="orange", width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["timestamp"], y=z["z_atr"], name="Z-score",
                             line=dict(color="purple", width=1.5)), row=2, col=1)
    for nivel in (2, -2):
        fig.add_hline(y=nivel, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=0, line_color="gray", row=2, col=1)
    fig.update_layout(height=650, xaxis_rangeslider_visible=False, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)


# ----------------------------------------------------------------------
# Pestaña genérica
# ----------------------------------------------------------------------
def render_seccion(seccion):
    """Función genérica: recibe el nombre de la sección y lee su configuración."""
    assets_cfg, pairs_cfg = cargar_configs()
    if seccion not in assets_cfg:
        st.info("Sección sin configuración.")
        return

    activos = assets_cfg[seccion].get("activos", [])
    pares = pairs_cfg.get(seccion, [])

    # a) Barra macro
    with st.spinner("Cargando referencias macro..."):
        macro = obtener_macro()
    if not macro.empty:
        st.subheader("Referencias macro")
        nombres = {"DGS10": "Tasa 10 años", "T10Y2Y": "Curva 10y-2y", "DFII10": "Tasa real 10y",
                   "VIXCLS": "VIX", "DTWEXBGS": "Dólar", "BAMLH0A0HYM2": "Spread HY"}
        cols = st.columns(min(len(macro), 7))
        for i, (sid, row) in enumerate(macro.iterrows()):
            with cols[i % len(cols)]:
                delta = f"{row['change_1m']:+.2f} ({row['pct_change_1m']:+.1f}%)"
                st.metric(nombres.get(sid, sid), f"{row['current_value']:.2f}", delta)
                st.caption(f"Percentil 10A: {row['percentile']:.0f}%")

    # b) Tabla principal
    st.subheader("Activos")
    with st.spinner("Calculando semáforos y leyendo resultados..."):
        semaforos = obtener_semaforos(",".join(activos), activos)
        reg, zdf = obtener_ultimos_calculos()

    filas = []
    for sym in activos:
        regs = reg[(reg.symbol == sym) & (reg.timeframe == "1D")]
        zs = zdf[(zdf.symbol == sym) & (zdf.timeframe == "1D")]
        sem = semaforos.get(sym, {}).get("trends", {})
        fila = {"Activo": sym}
        fila["Régimen (1D)"] = regs["regime"].iloc[0] if not regs.empty else "sin datos"
        for tf in ALL_TF:
            fila[tf] = EMOJI_MAP.get(sem.get(tf, "sin datos"), "▫️")
        fila["Z-ATR"] = zs["z_atr"].iloc[0] if not zs.empty else None
        fila["Z-desvío"] = zs["z_std"].iloc[0] if not zs.empty else None
        fila["Percentil Z"] = zs["percentile"].iloc[0] if not zs.empty else None
        filas.append(fila)

    df_tabla = pd.DataFrame(filas)

    def resaltar(val):
        try:
            return "background-color: #f8cbad" if abs(float(val)) > 2 else ""
        except (TypeError, ValueError):
            return ""

    styled = (
        df_tabla.style
        .map(resaltar, subset=["Z-ATR", "Z-desvío"])
        .format({"Z-ATR": "{:+.2f}", "Z-desvío": "{:+.2f}", "Percentil Z": "{:.0f}%"}, na_rep="-")
    )
    st.dataframe(styled, use_container_width=True)
    st.caption("▫️ = sin datos (la fuente gratuita no tiene historia para ese activo/temporalidad; para índices, los intradía son cortos: 1m ≈ 7 días, 5m/15m ≈ 60 días).")

    # c) Cointegración
    st.subheader("Cointegración de pares")
    coint = obtener_cointegracion(seccion, pares)
    if coint.empty:
        st.info("Sin resultados de cointegración guardados aún.")
    else:
        st.dataframe(
            coint.style.format({"p-valor": "{:.4f}", "Beta": "{:.2f}",
                                "Vida media (velas)": "{:.1f}", "Estabilidad %": "{:.0f}%"}, na_rep="-"),
            use_container_width=True,
        )

    # d) Detalle por activo
    st.subheader("Detalle por activo")
    c1, c2 = st.columns(2)
    with c1:
        sym_sel = st.selectbox("Activo", activos)
    with c2:
        tf_sel = st.selectbox("Temporalidad", ALL_TF, index=ALL_TF.index("1D"))
    with st.spinner("Armando gráfico..."):
        grafico_detalle(sym_sel, tf_sel)

    # f) Fecha de actualización
    st.caption(f"Última actualización de datos: {ultima_actualizacion()}")


def render_en_construccion():
    st.info("En construcción")


# ----------------------------------------------------------------------
# App principal
# ----------------------------------------------------------------------
def main():
    st.title("📊 Dashboard Financiero")

    # Botón actualizar
    if st.button("🔄 Actualizar datos"):
        prog = st.progress(0, text="Descargando datos...")
        subprocess.run([sys.executable, "update_data.py"], cwd=ROOT, check=False)
        prog.progress(50, text="Calculando régimen, z-score y cointegración...")
        subprocess.run([sys.executable, "run_calc.py"], cwd=ROOT, check=False)
        prog.progress(100, text="¡Listo!")
        st.cache_data.clear()
        st.success("Datos actualizados.")

    tabs = st.tabs(["Índices", "Metales", "Equity", "Small caps", "Cripto", "Argentina"])
    with tabs[0]:
        render_seccion("indices")
    with tabs[1]:
        render_en_construccion()
    with tabs[2]:
        render_en_construccion()
    with tabs[3]:
        render_en_construccion()
    with tabs[4]:
        render_en_construccion()
    with tabs[5]:
        render_en_construccion()

    with st.expander("Cómo leer esto"):
        st.markdown(
            """
- **Z-score alto (|z| > 2)** indica que el precio está *estirado* respecto a su promedio,
  **no** una señal de reversión: en tendencias fuertes puede persistir varios días.
- **Régimen "(débil)"**: la tendencia es clara por momentum pero el ADX todavía no la confirma.
  Tomarla con más cautela que una tendencia fuerte.
- **Cointegración**: que dos activos se muevan juntos hoy no garantiza que sigan haciéndolo;
  puede romperse. La columna *Estabilidad* muestra qué tan frecuente fue cointegrado.
- **Vida media**: velas promedio que tarda el spread en volver a la media.
- **Datos gratuitos**: yfinance y Binance tienen retraso de minutos; la intradía corta (1m, 5m, 15m)
  solo cubre un historial limitado.
- **Intradía de índices**: Yahoo solo guarda poco historial (1m ~7 días, 5m/15m ~60 días), por eso
  las columnas intradía del semáforo son menos profundas que el 1D.
- **ADX < 20**: no hay tendencia definida, solo ruido; el sistema lo marca como "lateral".
"""
        )


if __name__ == "__main__":
    main()
