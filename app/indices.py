"""Pantalla C2 aislada. Las cinco pestañas anteriores siguen usando render_seccion."""
import json
import subprocess
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml
from src.data import DatabaseManager
from src.data.backup import ROOT
from src.calc.regime import get_latest_market_regime
from src.data.four_hour import prepare_stored, market_results, sufficient_history, policy, series_descriptor
from src.indices_math import (prepare_bars, freshness, alignment, daily_means, relative_performance,
    session_vwap, select_range, aggregate_4h, aggregate_regular_hours, unexpected_gaps, pair_analysis, ALIGNMENT_LEGEND, schedule)
from src.presentation import asset_label, pair_label, help_text, TF_LABELS, section_terms, rich_text, definition

TFS = ["1m", "5m", "15m", "1h", "4h", "1D"]
FUTURES_NOTICE = "Los futuros continuos de Yahoo pueden tener saltos en los cambios de contrato; no se verificó cómo los ajusta."


def configs():
    return tuple(yaml.safe_load((ROOT / "config" / file).read_text(encoding="utf-8"))
                 for file in ["assets.yaml", "calc.yaml", "indices_pilot.yaml", "operations.yaml", "pairs.yaml"])


@st.cache_data(ttl=900, show_spinner=False)
def raw_data(db_path, symbol, tf, signature):
    with DatabaseManager(db_path)._get_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM candles WHERE symbol=? AND timeframe=? ORDER BY timestamp", conn, params=(symbol, tf))
    df["timestamp"] = pd.to_datetime(df.timestamp, utc=True, format="mixed")
    return df


@st.cache_data(ttl=900, show_spinner=False)
def view_model(db_path, signature, settings_json, _minute):
    assets, calc, pilot, ops, _ = json.loads(settings_json)
    now = pd.to_datetime(_minute, utc=True)
    daily, directions, frames, qualities = {}, {}, {}, []
    rows = []
    for symbol in assets["indices"]["activos"]:
        calendar = pilot["calendars"][symbol]
        states = {}
        for tf in TFS:
            if tf == "4h":
                bars = prepare_stored(raw_data(db_path, symbol, "4h", signature), symbol, now, calendar)
                effective_calendar = "CME_Equity" if policy(symbol) and policy(symbol)["method"] == "future_utc" else calendar
            else:
                bars = prepare_bars(raw_data(db_path, symbol, tf, signature), symbol, tf, calendar, now)
                effective_calendar = calendar
            frames[(symbol, tf)] = bars
            closed = bars[bars.closed]
            age = freshness(bars, tf, effective_calendar, now)
            result = market_results(closed, calc)[0] if tf == "4h" else get_latest_market_regime(closed, calc["regime"])
            state = result["direction"]
            states[tf] = state if not age["stale"] else "sin datos"
            qualities.append({"Activo": asset_label(symbol, tf), "Escala": TF_LABELS[tf],
                "Fuente": "Yahoo · " + asset_label(symbol, "4h") if tf == "4h" and policy(symbol) and policy(symbol)["method"] == "future_utc" else "Yahoo",
                "Último dato UTC": str(age.get("last_data", "—")),
                "Calidad": result.get("error_message") or age["label"], "Velas guardadas": len(closed), "Dirección": state})
            if tf == "1D":
                daily[symbol] = daily_means(bars)
                d = daily[symbol].iloc[-1] if len(daily[symbol]) else None
                rows.append({"symbol": symbol, "direction": state, "daily_stale": age["stale"], "age": age["label"],
                    "distance_pct": float(d.distance_pct) if d is not None and pd.notna(d.distance_pct) else None,
                    "distance_std": float(d.distance_std) if d is not None and pd.notna(d.distance_std) else None,
                    "last_data": str(d.bar_end) if d is not None else "—"})
        directions[symbol] = alignment(states)
    series = {s: d.set_index("session").close for s, d in daily.items()}
    benchmark = series.get("^GSPC", pd.Series(dtype=float))
    perf = relative_performance(series, benchmark, pilot["relative_strength_sessions"])
    return {"rows": rows, "alignment": directions, "daily": daily, "frames": frames, "quality": pd.DataFrame(qualities),
            "performance": perf, "calculated_at": pd.Timestamp.now(tz="UTC").isoformat()}


