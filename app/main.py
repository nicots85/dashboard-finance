#!/usr/bin/env python3
"""
app/main.py — Interfaz Streamlit de dashboard-finance.
Las seis pestañas reutilizan render_seccion(). C1 agrega nombres y ayudas,
conservando el diseño, los datos y los cálculos.

Correr:
  Mac/Linux:   streamlit run app/main.py
  Windows:     streamlit run app/main.py
"""

import os
import sys
import sqlite3
import subprocess
import json
from datetime import datetime

import pandas as pd
import streamlit as st
import yaml
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.data import DatabaseManager  # noqa: E402
from src.data.db_manager import DEFAULT_DB_PATH  # noqa: E402
from src.data.four_hour import series_descriptor, sufficient_history, prepare_stored  # noqa: E402
from src.presentation import (  # noqa: E402
    asset_label, pair_label, entity_label, definition, help_text,
    explain_symbols, rich_text, section_terms, column_specs, TF_LABELS, refresh_catalog,
)
from app.indices import render_section_pilot  # noqa: E402
from src.calc import (  # noqa: E402
    compute_market_regime_history,
    compute_zscore_history,
    compute_multi_timeframe_trends,
)

DB_PATH = DEFAULT_DB_PATH
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

SECTION_MACRO = {
    "indices": ["DGS10", "T10Y2Y", "DFII10", "VIXCLS", "DTWEXBGS", "BAMLH0A0HYM2"],
    "metales": ["DFII10", "DTWEXBGS"],
    "equity": ["DGS10", "T10Y2Y", "BAMLH0A0HYM2"],
    "smallcaps": ["DGS10", "BAMLH0A0HYM2"],
    "cripto": ["DTWEXBGS", "VIXCLS"],
    "argentina": ["DTWEXBGS"],
}

NOTAS_BASE = """
- **La dirección se detecta mejor en subas que en caídas:** en caídas históricas conocidas, la herramienta marcó como bajista entre 37% y 56% de las velas. Un 'lateral' o 'alcista débil' en medio de una caída no es un error.
- **Precio lejos de su promedio:** no significa que vaya a volver pronto. Una suba o baja fuerte puede mantenerlo lejos varios días.
- **Dirección débil:** el precio está muy separado de su promedio, pero la medida de fuerza todavía no confirma una tendencia fuerte.
- **Colores:** verde significa dirección de suba; rojo, de baja; gris, lateral. El cuadrado pequeño significa que faltan datos. Ninguno es una orden de compra o venta.
- **Dos activos relacionados:** que hayan conservado una relación en el período estudiado no asegura que siga funcionando.
- **Fecha del dato:** las fuentes gratuitas pueden llegar con retraso. Compará siempre el último dato usado con la fecha de tu plataforma.
"""

NOTAS_SECCION = {
    "indices": NOTAS_BASE + "\n- **Historia corta:** Yahoo entrega aproximadamente siete días de velas de un minuto y sesenta días de cinco o quince minutos. Lo ya guardado se conserva.",
    "metales": NOTAS_BASE + "\n- **Oro frente a plata:** si el cociente sube, el oro gana terreno frente a la plata. Es una comparación entre ambos, no una señal automática.\n- **Contratos:** Yahoo une futuros; no se pudo verificar cómo ajusta sus cambios de contrato.",
    "cripto": NOTAS_BASE + "\n- **Todos los días:** las criptos cotizan también los fines de semana; un dato antiguo se marca aunque sea sábado o domingo.\n- **Comparación con Bitcoin:** si sube el cociente de Ethereum o Solana frente a Bitcoin, la primera gana terreno relativo. No es la participación en el valor total del mercado.",
    "equity": NOTAS_BASE + "\n- **Mapa de colores:** muestra separación del promedio. Un valor alto no significa por sí solo que sea el mejor sector para comprar.",
    "smallcaps": NOTAS_BASE + "\n- **Pequeñas frente a grandes empresas:** un cociente creciente del fondo de pequeñas empresas frente al S&P 500 indica mejor desempeño relativo del primero.",
    "argentina": NOTAS_BASE + "\n- **Dólar implícito:** depende de los precios de la acción local y su certificado estadounidense; los horarios de Buenos Aires y Nueva York no coinciden por completo.\n- **El CCL tiene tendencia:** un valor alto de distancia a su media indica que subió rápido, no que vaya a bajar.",
}


def caption_help(text):
    st.caption(rich_text(explain_symbols(text)), unsafe_allow_html=True)


def dataframe_help(data, context=None, **kwargs):
    """Todos los encabezados pasan por el mismo catálogo de ayudas."""
    columns = data.columns if isinstance(data, pd.DataFrame) else data.data.columns
    config = {key: st.column_config.Column(**spec) for key, spec in column_specs(columns, context).items()}
    return st.dataframe(data, column_config=config, **kwargs)


