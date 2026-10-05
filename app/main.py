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

SECTION_MACRO = {
    "indices": ["DGS10", "T10Y2Y", "DFII10", "VIXCLS", "DTWEXBGS", "BAMLH0A0HYM2"],
    "metales": ["DFII10", "DTWEXBGS"],
    "equity": ["DGS10", "T10Y2Y", "BAMLH0A0HYM2"],
    "smallcaps": ["DGS10", "BAMLH0A0HYM2"],
    "cripto": ["DTWEXBGS", "VIXCLS"],
    "argentina": ["DTWEXBGS"],
}

NOTAS_BASE = """
- **Z-score alto (|z| > 2)** indica que el precio está *estirado* respecto a su promedio,
  **no** una señal de reversión: en tendencias fuertes puede persistir varios días.
- **Régimen "(débil)"**: la tendencia es clara por momentum pero el ADX todavía no la confirma.
- **Cointegración**: que dos activos se muevan juntos hoy no garantiza que sigan haciéndolo; puede romperse.
- **Datos gratuitos**: yfinance y Binance tienen retraso de minutos.
- **Intradía de índices**: Yahoo guarda poco historial (1m ~7 días, 5m/15m ~60 días).
"""

NOTAS_SECCION = {
    "indices": NOTAS_BASE,
    "metales": NOTAS_BASE + "\n- **Oro/Plata**: cuando el ratio sube, el oro gana terreno frente a la plata (y viceversa). Importa el *z-score del ratio*, no el nivel absoluto.",
    "cripto": NOTAS_BASE + "\n- **Cripto es 24/7**: no se marca desactualizado por fines de semana. **ETH/BTC y SOL/BTC** altos = altcoin dominando; muy bajos = BTC dominando.",
    "equity": NOTAS_BASE,
    "smallcaps": NOTAS_BASE,
    "argentina": NOTAS_BASE + "\n- **CCL implícito**: depende del dólar CCL entre mercados; los horarios de BYMA y NYSE no coinciden del todo, por lo que los valores intradía deben leerse con cautela.",
}


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

    # a) Barra macro (relevante a la sección)
    with st.spinner("Cargando referencias macro..."):
        macro = obtener_macro()
    macro_ids = SECTION_MACRO.get(seccion, [])
    if not macro.empty:
        if macro_ids:
            macro = macro[macro.index.isin(macro_ids)]
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
        fuentes = obtener_fuentes()

    filas = []
    filas_edad = []
    ahora = pd.Timestamp.now(tz="UTC")
    for sym in activos:
        regs = reg[(reg.symbol == sym) & (reg.timeframe == "1D")]
        zs = zdf[(zdf.symbol == sym) & (zdf.timeframe == "1D")]
        sem = semaforos.get(sym, {}).get("trends", {})
        fila = {"Activo": sym, "Fuente": fuentes.get(sym, "-")}
        fila["Régimen (1D)"] = regs["regime"].iloc[0] if not regs.empty else "sin datos"
        edad_fila = {"Activo": sym}
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
    st.dataframe(styled, use_container_width=True)
    st.caption("▫️ = sin datos (la fuente gratuita no tiene historia para ese activo/temporalidad).")

    # Antigüedad del dato por temporalidad (amarillo = desactualizado)
    st.caption("Antigüedad del dato por temporalidad (amarillo = desactualizado):")
    df_edad = pd.DataFrame(filas_edad)

    def viejo(v):
        return "background-color: #fff3b0" if v and v.startswith("⚠") else ""

    st.dataframe(df_edad.style.map(viejo), use_container_width=True, hide_index=True)

    # c) Cointegración / CCL implícito (según sección)
    if seccion == "argentina":
        st.subheader("CCL implícito por empresa")
        pares_cfg = assets_cfg[seccion].get("pares", [])
        equiv = assets_cfg[seccion].get("equivalencias", {})
        mostrar_ccl(pares_cfg, equiv)
    else:
        st.subheader("Cointegración de pares")
        if pares:
            coint = obtener_cointegracion(seccion, pares)
            if coint.empty:
                st.info("Sin resultados de cointegración guardados aún.")
            else:
                st.dataframe(
                    coint.style.format({"p-valor": "{:.4f}", "Beta": "{:.2f}",
                                        "Vida media (velas)": "{:.1f}", "Estabilidad %": "{:.0f}%"}, na_rep="-"),
                    use_container_width=True,
                )

    # c.b) Ratios con z-score (según sección)
    if seccion == "metales":
        st.subheader("Ratio Oro/Plata (GC=F / SI=F)")
        r = ratio_zscore("GC=F", "SI=F")
        mostrar_ratio(r, "Oro/Plata")
    elif seccion == "cripto":
        st.subheader("Dominancia relativa (ratio vs BTC)")
        c1, c2 = st.columns(2)
        with c1:
            mostrar_ratio(ratio_zscore("ETH/USDT", "BTC/USDT"), "ETH/BTC")
        with c2:
            mostrar_ratio(ratio_zscore("SOL/USDT", "BTC/USDT"), "SOL/BTC")
    elif seccion == "smallcaps":
        st.subheader("Fuerza relativa: IWM vs ^GSPC")
        mostrar_ratio(ratio_zscore("IWM", "^GSPC"), "IWM/^GSPC")
    elif seccion == "equity":
        st.subheader("Mapa de calor: z-score (ATR) por temporalidad")
        z_rows = []
        for sym in activos:
            fila = {"Activo": sym}
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
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Verde = extendido al alza (líder), rojo = débil (rezagado). Ordenado por z de 1D.")

    # d) Detalle por activo
    st.subheader("Detalle por activo")
    c1, c2 = st.columns(2)
    with c1:
        sym_sel = st.selectbox("Activo", activos, key=f"sym_{seccion}")
    with c2:
        tf_sel = st.selectbox("Temporalidad", ALL_TF, index=ALL_TF.index("1D"), key=f"tf_{seccion}")
    with st.spinner("Armando gráfico..."):
        grafico_detalle(sym_sel, tf_sel)

    # f) Fecha de actualización
    st.caption(f"Última actualización de datos: {ultima_actualizacion()}")

    # g) Cómo leer esto (adaptado a la sección)
    with st.expander("Cómo leer esto"):
        st.markdown(NOTAS_SECCION.get(seccion, NOTAS_BASE))


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
        filas.append({"Empresa": p["nombre"], "Local": p["local"], "ADR": p["adr"],
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
    st.dataframe(styled, use_container_width=True)

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
            c1.metric("CCL mediana (hoy)", f"${med.iloc[-1]:,.0f}")
            c2.metric("Z-score CCL", f"{z['z_atr']:+.2f}" if z["z_atr"] is not None else "-")
            c3.metric("Percentil histórico", f"{z['z_percentile']:.0f}%" if z["z_percentile"] is not None else "-")
            st.info("El CCL es un tipo de cambio con tendencia. Un z-score alto indica que subió rápido respecto de su volatilidad reciente, no que vaya a revertir.")
            st.caption(f"Mediana calculada con {len(series)} empresas. Si una empresa se aleja >5% de la mediana, se resalta en naranja.")

    st.caption(
        "No usamos cointegración local/ADR "
        "porque el CCL depende del dólar entre mercados y no es estable. "
        "Pendiente: brecha CCL/oficial BCRA (sin fuente gratuita simple configurada todavía). "
        f"Ventana intradía común BYMA–NYSE hoy: {ventana_conjunta()}."
    )


def mostrar_ratio(r, nombre):
    if r is None:
        st.info(f"Sin datos suficientes para {nombre}.")
        return
    z = r["z_atr"]
    st.metric(nombre, f"{r['ratio']:.4f}", f"z = {z:+.2f}" if z is not None else "z = -")
    if r["percentile"] is not None:
        st.caption(f"Percentil histórico del z: {r['percentile']:.0f}%")


def render_en_construccion():
    st.info("En construcción")


# ----------------------------------------------------------------------
# App principal
# ----------------------------------------------------------------------
def main():
    st.title("📊 Dashboard Financiero")

    # Botón actualizar
    if "tf_update" not in st.session_state:
        st.session_state.tf_update = None

    c_btn, c_btn2 = st.columns(2)
    correr_full = c_btn.button("🔄 Actualizar datos (todas las temporalidades)")
    correr_rapido = c_btn2.button("⚡ Actualización rápida (solo 1h y 1D)")

    if correr_full or correr_rapido:
        target_tfs = "1m,5m,15m,1h,4h,1D" if correr_full else "1h,1D"
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
        elif p2.returncode != 0:
            st.error(f"❌ Fallaron los cálculos (run_calc.py). Código de salida: {p2.returncode}. Revisá la consola.")
        else:
            st.success(f"✅ Datos actualizados ({target_tfs}).")

    tabs = st.tabs(["Índices", "Metales", "Equity", "Small caps", "Cripto", "Argentina"])
    with tabs[0]:
        render_seccion("indices")
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