@st.cache_data(ttl=900, show_spinner=False)
def cointegration_model(db_path, signature, settings_json, _minute, y, x):
    assets, calc, pilot, ops, pairs = json.loads(settings_json)
    values = []
    for symbol in [y, x]:
        bars = prepare_bars(raw_data(db_path, symbol, "1D", signature), symbol, "1D", pilot["calendars"][symbol], _minute)
        values.append(bars[bars.closed].set_index("session").close)
    return pair_analysis(*values, pilot["cointegration"])


def update_indices(db_path, quick=False):
    tfs = "1h,1D" if quick else "1m,5m,15m,1h,4h,1D"
    progress = st.progress(0, text="Actualizando únicamente los índices...")
    steps = [[sys.executable, str(ROOT / "update_data.py"), "--seccion", "indices", "--tf", tfs, "--db", db_path],
             [sys.executable, str(ROOT / "run_calc.py"), "--seccion", "indices", "--tf", tfs, "--db", db_path],
             [sys.executable, str(ROOT / "update_indices_references.py"), "--tf", tfs, "--db", db_path]]
    failures = []
    for i, command in enumerate(steps):
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        progress.progress((i + 1) / len(steps), text=["Índices descargados; recalculando...", "Actualizando referencias negociables...", "Proceso terminado"][i])
        if result.returncode:
            failures.append(f"{Path(command[1]).name}: código {result.returncode}\n{result.stderr[-1500:]}\n{result.stdout[-1500:]}")
    st.cache_data.clear()
    st.session_state["pilot_update_message"] = "Actualización parcial: revisá fuentes y fechas." if failures else "Índices y referencias actualizados."
    st.session_state["pilot_update_errors"] = failures
    st.rerun()


def metric(label, value, explanation, delta=None):
    st.metric(label, value, delta, help=explanation)