def metric_help(label, value, delta=None, terms=()):
    return st.metric(label, value, delta, help=help_text(*terms))


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
    if os.path.exists(DB_PATH + ".restore-lock"):
        raise RuntimeError("La base se está restaurando. Esperá a que termine antes de abrir el tablero.")
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
    """Misma versión guardada que la tabla; los avisos indican si falta recalcular."""
    reg, _ = obtener_ultimos_calculos()
    out = {}
    for sym in activos:
        trends = {}
        for tf in ALL_TF:
            rows = reg[(reg.symbol == sym) & (reg.timeframe == tf)]
            trends[tf] = rows["direction"].iloc[0] if not rows.empty and rows["calc_status"].iloc[0] != "no_calculable" else "sin datos"
        out[sym] = {"trends": trends}
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
            calculable = r["calc_status"] != "no_calculable" and pd.notna(r["p_value"])
            rows.append({
                "Par": f"{asset_label(p['y'], r['timeframe'])} / {asset_label(p['x'], r['timeframe'])}",
                "TF": TF_LABELS[r["timeframe"]],
                "Cointegrado": "No calculable" if not calculable else "✅ cointegrado" if r["is_cointegrated"] else "❌ no cointegrado",
                "p-valor": r["p_value"],
                "Beta": r["beta"],
                "Z-spread": f"{r['z_spread']:+.2f}" if (calculable and r["is_cointegrated"] and pd.notna(r["z_spread"])) else "-",
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


@st.cache_data(ttl=900)
def obtener_fuentes():
    df = query("SELECT symbol, source, MAX(timestamp) AS mt FROM candles GROUP BY symbol, source")
    df = df.sort_values("mt").drop_duplicates("symbol", keep="last")
    return dict(zip(df["symbol"], df["source"]))


TF_MINUTOS = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1D": 1440}


def ventana_conjunta(fecha=None):
    """Ventana común BYMA–NYSE calculada con zonas horarias reales (se ajusta al cambio de DST de EE.UU.)."""
    from zoneinfo import ZoneInfo

    art = ZoneInfo("America/Argentina/Buenos_Aires")
    ny = ZoneInfo("America/New_York")
    if fecha is None:
        fecha = pd.Timestamp.now(tz="UTC")

    # Horarios locales de cada mercado
    byma = (pd.Timestamp("11:00").time(), pd.Timestamp("17:00").time())
    nyse = (pd.Timestamp("9:30").time(), pd.Timestamp("16:00").time())

    dia = pd.Timestamp(fecha).normalize()
    b_ini = pd.Timestamp.combine(dia.date(), byma[0]).tz_localize(art)
    b_fin = pd.Timestamp.combine(dia.date(), byma[1]).tz_localize(art)
    n_ini = pd.Timestamp.combine(dia.date(), nyse[0]).tz_localize(ny)
    n_fin = pd.Timestamp.combine(dia.date(), nyse[1]).tz_localize(ny)

    ini = max(b_ini, n_ini)
    fin = min(b_fin, n_fin)
    if ini >= fin:
        return "sin solape hoy (usar cierre 1D)"
    return (
        f"{ini.tz_convert(art).strftime('%H:%M')}–{fin.tz_convert(art).strftime('%H:%M')} ART "
        f"({ini.tz_convert(ny).strftime('%H:%M')}–{fin.tz_convert(ny).strftime('%H:%M')} NY)"
    )


def antiguedad(symbol, tf, ahora, seccion):
    """Texto 'hace X' con ⚠ si está más viejo de lo esperado; para cripto no se marca fin de semana."""
    try:
        df = query(
            "SELECT MAX(timestamp) AS mt FROM candles WHERE symbol=? AND timeframe=?", (symbol, tf)
        )
        mt = df["mt"].iloc[0]
        if mt is None or (isinstance(mt, float) and pd.isna(mt)):
            return "-"
        mt = pd.to_datetime(mt, utc=True)
        delta = ahora - mt
        minutos = delta.total_seconds() / 60

        # fin de semana: para activos de mercados (no cripto), la última vela es del viernes
        es_cripto = seccion == "cripto"
        umbral = TF_MINUTOS[tf] * 3 + 5
        if not es_cripto:
            if ahora.dayofweek >= 5:  # sábado/domingo
                return f"hace {_fmt_edad(minutos)} (finde)"
            if mt.dayofweek == 4 and ahora.dayofweek == 0:
                return f"hace {_fmt_edad(minutos)} (finde)"

        if minutos > umbral:
            return f"⚠ hace {_fmt_edad(minutos)}"
        return f"hace {_fmt_edad(minutos)}"
    except Exception:
        return "-"


def _fmt_edad(minutos):
    if minutos < 60:
        return f"{int(minutos)} min"
    if minutos < 60 * 48:
        return f"{int(minutos // 60)} h"
    return f"{int(minutos // 1440)} d"


@st.cache_data(ttl=900)
def ratio_zscore(y, x, tf="1D"):
    """Z-score y percentil del ratio y/x (ej: Oro/Plata, ETH/BTC)."""
    from src.calc.zscore import get_latest_zscore

    db = DatabaseManager()
    dy = db.load_candles(y, tf)
    dx = db.load_candles(x, tf)
    if dy.empty or dx.empty:
        return None
    m = pd.concat(
        [dy.set_index("timestamp")["close"].rename("cy"), dx.set_index("timestamp")["close"].rename("cx")],
        axis=1, join="inner",
    ).dropna()
    if len(m) < 60:
        return None
    ratio = m["cy"] / m["cx"]
    df = pd.DataFrame({"timestamp": ratio.index, "open": ratio.values, "high": ratio.values,
                       "low": ratio.values, "close": ratio.values, "volume": 0.0})
    z = get_latest_zscore(df)
    return {"ratio": float(ratio.iloc[-1]), "z_atr": z["z_atr"], "percentile": z["z_percentile"]}


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
    if tf == "4h":
        with DatabaseManager(DB_PATH)._get_connection() as conn:
            descriptor = series_descriptor(symbol, conn)
        st.caption(asset_label(symbol, tf) + " · " + descriptor["label"])
    df = obtener_historia(symbol, tf)
    if df.empty or len(df) < 60:
        st.warning("No hay suficientes datos para este activo/temporalidad.")
        return
    hist = compute_market_regime_history(df)
    z = compute_zscore_history(df)
    if tf == "4h":
        with open(os.path.join(ROOT, "config/calc.yaml"), encoding="utf-8") as f:
            config = yaml.safe_load(f)
        enough, required = sufficient_history(df, config)
        if not enough:
            st.warning(f"Historia insuficiente en 4h: {len(df)} velas; se requieren {required}. No se muestra una etiqueta de régimen dudosa.")
            hist["direction"] = "sin datos"
            z["z_atr"] = float("nan")

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3],
        vertical_spacing=0.05, subplot_titles=(f"{asset_label(symbol, tf)} — {TF_LABELS[tf]}: precio y EMA de 50 velas", "Z-score: distancia a la media por ATR"),
    )
    fig.layout.annotations[0].hovertext = help_text(symbol, tf, "EMA")
    fig.layout.annotations[1].hovertext = help_text("z-score", "ATR")

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
        name=asset_label(symbol, tf), hoverinfo="text",
        hovertext=[f"{asset_label(symbol, tf)}<br>{row.timestamp}<br>Apertura: {row.open:,.2f}<br>Máximo: {row.high:,.2f}<br>Mínimo: {row.low:,.2f}<br>Cierre: {row.close:,.2f}" for row in df.itertuples()],
    ), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["timestamp"], y=hist["ema"], name="EMA 50",
                             line=dict(color="orange", width=1.5),
                             hovertemplate="Media exponencial (EMA) de 50 velas: %{y:,.2f}<br>" + definition("EMA") + "<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["timestamp"], y=z["z_atr"], name="Z-score",
                             line=dict(color="purple", width=1.5),
                             hovertemplate="Distancia a la media: %{y:+.2f} rangos habituales (ATR)<br>" + definition("z-score") + "<extra></extra>"), row=2, col=1)
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

    # a) Barra macro (relevante a la sección)
    with st.spinner("Cargando referencias macro..."):
        macro = obtener_macro()
    macro_ids = SECTION_MACRO.get(seccion, [])
    if not macro.empty:
        if macro_ids:
            macro = macro[macro.index.isin(macro_ids)]
        st.subheader("Referencias económicas", help=help_text("FRED", "cambio a un mes", "percentil"))
        cols = st.columns(min(len(macro), 7))
        for i, (sid, row) in enumerate(macro.iterrows()):
            with cols[i % len(cols)]:
                delta = f"{row['change_1m']:+.2f} ({row['pct_change_1m']:+.1f}%)"
                metric_help(asset_label(sid), f"{row['current_value']:.2f}", delta, terms=(sid, "cambio a un mes", "percentil"))
                caption_help(f"Percentil histórico (hasta 10 años): {row['percentile']:.0f}%")

    # b) Tabla principal
    st.subheader("Activos")
    with st.spinner("Calculando semáforos y leyendo resultados..."):
        semaforos = obtener_semaforos(",".join(activos), activos)
        reg, zdf = obtener_ultimos_calculos()
        fuentes = obtener_fuentes()

    filas = []
    filas_edad = []
    ahora = pd.Timestamp.now(tz="UTC")
    for sym in activos:
        regs = reg[(reg.symbol == sym) & (reg.timeframe == "1D")]
        zs = zdf[(zdf.symbol == sym) & (zdf.timeframe == "1D")]
        sem = semaforos.get(sym, {}).get("trends", {})
        fila = {"Activo": asset_label(sym), "Fuente": fuentes.get(sym, "-")}
        fila["Régimen (1D)"] = regs["regime"].iloc[0] if not regs.empty else "sin datos"
        edad_fila = {"Activo": asset_label(sym)}
        for tf in ALL_TF:
            fila[tf] = EMOJI_MAP.get(sem.get(tf, "sin datos"), "▫️")
            edad_fila[tf] = antiguedad(sym, tf, ahora, seccion)
        fila["Z-ATR"] = zs["z_atr"].iloc[0] if not zs.empty else None
        fila["Z-desvío"] = zs["z_std"].iloc[0] if not zs.empty else None
        fila["Percentil Z"] = zs["percentile"].iloc[0] if not zs.empty else None
        filas.append(fila)
        filas_edad.append(edad_fila)

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
    dataframe_help(styled, use_container_width=True)
    caption_help("▫️ = sin datos: la fuente no entrega suficiente historia para calcular ese activo en esa temporalidad.")

    # Antigüedad del dato por temporalidad (amarillo = desactualizado)
    caption_help("Antigüedad del dato por temporalidad (amarillo = desactualizado):")
    df_edad = pd.DataFrame(filas_edad)

    def viejo(v):
        return "background-color: #fff3b0" if v and v.startswith("⚠") else ""

    dataframe_help(df_edad.style.map(viejo), context="age", use_container_width=True, hide_index=True)
    with st.expander("Método y versión de la 4h"):
        with DatabaseManager(DB_PATH)._get_connection() as conn:
            for symbol in activos:
                descriptor = series_descriptor(symbol, conn)
                st.write(asset_label(symbol, "4h") + " · " + descriptor["label"] + " · " + descriptor["version"])

    # c) Cointegración / CCL implícito (según sección)
    if seccion == "argentina":
        st.subheader("Dólar implícito por empresa (CCL)", help=help_text("CCL", "CCL implícito", "ADR"))
        pares_cfg = assets_cfg[seccion].get("pares", [])
        equiv = assets_cfg[seccion].get("equivalencias", {})
        mostrar_ccl(pares_cfg, equiv)
    else:
        st.subheader("Cointegración de pares", help=help_text("cointegración", "par"))
        if pares:
            coint = obtener_cointegracion(seccion, pares)
            if coint.empty:
                st.info("Sin resultados de cointegración guardados aún.")
            else:
                dataframe_help(
                    coint.style.format({"p-valor": "{:.4f}", "Beta": "{:.2f}",
                                        "Vida media (velas)": "{:.1f}", "Estabilidad %": "{:.0f}%"}, na_rep="-"),
                    use_container_width=True,
                )

    # c.b) Ratios con z-score (según sección)
    if seccion == "metales":
        st.subheader("Ratio: " + pair_label("GC=F", "SI=F"), help=help_text("ratio", "GC=F", "SI=F"))
        r = ratio_zscore("GC=F", "SI=F")
        mostrar_ratio(r, pair_label("GC=F", "SI=F"), ("GC=F", "SI=F"))
    elif seccion == "cripto":
        st.subheader("Comparación relativa frente a Bitcoin (BTC/USDT)", help=help_text("ratio", "BTC/USDT"))
        c1, c2 = st.columns(2)
        with c1:
            mostrar_ratio(ratio_zscore("ETH/USDT", "BTC/USDT"), pair_label("ETH/USDT", "BTC/USDT"), ("ETH/USDT", "BTC/USDT"))
        with c2:
            mostrar_ratio(ratio_zscore("SOL/USDT", "BTC/USDT"), pair_label("SOL/USDT", "BTC/USDT"), ("SOL/USDT", "BTC/USDT"))
    elif seccion == "smallcaps":
        st.subheader("Fuerza relativa: " + pair_label("IWM", "^GSPC"), help=help_text("fuerza relativa", "IWM", "^GSPC"))
        mostrar_ratio(ratio_zscore("IWM", "^GSPC"), pair_label("IWM", "^GSPC"), ("IWM", "^GSPC"))
    elif seccion == "equity":
        st.subheader("Mapa de colores: z-score por rango (ATR)", help=help_text("z-score", "ATR", "temporalidad"))
        z_rows = []
        for sym in activos:
            fila = {"Activo": asset_label(sym)}
            for tf in ALL_TF:
                zz = zdf[(zdf.symbol == sym) & (zdf.timeframe == tf)]
                fila[tf] = float(zz["z_atr"].iloc[0]) if not zz.empty else None
            z_rows.append(fila)
        df_heat = pd.DataFrame(z_rows).set_index("Activo")
        # ordenar por z de 1D (líder arriba)
        df_heat = df_heat.sort_values("1D", ascending=False, na_position="last")
        import plotly.express as px

        fig = px.imshow(
            df_heat.astype(float),
            color_continuous_scale="RdYlGn",
            color_continuous_midpoint=0,
            aspect="auto",
            labels=dict(color="Z-ATR"),
        )
        fig.update_layout(height=max(300, 28 * len(df_heat)))
        fig.update_traces(hovertemplate="%{y}<br>Temporalidad: %{x}<br>Distancia: %{z:+.2f} rangos habituales (ATR)<br>" + definition("z-score") + "<extra></extra>")
        fig.update_xaxes(tickvals=ALL_TF, ticktext=[TF_LABELS[tf] for tf in ALL_TF])
        st.plotly_chart(fig, use_container_width=True)
        caption_help("Verde = precio por encima de su media; rojo = por debajo. No equivale a una recomendación. El orden usa la distancia del día.")

    # d) Detalle por activo
    st.subheader("Detalle por activo")
    c1, c2 = st.columns(2)
    with c1:
        sym_sel = st.selectbox("Activo", activos, format_func=asset_label, help=help_text("activo", *activos), key=f"sym_{seccion}")
    with c2:
        tf_sel = st.selectbox("Temporalidad", ALL_TF, format_func=lambda tf: TF_LABELS[tf], help=help_text("temporalidad", *ALL_TF), index=ALL_TF.index("1D"), key=f"tf_{seccion}")
    with st.spinner("Armando gráfico..."):
        grafico_detalle(sym_sel, tf_sel)

    # f) Fecha de actualización
    caption_help(f"Última recepción guardada de datos (UTC): {ultima_actualizacion()}")
    with st.expander("Fechas de cálculo y datos usados"):
        pair_keys = {f"{p['y']}/{p['x']}" for p in pares}
        keys = set(activos) | pair_keys | set(SECTION_MACRO.get(seccion, []))
        health = [h for h in st.session_state.get("calculation_health", []) if h["asset"] in keys]
        if health:
            names = {"asset": "Activo o par", "timeframe": "Temporalidad", "calculated_at": "Calculado (UTC)",
                     "last_data_timestamp": "Último dato usado (UTC)", "status": "Estado", "reason": "Aviso"}
            dates = pd.DataFrame(health).drop(columns=["table"]).rename(columns=names)
            dates["Activo o par"] = dates["Activo o par"].map(entity_label)
            for i, item in enumerate(health):
                if item["timeframe"] == "4h" and item["asset"] in activos:
                    dates.loc[dates.index[i], "Activo o par"] = asset_label(item["asset"], "4h")
            dates["Temporalidad"] = dates["Temporalidad"].map(TF_LABELS)
            dates["Estado"] = dates["Estado"].map({"ok": "Comprobado", "stale": "Desactualizado",
                "untracked": "Recalcular para comprobar", "no_calculable": "No calculable"})
            dataframe_help(dates, use_container_width=True, hide_index=True)

    # g) Cómo leer esto (adaptado a la sección)
    with st.expander("Cómo leer esto"):
        st.markdown(rich_text(NOTAS_SECCION.get(seccion, NOTAS_BASE)), unsafe_allow_html=True)
    with st.expander("Glosario"):
        for term in section_terms(seccion, SECTION_MACRO.get(seccion, [])):
            try:
                label = asset_label(term)
            except KeyError:
                label = term
            st.markdown("**" + rich_text(label) + "** — " + rich_text(definition(term)), unsafe_allow_html=True)