def render_detail(db_path, signature, pilot, ops, frames):
    st.subheader("Detalle por activo")
    symbols = list(pilot["references"])
    c1, c2, c3 = st.columns(3)
    selected_tf = st.session_state.get("pilot_tf")
    symbol = c1.selectbox("Activo", symbols, format_func=lambda s: asset_label(s, selected_tf), key="pilot_asset", help=help_text("activo"))
    tf = c2.selectbox("Temporalidad", TFS, index=5, format_func=lambda t: TF_LABELS[t], key="pilot_tf", help=help_text("temporalidad"))
    period = c3.selectbox("Rango", ["Predeterminado", "Último mes", "Últimos 3 meses", "Último año", "Personalizado"], key="pilot_range",
                         help="El rango se mide en sesiones o tiempo, no en un número fijo de velas.")
    now = pd.Timestamp.now(tz="UTC")
    start, end = None, None
    if period != "Predeterminado" and period != "Personalizado":
        start = now - pd.DateOffset(months={"Último mes": 1, "Últimos 3 meses": 3, "Último año": 12}[period])
    if period == "Personalizado":
        chosen = st.date_input("Desde / hasta", value=(now.date()-pd.Timedelta(days=30), now.date()), key="pilot_dates")
        if len(chosen) != 2:
            st.info("Elegí el comienzo y el fin del rango.")
            return
        start = pd.to_datetime(chosen[0], utc=True)
        end = pd.to_datetime(chosen[1], utc=True) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    reference = symbol
    mode = ops["cme_vwap_session"]["default"] or "complete"
    if tf != "1D":
        options = pilot["references"][symbol] + ([] if tf == "4h" and policy(symbol) and policy(symbol)["method"] == "future_utc" else [symbol])
        c1, c2 = st.columns(2)
        reference = c1.selectbox("Instrumento del gráfico", options, format_func=asset_label, key="pilot_reference_" + symbol,
            help="El gráfico, el precio y el volumen pertenecen siempre al mismo instrumento. El índice no recibe el VWAP de un futuro.")
        selected = c2.selectbox("Sesión del VWAP de futuros", ["complete", "regular"], index=0 if reference.endswith("=F") and mode == "complete" else 1,
            format_func=lambda s: "Completa: reinicio 18:00 Nueva York" if s == "complete" else "Regular: 09:30–16:00 Nueva York",
            disabled=not reference.endswith("=F"), key="pilot_vwap_session_" + reference,
            help="Sesión completa hasta las 17:00 del día siguiente; sesión regular de acciones hasta las 16:00. Se ajusta al cambio de hora de Nueva York.")
        mode = selected if reference.endswith("=F") else "regular"
        st.caption("Sesión de VWAP: **configuración provisional** (elegida para empezar; la confirmás vos).")
    if reference == "NQ=F":
        st.info("Comparación de " + asset_label(reference) + " con tu CFD USTEC: pendiente de tu validación con el bróker.")
    cal = pilot["calendars"][reference]
    can_vwap = reference in pilot["names"] or reference == "IWM"
    base_tf = "1h" if tf == "4h" else tf
    if tf == "1h" and mode == "regular" and reference.endswith("=F"):
        base_tf = "5m"
    data = None
    chart_label = asset_label(reference)
    if tf == "4h":
        spec = policy(symbol)
        storage = symbol if spec and spec["method"] == "future_utc" and reference == spec["reference"] else reference
        data = prepare_stored(raw_data(db_path, storage, "4h", signature), storage, now, cal)
        chart_label = asset_label(storage, "4h")
        with DatabaseManager(db_path)._get_connection() as conn:
            descriptor = series_descriptor(storage, conn)
        st.caption(chart_label + " · " + descriptor["label"])
        if descriptor["method"] == "future_utc":
            st.caption("Horario de plataforma: " + descriptor["timezone"] + " · " + "/".join(descriptor["starts"]) + " · validación pendiente.")
        enough, required = sufficient_history(data[data.closed], configs()[1])
        if not enough:
            st.warning(f"Historia insuficiente en 4h: se requieren {required} velas; no se usa una etiqueta dudosa.")
        st.caption("Las velas 4h se construyen desde horas. El selector de sesión cambia el VWAP, no las aperturas de esa serie de 4h.")
    else:
        data = prepare_bars(raw_data(db_path, reference, base_tf, signature), reference, base_tf, cal, now,
                            regular=reference.endswith("=F") and mode == "regular")
    if tf == "1h" and mode == "regular" and reference.endswith("=F"):
        data = aggregate_regular_hours(data, now)
        st.caption("Sesión regular: las horas se reconstruyen desde 09:30 de Nueva York con velas de cinco minutos.")
    if data.empty:
        st.warning("No hay datos del instrumento elegido. Actualizá las referencias o elegí el precio del índice.")
        return
    if tf == "1D":
        means = daily_means(data)
        plotted = data.merge(means[["timestamp", "ema50", "ema200", "distance_pct", "distance_std"]], on="timestamp", how="left")
    else:
        plotted = data.copy()
    visible, info = select_range(plotted, tf, pilot["default_ranges"], now, start, end)
    if visible.empty:
        st.warning("No hay datos para ese rango.")
        return
    st.caption(f"{len(visible)} velas visibles de {len(data)} disponibles · {info['start']} → {info['end']} UTC.")
    if info["short_history"]:
        st.warning("La historia disponible es más corta que el rango solicitado; se muestra toda la que hay.")
    gaps = unexpected_gaps(visible, tf, cal)
    if gaps:
        st.warning(f"Hay {len(gaps)} posibles huecos con mercado abierto. Se comprime el eje, pero no se ocultan estos avisos.")
        with st.expander("Ver huecos del gráfico"):
            for message in gaps[:30]:
                st.write(message)
    labels = visible.timestamp.dt.strftime("%Y-%m-%d %H:%M UTC").tolist()
    fig = go.Figure(go.Candlestick(x=labels, open=visible.open, high=visible.high, low=visible.low, close=visible.close, name=chart_label))
    open_bars = visible[~visible.closed]
    if len(open_bars):
        fig.add_trace(go.Scatter(x=open_bars.timestamp.dt.strftime("%Y-%m-%d %H:%M UTC"), y=open_bars.close,
            mode="markers", marker={"color": "orange", "size": 10, "symbol": "diamond"}, name="Vela abierta o recibida provisional"))
        st.caption("Diamante naranja: vela abierta o último valor recibido antes de terminar; no se usa para la lectura de cierres.")
    vwap_last, partial = None, []
    if tf == "1D":
        for p, color in [(50, "orange"), (200, "royalblue")]:
            fig.add_trace(go.Scatter(x=labels, y=visible[f"ema{p}"], name=f"Media de {p} cierres", line={"color": color}))
        if visible.ema200.isna().all():
            st.info("No hay 200 cierres anteriores suficientes para mostrar la media larga.")
    elif can_vwap:
        # Calcular antes de recortar; escoger la menor vela que cubra el rango.
        candidates = ["1m", "5m", "15m", "1h"]
        source = None
        chosen_tf = None
        for candidate in candidates:
            raw = raw_data(db_path, reference, candidate, signature)
            prepared = prepare_bars(raw, reference, candidate, cal, now, regular=mode == "regular" and reference.endswith("=F"))
            if len(prepared) and prepared.timestamp.min() <= visible.timestamp.min() - pd.Timedelta(days=1):
                source, chosen_tf = prepared, candidate
                break
        if source is None:
            source = prepare_bars(raw_data(db_path, reference, base_tf, signature), reference, base_tf, cal, now,
                regular=mode == "regular" and reference.endswith("=F"))
            chosen_tf = base_tf
            partial.append("La fuente no cubre el comienzo completo de todas las sesiones del rango.")
        v = session_vwap(source)
        # Datos previos de la sesión incluidos aunque queden fuera del rango visible.
        end_times = pd.DatetimeIndex(visible.bar_end)
        idx = pd.DatetimeIndex(v.bar_end).get_indexer(end_times, method="pad")
        sampled = v.iloc[np.maximum(idx, 0)].copy().reset_index(drop=True)
        vcolumns = ["vwap", "sigma", "distance_bands", "upper1", "lower1", "upper2", "lower2"]
        sampled.loc[idx < 0, vcolumns] = np.nan
        # No arrastrar el VWAP de una sesión anterior a una nueva sin volumen.
        sampled.loc[sampled.session.to_numpy() != visible.session.to_numpy(), vcolumns] = np.nan
        for column, label, color in [("vwap", "VWAP de " + reference, "orange"), ("upper1", "+1 desvío", "seagreen"),
            ("lower1", "−1 desvío", "seagreen"), ("upper2", "+2 desvíos", "gray"), ("lower2", "−2 desvíos", "gray")]:
            xs, ys, previous = [], [], None
            for x, y, session in zip(labels, sampled[column], visible.session):
                if previous is not None and previous != session:
                    xs.append(x); ys.append(None)
                xs.append(x); ys.append(y)
                previous = session
            fig.add_trace(go.Scatter(x=xs, y=ys, name=label, connectgaps=False,
                                    line={"color": color, "width": 2 if column == "vwap" else 1, "dash": "solid" if column == "vwap" else "dot"}))
        coverage = v.groupby("session").volume_valid.mean()
        session = visible.session.iloc[-1]
        if session in coverage and coverage[session] < pilot["vwap"]["minimum_volume_coverage"]:
            partial.append(f"La sesión tiene volumen positivo en solo {coverage[session]:.0%} de sus velas.")
        if len(sampled) and pd.notna(sampled.vwap.iloc[-1]):
            vwap_last = sampled.iloc[-1]
        st.caption(f"VWAP de {reference} — {asset_label(reference)} · precio típico y volumen del mismo instrumento · base: {TF_LABELS[chosen_tf]} · sesión {mode}.")
    else:
        st.info("VWAP no disponible para este índice. No se mezcla su precio con el volumen de otro instrumento.")
    fig.update_layout(height=520, xaxis={"type": "category", "categoryorder": "array", "categoryarray": labels, "rangeslider": {"visible": False}, "nticks": 8},
                      title=chart_label + " — " + TF_LABELS[tf], yaxis_title="Precio", legend={"orientation": "h"})
    st.plotly_chart(fig, width="stretch", key="pilot_price_chart")
    if partial:
        st.warning("VWAP parcial: " + " ".join(partial))
    if vwap_last is not None:
        price = visible.close.iloc[-1]
        pct = (price / vwap_last.vwap - 1) * 100
        bands = (price - vwap_last.vwap) / vwap_last.sigma if vwap_last.sigma > 0 else None
        where = "sobre" if pct >= 0 else "bajo"
        text = f"El instrumento está {abs(pct):.2f}% {where} su promedio de sesión"
        if bands is not None:
            text += f" ({abs(bands):.2f} bandas de distancia)"
        st.write(text + ". Una separación alta no asegura una vuelta al promedio.")
    elif tf == "1D" and pd.notna(visible.ema50.iloc[-1]):
        pct = visible.distance_pct.iloc[-1]
        st.write(f"El índice está {abs(pct):.2f}% {'sobre' if pct >= 0 else 'bajo'} su media de 50 cierres.")
    if tf != "1D":
        long_daily = daily_means(prepare_bars(raw_data(db_path, reference, "1D", signature), reference, "1D", cal, now))
        if len(long_daily) and pd.notna(long_daily.ema200.iloc[-1]):
            long_pct = (visible.close.iloc[-1] / long_daily.ema200.iloc[-1] - 1) * 100
            st.caption(f"Línea base larga del mismo instrumento: {long_pct:+.2f}% frente a la media de 200 cierres diarios, hasta {long_daily.session.iloc[-1]}.")