@st.cache_data(ttl=900)
def ccl_serie(local, adr, ratio, tf):
    """CCL implícito = precio_local * ratio / precio_ADR, alineado por timestamp."""
    db = DatabaseManager()
    dl = db.load_candles(local, tf)
    da = db.load_candles(adr, tf)
    if dl.empty or da.empty:
        return pd.Series(dtype=float)
    if tf == "1D":
        a = dl.set_index(dl["timestamp"].dt.date)["close"].sort_index()
        b = da.set_index(da["timestamp"].dt.date)["close"].sort_index()
        idx = a.index.intersection(b.index)
        return (a.loc[idx] * ratio / b.loc[idx]).sort_index()
    a = dl.set_index("timestamp")["close"].sort_index()
    b = da.set_index("timestamp")["close"].sort_index()
    idx = a.index.intersection(b.index)
    return (a.loc[idx] * ratio / b.loc[idx]).sort_index()


def mostrar_ccl(pares_cfg, equiv):
    """Tabla de CCL por empresa + mediana con z-score y percentil; dispersión destacada."""
    ccl_1d = {}
    for p in pares_cfg:
        adr_sym = p["adr"]
        ratio = equiv.get(adr_sym.split("/")[0]) or equiv.get(adr_sym)
        s = ccl_serie(p["local"], p["adr"], ratio, "1D") if ratio else pd.Series(dtype=float)
        ccl_1d[p["nombre"]] = s

    hoy = max((s.index.max() for s in ccl_1d.values() if not s.empty), default=None)
    filas = []
    serie_hoy = []
    for p in pares_cfg:
        s = ccl_1d.get(p["nombre"], pd.Series(dtype=float))
        val = float(s.loc[hoy]) if hoy in s.index else (float(s.iloc[-1]) if not s.empty else None)
        serie_hoy.append(val)
        filas.append({"Empresa": asset_label(p["local"]), "Local": asset_label(p["local"]), "ADR": asset_label(p["adr"]),
                      "Equiv.": equiv.get(p["adr"]), "CCL implícito": val})

    df = pd.DataFrame(filas)
    mediana = float(pd.Series(serie_hoy).median()) if serie_hoy else None
    if mediana:
        df["% vs mediana"] = df["CCL implícito"].apply(lambda v: (v / mediana - 1) * 100 if v else None)
    styled = df.style.format({"CCL implícito": "{:,.1f}", "% vs mediana": "{:+.1f}%"}, na_rep="-")

    def lejos(v):
        try:
            return "background-color: #f8cbad" if abs(float(v)) > 5 else ""
        except (TypeError, ValueError):
            return ""

    styled = styled.map(lejos, subset=["% vs mediana"])
    dataframe_help(styled, use_container_width=True)

    # Mediana histórica + z-score
    series = [s.rename(k) for k, s in ccl_1d.items() if not s.empty]
    if series:
        med = pd.concat(series, axis=1).median(axis=1).dropna()
        med = med.sort_index()
        med.index = pd.to_datetime(med.index, utc=True)
        if len(med) > 60:
            from src.calc.zscore import get_latest_zscore

            dfp = pd.DataFrame({"timestamp": med.index, "open": med.values, "high": med.values,
                                "low": med.values, "close": med.values, "volume": 0.0})
            dfp["timestamp"] = pd.to_datetime(dfp["timestamp"], utc=True)
            z = get_latest_zscore(dfp)
            c1, c2, c3 = st.columns(3)
            with c1:
                metric_help("Dólar implícito mediano (CCL)", f"${med.iloc[-1]:,.0f}", terms=("CCL", "mediana"))
            with c2:
                metric_help("Distancia del CCL a su media (z-score)", f"{z['z_atr']:+.2f}" if z["z_atr"] is not None else "-", terms=("CCL", "z-score", "ATR"))
            with c3:
                metric_help("Percentil histórico", f"{z['z_percentile']:.0f}%" if z["z_percentile"] is not None else "-", terms=("percentil del z",))
            st.info("El CCL es un tipo de cambio con tendencia. Un z-score alto indica que subió rápido respecto de su volatilidad reciente, no que vaya a revertir.")
            caption_help(f"Mediana calculada con {len(series)} empresas. Si una empresa se aleja más del 5% de la mediana, se resalta en naranja.")

    caption_help(
        "No usamos cointegración local/ADR "
        "porque el CCL depende del dólar entre mercados y no es estable. "
        "Pendiente: brecha CCL/oficial BCRA (sin fuente gratuita simple configurada todavía). "
        f"Ventana intradía común BYMA–NYSE hoy: {ventana_conjunta()}."
    )


def mostrar_ratio(r, nombre, symbols=()):
    if r is None:
        st.info(f"Sin datos suficientes para {nombre}.")
        return
    z = r["z_atr"]
    metric_help(nombre, f"{r['ratio']:.4f}", f"z = {z:+.2f}" if z is not None else "z = -", terms=("ratio", "z-score", *symbols))
    if r["percentile"] is not None:
        caption_help(f"Percentil histórico del z-score: {r['percentile']:.0f}%")


def render_historial():
    from src.data.snapshots import list_photos, get_photo, changes_between, export_photos, import_photos, SECTIONS
    with st.expander("Historial"):
        st.caption("Recuerda lo que decía el tablero en cada momento. Abrir esta sección o cambiar un selector **no** crea una foto.")
        try:
            photos = list_photos(DB_PATH)
        except Exception as exc:
            st.error(f"No se pudo leer el historial: {exc}")
            return
        if not photos:
            st.info("Todavía no hay fotos. Se crean al actualizar datos manualmente o con la copia diaria programada.")
            return
        view = st.radio("Ver", ["Hoy", "Ayer", "Semana pasada", "Elegir foto"], horizontal=True, key="hist_view")
        now = pd.Timestamp.now(tz="UTC")
        if view == "Hoy":
            chosen = [p for p in photos if str(p["created_at"])[:10] == str(now.date())]
        elif view == "Ayer":
            chosen = [p for p in photos if str(p["created_at"])[:10] == str((now - pd.Timedelta(days=1)).date())]
        elif view == "Semana pasada":
            chosen = [p for p in photos if now - pd.Timedelta(days=7) <= pd.to_datetime(p["created_at"], utc=True) <= now]
        else:
            chosen = photos
        if not chosen:
            st.info("No hay fotos en ese período.")
            return
        labels = {p["id"]: f"{p['created_at']} · {p['trigger']} · {p['status']}{' · tardía' if p['late'] else ''} · {p['machine']} · {p['four_hour_label']}" for p in chosen}
        pid = st.selectbox("Foto", list(labels), format_func=lambda i: labels[i], key="hist_photo")
        photo = get_photo(pid, DB_PATH)
        st.caption("Serie usada en esa foto: " + photo["four_hour_label"])
        st.caption("Definición de dirección: " + photo.get("direction_definition_label", "definición antigua"))
        with st.expander("Versiones 4h de esa foto"):
            if photo["four_hour_label"] == "4h antigua":
                st.write("4h antigua. La foto no se modifica ni se recalcula con la serie nueva.")
            else:
                for name, section in photo["content"].get("sections", {}).items():
                    for item in section.get("assets", []):
                        timeframe = item.get("timeframes", {}).get("4h", {})
                        version = timeframe.get("series_4h", {})
                        st.write(f"{timeframe.get('display_name', asset_label(item['symbol']))}: {version.get('label', '4h antigua')} · {version.get('version', '4h-antigua')}")
        with st.expander("Alineación y distancia por activo"):
            for name, section in photo["content"].get("sections", {}).items():
                for item in section.get("assets", []):
                    sym = item["symbol"]
                    align = item.get("alignment", {})
                    if align:
                        st.write(f"**{asset_label(sym)}**: {align.get('up', 0)}↑ / {align.get('down', 0)}↓ / {align.get('weak', 0)} débiles de {align.get('available', 0)} disponibles; faltan {align.get('missing_timeframes', [])}")
                    for tf, data in item.get("timeframes", {}).items():
                        dist = data.get("distance", {})
                        if dist:
                            ema = f"{dist.get('ema50_pct', 0):+.2f}%" if dist.get("ema50_pct") is not None else "—"
                            vwap = f"{dist.get('vwap_pct', 0):+.2f}%" if dist.get("vwap_pct") is not None else "—"
                            st.caption(f"{tf}: EMA50 {ema} · VWAP {vwap} · instrumento {dist.get('instrument', sym)} · sesión {dist.get('session', '—')}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Resultado", photo["status"])
        c2.metric("Activadores", photo["trigger"])
        c3.metric("Tardía", "Sí" if photo["late"] else "No")
        c4.metric("Máquina", photo["machine"])
        if photo["errors"]:
            st.error("Errores de esa actualización: " + "; ".join(photo["errors"]))
        st.caption(f"Temporalidades incluidas: {', '.join(json.loads(photo['tfs_scope']))}. Si fue rápida, faltan 1m, 5m, 15m y 4h en esa foto.")
        sections = photo["content"]["sections"]
        idx = sections.get("indices", {})
        if idx.get("kpis"):
            k = idx["kpis"]
            c1, c2, c3 = st.columns(3)
            c1.metric("Más fuerte 20 ruedas", k.get("top_relative_20d") or "—")
            c2.metric("Más alineado", k.get("most_aligned") or "—")
            c3.metric("Más alejado", k.get("most_stretched_1d") or "—")
        arg = sections.get("argentina", {}).get("ccl", {})
        if arg.get("median"):
            st.metric("CCL mediano de esa foto", f"${arg['median']:,.0f}")
        # Evolución de un activo
        symbols = sorted({a["symbol"] for s in SECTIONS for a in sections.get(s, {}).get("assets", [])})
        sym = st.selectbox("Activo para evolución", symbols, key="hist_asset")
        rows = []
        for p in list_photos(DB_PATH, 60):
            full = get_photo(p["id"], DB_PATH)
            for s in SECTIONS:
                for a in full["content"]["sections"].get(s, {}).get("assets", []):
                    if a["symbol"] == sym:
                        d = a["timeframes"].get("1D", {})
                        rows.append({"fecha": p["created_at"], "dirección": d.get("direction"), "z_1d": a.get("z_atr_1d")})
        if rows:
            evo = pd.DataFrame(rows).sort_values("fecha")
            st.dataframe(evo.tail(30), hide_index=True)
            if evo["z_1d"].notna().any():
                st.line_chart(evo.set_index("fecha")["z_1d"])
        # Cambios contra la foto anterior real
        ordered = sorted(photos, key=lambda p: p["created_at"])
        ids = [p["id"] for p in ordered]
        if pid in ids and ids.index(pid) > 0:
            prev = ids[ids.index(pid) - 1]
            changes = changes_between(prev, pid, DB_PATH)
            st.subheader("Cambios frente a la foto anterior")
            if changes:
                st.dataframe(pd.DataFrame(changes), hide_index=True)
            else:
                st.caption("Sin cambios relevantes frente a la foto anterior.")
        # Comparar dos fotos
        st.subheader("Comparar dos fotos")
        a_id = st.selectbox("Foto A", list(labels), format_func=lambda i: labels[i], key="hist_a")
        b_id = st.selectbox("Foto B", list(labels), format_func=lambda i: labels[i], key="hist_b")
        if st.button("Comparar A vs B", key="hist_compare"):
            changes = changes_between(a_id, b_id, DB_PATH)
            st.dataframe(pd.DataFrame(changes) if changes else pd.DataFrame([{"Resultado": "Sin cambios relevantes"}]), hide_index=True)
        st.download_button("Exportar historial (ZIP)", data=export_photos(DB_PATH), file_name="historial_tablero.zip", mime="application/zip", key="hist_export")
        uploaded = st.file_uploader("Importar historial (ZIP)", type=["zip"], key="hist_import")
        if uploaded is not None:
            result = import_photos(uploaded.read(), DB_PATH)
            st.success(f"Importación: {result['added']} agregadas, {result['skipped_duplicates']} duplicadas exactas omitidas, {result['kept_distinct']} conservadas como versiones distintas.")
        st.caption("Esta sección muestra lo que el tablero decía en cada foto. No recalcula con los precios de hoy.")