def render_cointegration(db_path, signature, settings_json, minute, pilot, pairs):
    with st.expander("Relaciones entre índices: corto y largo plazo"):
        tf = st.selectbox("Escala de la relación", ["1D", "1h", "4h"], format_func=lambda t: TF_LABELS[t], key="pilot_pair_tf",
                          help="La estabilidad se evalúa solo en diario. En una y cuatro horas se informa historia insuficiente.")
        if tf != "1D":
            st.info("Historia insuficiente para evaluar estabilidad")
            return
        pair = st.selectbox("Par de índices", list(range(len(pairs))), format_func=lambda i: pair_label(pairs[i]["y"], pairs[i]["x"]), key="pilot_pair", help=help_text("par", "cointegración"))
        p = pairs[pair]
        requested = (p["y"], p["x"])
        if st.button("Mostrar comparación y gráficos del par", key="pilot_load_pair",
                     help="Calcula la relación diaria y los gráficos móviles. La primera consulta puede tardar; después queda en caché."):
            st.session_state["pilot_loaded_pair"] = requested
        if st.session_state.get("pilot_loaded_pair") != requested:
            st.caption("Elegí el par y pedí la comparación. Así no se recalcula su historia mientras mirás los indicadores principales.")
            return
        with st.spinner("Comparando ventanas y la línea base larga..."):
            result = cointegration_model(db_path, signature, settings_json, minute, p["y"], p["x"])
        st.write("**Estado: " + result["state"] + "**")
        if result.get("reason"):
            st.info(result["reason"])
        if result["state"] == "no calculable":
            return
        c1, c2, c3 = st.columns(3)
        with c1:
            metric("Beta larga fija", f"{result['beta']:.3f}", "Factor ajustado usando solo la historia diaria disponible hasta este último cierre, idéntico para las dos comparaciones.")
        with c2:
            metric("Últimas 250 velas", f"{result['z_short']:+.2f}", "Distancia frente a media y desvío recientes; no cambia la beta.")
        with c3:
            metric("Historia larga", f"{result['z_long']:+.2f}", "Distancia del mismo spread frente a toda la historia válida disponible.")
        st.caption(f"Bloques sin solape: {result['confirmed_blocks']} de 5 confirmaron ambos órdenes. Base larga: {result['start']} → {result['end']} ({result['bars']} cierres).")
        fig = go.Figure(go.Scatter(x=result["spread"].index, y=result["spread"], name="Diferencia con beta larga fija"))
        fig.add_hline(y=result["mean_long"], line_dash="dash", annotation_text="Media larga")
        fig.add_hline(y=result["mean_short"], line_dash="dot", annotation_text="Media reciente")
        fig.update_layout(height=260, title="Mismo spread: referencia reciente y larga")
        st.plotly_chart(fig, width="stretch", key="pilot_spread")
        r = result["rolling"]
        fig = go.Figure()
        for col, label in [("p_yx", "Primero respecto del segundo"), ("p_xy", "Segundo respecto del primero")]:
            fig.add_trace(go.Scatter(x=r.date, y=r[col], name=label))
        fig.add_hline(y=.05, line_dash="dash", line_color="red", annotation_text="Umbral 0,05")
        fig.update_layout(height=260, title="p-valor móvil: 500 cierres, cada 21 ruedas", yaxis_range=[0, 1])
        st.plotly_chart(fig, width="stretch", key="pilot_pvalue")
        with st.expander("Pruebas y regla del estado"):
            st.json({"ventana_principal": result["primary"], "contraste": result["contrast"], "parámetros": pilot["cointegration"]})
            st.write("Estable exige confirmación en ambos órdenes, contraste concordante, Johansen con una relación y al menos cuatro de cinco bloques confirmados. Intermitente indica confirmaciones parciales o discrepancias. Sin relación significa sin confirmación en los períodos evaluados.")
        st.markdown("**Contexto académico — no interviene en los números:** Engle y Granger (1987) desarrollaron pruebas para estudiar un equilibrio entre series con tendencia; no estudiaron específicamente estos pares de índices. [Referencia verificada](https://doi.org/10.2307/1913236).")