def render_en_construccion():
    st.info("En construcción")


# ----------------------------------------------------------------------
# App principal
# ----------------------------------------------------------------------
def global_update_controls():
    # Botón actualizar
    if "tf_update" not in st.session_state:
        st.session_state.tf_update = None

    c_btn, c_btn2 = st.columns(2)
    correr_full = c_btn.button("🔄 Actualizar datos (todas las temporalidades)", help=help_text("temporalidad", *ALL_TF))
    correr_rapido = c_btn2.button("⚡ Actualización rápida (solo una hora y diario)", help=help_text("1h", "1D"))

    if correr_full or correr_rapido:
        target_tfs = "1m,5m,15m,1h,4h,1D" if correr_full else "1h,1D"
        quick = bool(correr_rapido)
        prog = st.progress(0, text=f"Descargando datos ({target_tfs})...")
        p1 = subprocess.run(
            [sys.executable, "update_data.py", "--tf", target_tfs], cwd=ROOT, check=False
        )
        prog.progress(50, text="Calculando régimen, z-score y cointegración...")
        p2 = subprocess.run(
            [sys.executable, "run_calc.py", "--tf", target_tfs], cwd=ROOT, check=False
        )
        prog.progress(100, text="¡Listo!")
        st.cache_data.clear()

        if p1.returncode != 0:
            st.error(f"❌ Falló la descarga de datos (update_data.py). Código de salida: {p1.returncode}. Revisá la consola.")
            errors = [f"update_data.py código {p1.returncode}"]
            status = "error"
        elif p2.returncode != 0:
            st.error(f"❌ Fallaron los cálculos (run_calc.py). Código de salida: {p2.returncode}. Revisá la consola.")
            errors = [f"run_calc.py código {p2.returncode}"]
            status = "error"
        else:
            st.success(f"✅ Descarga y cálculos terminaron ({target_tfs}). Revisá las fechas y avisos para ver qué series recibieron datos nuevos.")
            errors = []
            status = "ok"
        try:
            from src.data.snapshots import take_snapshot
            pid = take_snapshot(DB_PATH, trigger="manual_full" if not quick else "manual_quick", status=status,
                                errors=errors, tfs_scope=target_tfs.split(","))
            st.caption(f"Foto del tablero guardada: {pid}. Actualización rápida: quedan fuera 1m, 5m, 15m y 4h de esta foto." if quick else f"Foto del tablero guardada: {pid}.")
        except Exception as exc:
            st.error(f"No se pudo guardar la foto del tablero: {exc}")