def render_indices(db_path, legacy_render):
    assets, calc, pilot, ops, pairs = configs()
    signature = DatabaseManager(db_path).data_signature()
    minute = pd.Timestamp.now(tz="UTC").floor("min").isoformat()
    settings_json = json.dumps([assets, calc, pilot, ops, pairs], sort_keys=True)
    with st.spinner("Preparando la lectura de Índices y su calendario..."):
        model = view_model(db_path, signature, settings_json, minute)
    # Las edades corresponden a la hora de cálculo visible. La lectura se
    # renueva al cambiar precios o al vencer su caché, sin recalcular en cada clic.
    data_end = max((r["last_data"] for r in model["rows"] if r["last_data"] != "—"), default="Sin datos")
    calculated = pd.to_datetime(model["calculated_at"], utc=True).tz_convert("America/Argentina/Buenos_Aires")
    st.caption(f"Datos al: {data_end} · Calculado: {calculated.strftime('%d/%m/%Y %H:%M:%S')} Buenos Aires")
    c1, c2 = st.columns(2)
    if c1.button("Actualizar Índices y referencias", key="pilot_update_all", help="Descarga y calcula solo Índices; las referencias tienen precio y volumen propios."):
        update_indices(db_path)
    if c2.button("Actualización rápida de Índices", key="pilot_update_quick", help="Solo una hora y diario; las escalas cortas pueden seguir atrasadas."):
        update_indices(db_path, True)
    if st.session_state.get("pilot_update_message"):
        st.info(st.session_state["pilot_update_message"])
        for err in st.session_state.get("pilot_update_errors", []):
            st.error(err)
    rows = model["rows"]
    stale = sum(r["daily_stale"] for r in rows)
    if stale:
        st.warning(f"{stale} índices tienen cierres diarios atrasados o no comprobables. Los conteos describen sus últimos datos, no una cotización en vivo.")
    up = sum(r["direction"].startswith("alcista") for r in rows)
    down = sum(r["direction"].startswith("bajista") for r in rows)
    aligned = max(model["alignment"], key=lambda s: model["alignment"][s]["score"], default=None)
    performance = model["performance"].dropna(subset=["relative_pp"])
    leader = performance.sort_values("relative_pp", ascending=False).iloc[0] if len(performance) else None
    distances = [r for r in rows if r["distance_std"] is not None]
    stretched = max(distances, key=lambda r: abs(r["distance_std"])) if distances else None
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric("Dirección", f"{up} suben / {down} bajan", "Dirección de los últimos cierres diarios, con las mismas reglas anteriores; las débiles cuentan y los datos atrasados se avisan. Ayuda a ver amplitud.")
    with c2:
        metric("Más alineado", asset_label(aligned) if aligned and model["alignment"][aligned]["available"] else "Sin escalas vigentes", ALIGNMENT_LEGEND,
               model["alignment"][aligned]["label"] if aligned else None)
    with c3:
        metric("Más fuerte", asset_label(leader.symbol) if leader is not None else "Historia insuficiente",
               "Mayor diferencia de rendimiento frente al S&P 500 en las últimas 20 ruedas comunes. No es simplemente el más separado de su media.",
               f"{leader.relative_pp:+.2f} puntos" if leader is not None else None)
    with c4:
        metric("Más alejado", asset_label(stretched["symbol"]) if stretched else "Sin media válida",
               "Mayor separación absoluta de la media exponencial de 50 cierres, dividida por el desvío de 50 cierres. Ayuda a detectar precios estirados, no a predecir reversión.",
               f"{stretched['distance_std']:+.2f} desvíos" if stretched else None)
    st.subheader("Contexto económico")
    with DatabaseManager(db_path)._get_connection() as conn:
        macro = pd.read_sql_query("SELECT * FROM calc_macro WHERE series_id IN ('DGS10','T10Y2Y','VIXCLS') ORDER BY timestamp DESC", conn).drop_duplicates("series_id")
    for col, sid in zip(st.columns(3), ["DGS10", "T10Y2Y", "VIXCLS"]):
        with col:
            m = macro[macro.series_id == sid]
            if m.empty:
                metric(asset_label(sid), "Sin datos", help_text(sid))
            else:
                r = m.iloc[0]
                metric(asset_label(sid), f"{r.current_value:.2f}", help_text(sid, "cambio a un mes"), f"{r.change_1m:+.2f} en un mes")
                st.caption("Fecha del dato: " + str(r.timestamp)[:10])
    st.subheader("Fuerza relativa frente al S&P 500 — 20 ruedas")
    if len(performance):
        ranked = performance.sort_values("relative_pp")
        fig = go.Figure(go.Bar(x=ranked.relative_pp, y=[asset_label(s) for s in ranked.symbol], orientation="h",
            marker_color=["seagreen" if x >= 0 else "indianred" for x in ranked.relative_pp],
            customdata=ranked[["return_pct", "benchmark_pct", "last_session"]].to_numpy(),
            hovertemplate="%{y}<br>Diferencia: %{x:+.2f} puntos porcentuales<br>Índice: %{customdata[0]:+.2f}% · S&P: %{customdata[1]:+.2f}%<br>Hasta %{customdata[2]}<extra></extra>"))
        fig.update_layout(height=280, margin={"l": 0, "r": 15, "t": 10, "b": 35}, xaxis_title="Puntos porcentuales frente al S&P 500")
        st.plotly_chart(fig, width="stretch", key="pilot_relative_strength")
    summary = pd.DataFrame([{"Activo": asset_label(r["symbol"]), "Dirección": r["direction"], "Alineación": model["alignment"][r["symbol"]]["label"],
        "Distancia": f"{r['distance_pct']:+.2f}% · {r['distance_std']:+.2f} desvíos" if r["distance_pct"] is not None and r["distance_std"] is not None else "No disponible", "Dato": r["age"]} for r in rows])
    st.dataframe(summary, hide_index=True, width="stretch", column_config={
        "Activo": st.column_config.Column(help=help_text("activo")), "Dirección": st.column_config.Column(help=help_text("régimen")),
        "Alineación": st.column_config.Column(help=ALIGNMENT_LEGEND), "Distancia": st.column_config.Column(help="Lectura diaria: media de 50 cierres y desvío de 50 cierres. El VWAP de sesión se muestra abajo, en su propio instrumento."),
        "Dato": st.column_config.Column(help="Antigüedad calculada según ruedas, cierres y feriados reales del mercado."),
        "_index": st.column_config.Column(help=help_text("fila"))})
    with st.expander("Alineación por grupo de escalas"):
        st.write(ALIGNMENT_LEGEND)
        for symbol, a in model["alignment"].items():
            st.write("**" + asset_label(symbol) + "** — " + a["label"])
            st.caption("Componente 4h: " + asset_label(symbol, "4h"))
            for group, v in a["groups"].items():
                st.caption(f"{group}: {v['available']} de {v['total']} disponibles; {v['up']} hacia arriba, {v['down']} hacia abajo, {v['weak']} débiles.")
    st.info(FUTURES_NOTICE)
    render_detail(db_path, signature, pilot, ops, model["frames"])
    render_cointegration(db_path, signature, settings_json, minute, pilot, pairs["indices"])
    with st.expander("Fuentes, fechas, parámetros y calidad de los datos"):
        st.dataframe(model["quality"], hide_index=True, width="stretch", column_config={**{c: st.column_config.Column(help="Trazabilidad de la lectura del piloto: calendario, fuente y fecha usada.") for c in model["quality"].columns}, "_index": st.column_config.Column(help="Número de fila.")})
        st.json({"parámetros diarios": calc["regime"], "lectura piloto": pilot, "horario 4h": ops["platform_4h"], "sesión": ops["cme_vwap_session"]})
        ref_rows = []
        for reference in pilot["names"]:
            for tf in TFS:
                df = raw_data(db_path, reference, tf, signature)
                ref_rows.append({"Instrumento": asset_label(reference), "Escala": TF_LABELS[tf], "Fuente": "Yahoo",
                    "Última marca UTC": str(df.timestamp.max()) if len(df) else "Sin datos", "Velas": len(df)})
        st.dataframe(pd.DataFrame(ref_rows), hide_index=True, width="stretch", column_config={
            **{c: st.column_config.Column(help="Cobertura del instrumento de referencia; precio y volumen no se mezclan con el índice.") for c in ["Instrumento", "Escala", "Fuente", "Última marca UTC", "Velas"]},
            "_index": st.column_config.Column(help="Número de fila.")})
        st.write("Las recepciones antiguas, anteriores al formato UTC verificado de C0, no permiten comprobar retrospectivamente si la última vela se recibió terminada. Las nuevas recepciones sí distinguen valores provisionales.")
        st.write("La hora de cálculo corresponde a esta lectura en caché; las fotos se generan únicamente al actualizar.")
        notices = DatabaseManager(db_path).get_data_notices()
        wanted = set(assets["indices"]["activos"]) | set(pilot["names"])
        for n in notices:
            if n["asset"] in wanted:
                st.write(f"{asset_label(n['asset'])}: {n['message']}")
    with st.expander("Cómo leer esto"):
        st.write("Primero mirá si varios índices y escalas coinciden. La fuerza relativa compara rendimientos; estar lejos de una media no equivale a ser más fuerte. Las bandas de sesión describen distancia, no aseguran reversión. Revisá fechas, fuente y velas abiertas antes de comparar con tu plataforma.")
    with st.expander("Glosario"):
        for term in section_terms("indices", ["DGS10", "T10Y2Y", "VIXCLS"]):
            try:
                label = asset_label(term)
            except KeyError:
                label = term
            text = "Promedio de sesión ponderado por el volumen del mismo instrumento; reinicio según la sesión elegida." if term == "VWAP" else definition(term)
            st.markdown("**" + rich_text(label) + "** — " + rich_text(text), unsafe_allow_html=True)
    with st.expander("Vista anterior (para comparar)"):
        legacy_render("indices")