def main():
    refresh_catalog()
    st.title("📊 Dashboard Financiero")
    db = DatabaseManager(DB_PATH)
    signature = db.data_signature()
    if st.session_state.get("data_signature") != signature:
        st.cache_data.clear()
        st.session_state["data_signature"] = signature
    with open(os.path.join(ROOT, "config", "calc.yaml"), encoding="utf-8") as file:
        calc_config = yaml.safe_load(file)
    health = db.get_calculation_health(calc_config)
    st.session_state["calculation_health"] = health
    pending = [h for h in health if h["status"] != "ok"]
    if pending:
        st.warning(f"Hay {len(pending)} resultados desactualizados, no calculables o sin versión comprobable. Revisá las fechas de cálculo y datos usados; los valores anteriores no se presentan como recién actualizados.")
    notices = db.get_data_notices()
    if notices:
        with st.expander(f"Avisos de descargas y datos ({len(notices)})"):
            for notice in notices[:30]:
                st.markdown(rich_text(entity_label(notice['asset']) + " · " + TF_LABELS.get(notice['timeframe'], notice['timeframe']) + ": " + explain_symbols(notice['message'])), unsafe_allow_html=True)
            if len(notices) > 30:
                st.caption("El registro completo puede consultarse con check_data.py.")
    global_update_controls()
    render_historial()
    tabs = st.tabs(["Índices", "Metales", "Equity", "Small caps", "Cripto", "Argentina"])
    with tabs[0]:
        render_section_pilot(DB_PATH, render_seccion, section="indices")
    with tabs[1]:
        render_seccion("metales")
    with tabs[2]:
        render_seccion("equity")
    with tabs[3]:
        render_seccion("smallcaps")
    with tabs[4]:
        render_seccion("cripto")
    with tabs[5]:
        render_seccion("argentina")


if __name__ == "__main__":
    main()
