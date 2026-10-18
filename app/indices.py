"""Pilotos guiados por config/sections.yaml, incluidos Equity y Small caps."""
import json
import subprocess
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml
from src.data.db_manager import DatabaseManager
from src.data.backup import ROOT
from src.calc.regime import get_latest_market_regime
from src.data.four_hour import prepare_stored, market_results, sufficient_history, policy, series_descriptor
from src.indices_math import (prepare_bars, freshness, alignment, daily_means, relative_performance,
    session_vwap, select_range, aggregate_4h, aggregate_regular_hours, unexpected_gaps, pair_analysis, ratio_analysis, ALIGNMENT_LEGEND, schedule)
from src.presentation import asset_label, pair_label, help_text, TF_LABELS, section_terms, rich_text, definition, explain_symbols
from src.pilot_math import common_performance, ratio_reading, select_exchange, crypto_vwap_readings, crypto_kpis, pair_coverage, cointegration_parameters, smallcaps_indicators
from src.argentina_math import argentina_indicators
from src.equity_math import regular_stock_bars, equity_indicators, session_for

TFS = ["1m", "5m", "15m", "1h", "4h", "1D"]
FUTURES_NOTICE = "Los futuros continuos de Yahoo pueden tener saltos en los cambios de contrato; no se verificó cómo los ajusta."
MULTIPLE_PAIRS_NOTE = "Al evaluar muchos pares, algunos aparecerán como «intermitentes» por azar. Tomalo como una pista débil, no como una señal."


def pilot_asset_label(pilot, symbol, timeframe=None, exchange=None):
    label = asset_label(symbol, timeframe)
    if pilot.get("exchanges"):
        exchange = exchange or pilot["exchanges"].get(symbol)
        label += " · " + (exchange.title() if exchange else "Exchange sin identificar")
    if pilot.get("regular_session") and timeframe == "4h":
        label += " · 4h de sesión"
    return label


def widget_key(section, name):
    """Conservar las claves del piloto original; aislar las demás secciones."""
    return name if section == "indices" else f"{section}_{name}"


def configs(section="indices"):
    assets_cfg = yaml.safe_load((ROOT / "config" / "assets.yaml").read_text(encoding="utf-8"))
    calc_cfg = yaml.safe_load((ROOT / "config" / "calc.yaml").read_text(encoding="utf-8"))
    sections_cfg = yaml.safe_load((ROOT / "config" / "sections.yaml").read_text(encoding="utf-8"))
    ops_cfg = yaml.safe_load((ROOT / "config" / "operations.yaml").read_text(encoding="utf-8"))
    pairs_cfg = yaml.safe_load((ROOT / "config" / "pairs.yaml").read_text(encoding="utf-8"))
    pilot_cfg = sections_cfg[section]
    return assets_cfg, calc_cfg, pilot_cfg, ops_cfg, pairs_cfg


@st.cache_data(ttl=900, show_spinner=False)
def raw_data(db_path, symbol, tf, signature):
    with DatabaseManager(db_path)._get_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM candles WHERE symbol=? AND timeframe=? ORDER BY timestamp", conn, params=(symbol, tf))
    df["timestamp"] = pd.to_datetime(df.timestamp, utc=True, format="mixed")
    return df


@st.cache_data(ttl=900, show_spinner=False)
def view_model(db_path, signature, settings_json, _minute, section="indices"):
    assets, calc, pilot, ops, pairs = json.loads(settings_json)
    now = pd.to_datetime(_minute, utc=True)
    daily, directions, frames, qualities = {}, {}, {}, []
    crypto = pilot.get("vwap_mode") == "utc"
    regular = pilot.get("regular_session", False)
    exchanges = {}
    rows = []
    for symbol in assets[section]["activos"]:
        calendar = pilot["calendars"][symbol]
        session = session_for(pilot, symbol)
        states = {}
        for tf in TFS:
            if tf not in pilot.get("asset_timeframes", {}).get(symbol, TFS):
                states[tf] = "sin datos"
                with DatabaseManager(db_path)._get_connection() as conn:
                    stored = conn.execute("SELECT COUNT(*), MAX(timestamp) FROM candles WHERE symbol=? AND timeframe=?", (symbol, tf)).fetchone()
                qualities.append({"Activo": asset_label(symbol, tf), "Escala": TF_LABELS[tf],
                    "Fuente": "Yahoo", "Último dato UTC": stored[1] or "—", "Calidad": pilot["asset_notices"][symbol],
                    "Velas guardadas": stored[0], "Dirección": "sin datos"})
                continue
            if regular and session and tf == "4h":
                base_tf = "15m"  # La 4h de sesión se arma desde la escala menor.
            elif regular and session is None and tf == "1h":
                base_tf = "5m"
            else:
                base_tf = tf
            raw = raw_data(db_path, symbol, base_tf, signature)
            if crypto:
                raw, info = select_exchange(raw, pilot["exchanges"][symbol])
                exchanges[(symbol, tf)] = info
            if regular:
                bars = regular_stock_bars(raw, symbol, tf, now, session)
                effective_calendar = session["calendar"] if session else "NYSE"
            elif tf == "4h":
                bars = prepare_stored(raw, symbol, now, calendar)
                effective_calendar = "CME_Equity" if policy(symbol) and policy(symbol)["method"] == "future_utc" else calendar
            else:
                bars = prepare_bars(raw, symbol, tf, calendar, now)
                effective_calendar = calendar
            frames[(symbol, tf)] = bars
            closed = bars[bars.closed]
            age = freshness(bars, tf, effective_calendar, now)
            result = market_results(closed, calc)[0] if tf == "4h" else get_latest_market_regime(closed, calc["regime"])
            state = result["direction"]
            states[tf] = state if not age["stale"] else "sin datos"
            source_label = info["exchange"].title() if crypto and info["exchange"] else "Sin exchange registrada" if crypto else "Yahoo"
            quality = result.get("error_message") or age["label"]
            if crypto and info["changed"]:
                quality += "; cambio de exchange: " + ", ".join(info["sources"]) + "; esperada " + info["expected"]
            qualities.append({"Activo": pilot_asset_label(pilot, symbol, tf, info["exchange"] if crypto else None), "Escala": TF_LABELS[tf],
                "Fuente": "Yahoo · " + asset_label(symbol, "4h") if tf == "4h" and policy(symbol) and policy(symbol)["method"] == "future_utc" else source_label,
                "Último dato UTC": str(age.get("last_data", "—")),
                "Calidad": quality, "Velas guardadas": len(closed), "Dirección": state})
            if tf == "1D":
                if pilot.get("deduplicate_daily_sessions"):
                    bars = bars.drop_duplicates("session", keep="last")
                daily[symbol] = daily_means(bars)
                d = daily[symbol].iloc[-1] if len(daily[symbol]) else None
                rows.append({"symbol": symbol, "direction": state, "daily_stale": age["stale"], "age": age["label"],
                    "distance_pct": float(d.distance_pct) if d is not None and pd.notna(d.distance_pct) else None,
                    "distance_std": float(d.distance_std) if d is not None and pd.notna(d.distance_std) else None,
                     "last_data": str(d.bar_end) if d is not None else "—"})
                if crypto:
                    rows[-1]["exchange"] = info["exchange"]
        directions[symbol] = alignment(states)
    series = {s: d.set_index("session").close for s, d in daily.items()}
    benchmark_symbol = pilot.get("benchmark", "^GSPC")
    benchmark = series.get(benchmark_symbol, pd.Series(dtype=float))
    if benchmark.empty:
        # Benchmark externo a la sección (p. ej. dólar DTWEXBGS en Metales): leer su historia diaria de FRED.
        with DatabaseManager(db_path)._get_connection() as conn:
            frows = pd.read_sql_query("SELECT timestamp, value FROM fred_series WHERE series_id = ? ORDER BY timestamp", conn, params=(benchmark_symbol,))
        if len(frows):
            frows = frows[pd.to_datetime(frows.timestamp, utc=True) <= now]
            dates = pd.to_datetime(frows.timestamp, utc=True).dt.strftime("%Y-%m-%d")
            benchmark = pd.Series(frows.value.to_numpy(dtype=float), index=dates.to_numpy()).groupby(level=0).last()
        elif regular:
            bars = prepare_bars(raw_data(db_path, benchmark_symbol, "1D", signature), benchmark_symbol, "1D", pilot["calendars"].get(benchmark_symbol, "NYSE"), now)
            benchmark = daily_means(bars).set_index("session").close
    perf = relative_performance(series, benchmark, pilot["relative_strength_sessions"])
    for spec in pilot.get("ratios", []):
        for symbol in (spec["y"], spec["x"]):
            if symbol not in daily:
                bars = prepare_bars(raw_data(db_path, symbol, "1D", signature), symbol, "1D", pilot["calendars"][symbol], now)
                daily[symbol] = daily_means(bars)
    between = common_performance(series, pilot["relative_strength_sessions"]) if pilot.get("compare_all_assets") else None
    ratios = {spec["label"]: ratio_reading(daily, spec)[0] for spec in pilot.get("ratios", [])}
    vwaps = crypto_vwap_readings(frames, assets[section]["activos"], pilot["vwap"]["minimum_volume_coverage"]) if crypto else {}
    argentina = argentina_indicators(frames, rows, pilot, assets["argentina"]["pares"], assets["argentina"]["equivalencias"], now) \
        if pilot.get("summary_layout") == "argentina" else None
    return {"rows": rows, "alignment": directions, "quality": pd.DataFrame(qualities), "frames": frames,
            "daily": daily, "performance": perf, "benchmark_last_session": str(benchmark.index.max()) if len(benchmark) else None,
            "performance_between": between,
            "ratios": ratios, "session_vwaps": vwaps, "exchanges": exchanges,
            "pair_coverage": pair_coverage(frames, pairs[section], pilot) if crypto else [],
            "equity": equity_indicators(rows, daily, frames, benchmark, pilot) if pilot.get("summary_layout") == "equity" else None,
            "smallcaps": smallcaps_indicators(rows, daily, pilot) if pilot.get("summary_layout") == "smallcaps" else None,
            "argentina": argentina,
            "calculated_at": pd.Timestamp.now(tz="UTC").isoformat()}


@st.cache_data(ttl=900, show_spinner=False)
def cointegration_model(db_path, signature, settings_json, _minute, y, x, tf="1D"):
    assets, calc, pilot, ops, pairs = json.loads(settings_json)
    values = []
    crypto = pilot.get("vwap_mode") == "utc"
    sources = []
    for symbol in [y, x]:
        raw = raw_data(db_path, symbol, tf, signature)
        if crypto:
            raw, info = select_exchange(raw, pilot["exchanges"][symbol])
            sources.append(info["exchange"])
        bars = prepare_stored(raw, symbol, _minute, pilot["calendars"][symbol]) if tf == "4h" else prepare_bars(raw, symbol, tf, pilot["calendars"][symbol], _minute)
        closed = bars[bars.closed]
        if tf == "1D" and pilot.get("deduplicate_daily_sessions"):
            closed = closed.drop_duplicates("session", keep="last")
        values.append(closed.set_index("session" if tf == "1D" else "timestamp").close)
    common = pd.concat([value.rename(str(i)) for i, value in enumerate(values)], axis=1, join="inner").dropna()
    common = common[(common > 0).all(axis=1)]
    params = cointegration_parameters(pilot, y, x, tf, len(common))
    result = pair_analysis(*values, params)
    if crypto:
        result.update({"timeframe": tf, "exchanges": sources, "required_blocks": params["required_blocks"],
                       "block_size": params.get("block_size", params["primary_window"])})
    return result


def update_section_pilot(db_path, quick=False, section="indices"):
    pilot = configs(section)[2]
    label = pilot["label"]
    requested_tfs = ["1h", "1D"] if quick else TFS
    tfs = ",".join(requested_tfs)
    progress = st.progress(0, text=f"Actualizando únicamente {label.lower()}...")
    steps = [[sys.executable, str(ROOT / "update_data.py"), "--seccion", section, "--tf", tfs, "--db", db_path],
             [sys.executable, str(ROOT / "run_calc.py"), "--seccion", section, "--tf", tfs, "--db", db_path]]
    if section == "indices":
        steps.append([sys.executable, str(ROOT / "update_indices_references.py"), "--tf", tfs, "--db", db_path])
    texts = [f"{label} descargados; recalculando...", f"{label} recalculados", "Actualizando referencias negociables...", "Proceso terminado"]
    failures = []
    for i, command in enumerate(steps):
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        progress.progress((i + 1) / len(steps), text=texts[i])
        if result.returncode:
            failures.append(f"{Path(command[1]).name}: código {result.returncode}\n{result.stderr[-1500:]}\n{result.stdout[-1500:]}")
    st.cache_data.clear()
    st.session_state[widget_key(section, "pilot_update_message")] = "Actualización parcial: revisá fuentes y fechas." if failures else f"{label} actualizados."
    st.session_state[widget_key(section, "pilot_update_errors")] = failures
    st.rerun()


def metric(label, value, explanation, delta=None):
    st.metric(label, value, delta, help=explanation)


def render_crypto_summary(pilot, model):
    kpis = crypto_kpis(model["rows"], model["alignment"], model["ratios"], model["session_vwaps"])
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        metric("Dirección", f"{kpis['up']} de {kpis['total']} suben / {kpis['down']} bajan",
               "Conteo de direcciones de los últimos cierres diarios disponibles, incluidas las débiles. Revisá su fecha: no es precio en vivo.")
    with c2:
        symbol = kpis["most_aligned"]
        source = next((r.get("exchange") for r in model["rows"] if r["symbol"] == symbol), None)
        metric("Más alineado", pilot_asset_label(pilot, symbol, exchange=source) if symbol else "Sin escalas vigentes", ALIGNMENT_LEGEND,
               kpis["alignment"]["label"] if symbol else None)
    for column, key, title in [(c3, "eth_btc", "ETH/BTC"), (c4, "sol_btc", "SOL/BTC")]:
        with column:
            ratio = kpis[key] or {}
            metric(title, f"{ratio['ratio']:.6f}" if ratio.get("ratio") is not None else "Sin datos",
                   "Ratio de cierres diarios comunes del mismo período. La distancia a su media y el percentil aparecen en el detalle del ratio.",
                   f"{ratio['distance_pct']:+.2f}% vs media" if ratio.get("distance_pct") is not None else None)
    with c5:
        v = kpis["furthest_vwap"]
        metric("Mayor separación del VWAP", pilot_asset_label(pilot, v["symbol"], exchange=v["exchange"]) if v else "Sin VWAP válido",
               "Mayor separación porcentual absoluta entre las seis criptos, comparando la misma sesión UTC y corte común de cierres. El precio y volumen pertenecen a la misma exchange; se excluyen sesiones parciales.",
               f"{v['distance_pct']:+.2f}%" if v else None)
    if kpis["furthest_vwap"]:
        v = kpis["furthest_vwap"]
        st.caption(f"VWAP comparado de la sesión {v['session']} · corte común {v['common_cutoff']} · base {TF_LABELS[v['base_tf']]} · reinicio 00:00 UTC. Describe los últimos datos disponibles, no garantiza una reversión.")


def render_equity_summary(pilot, model, section):
    reading = model["equity"]
    k = reading["kpis"]
    columns = st.columns(5)
    with columns[0]:
        metric("Sectores que suben", f"{k['sector_up']} de {k['sector_total']}",
               "Dirección de los últimos cierres diarios de los once ETF sectoriales. Los cierres atrasados se avisan; no es cotización en vivo.")
    for column, field, title in [(columns[1], "leader", "Sector líder frente al S&P 500"), (columns[2], "laggard", "Sector rezagado frente al S&P 500")]:
        with column:
            row = k[field]
            metric(title, asset_label(row["symbol"]) if row else "Historia común insuficiente",
                   "Rendimiento menos rendimiento del S&P 500 sobre las mismas veinte ruedas comunes de todos los sectores y el benchmark; se mide en puntos porcentuales.",
                   f"{row['relative_pp']:+.2f} puntos" if row else None)
    with columns[3]:
        metric("Fortaleza de las siete tecnológicas", f"{k['mega_up']} de {k['mega_total']} suben",
               "Cuenta las direcciones diarias de Apple, Microsoft, Nvidia, Alphabet, Amazon, Meta y Tesla, por separado de los sectores.")
    with columns[4]:
        row = k["stretched"]
        metric("Mayor separación de la media", asset_label(row["symbol"]) if row else "Sin media válida",
               "Máxima separación absoluta frente a la EMA de 50 cierres diarios, dividida por el desvío de 50 cierres. No es fuerza relativa ni predicción de reversión.",
               f"{row['distance_pct']:+.2f}% · {row['distance_std']:+.2f} desvíos" if row else None)
    if k["start_session"]:
        st.caption(f"Rendimiento sectorial comparado: {k['start_session']} → {k['last_session']} · {pilot['relative_strength_sessions']} ruedas comunes de los once sectores y el S&P 500.")
    st.subheader("Mapa de calor sectorial: distancia a la EMA de 50 cierres")
    heat = reading["heatmap"]
    values = heat[TFS].to_numpy(dtype=float)
    finite = np.abs(values[np.isfinite(values)])
    scale = max(1., float(finite.max())) if len(finite) else 1.
    fig = go.Figure(go.Heatmap(z=values, x=[TF_LABELS[tf] for tf in TFS], y=[asset_label(s) for s in heat.symbol],
                             colorscale="RdYlGn", zmin=-scale, zmax=scale, zmid=0,
                             colorbar={"title": "% vs EMA"},
                             hovertemplate="%{y}<br>%{x}: %{z:+.2f}% frente a su EMA de 50 cierres<extra></extra>"))
    fig.update_layout(height=420, plot_bgcolor="#ededed", yaxis={"autorange": "reversed"})
    st.plotly_chart(fig, width="stretch", key=widget_key(section, "pilot_sector_heatmap"))
    st.caption("Verde: precio por encima de su media; rojo: por debajo; gris: historia insuficiente. Sectores ordenados por distancia diaria, de mayor a menor. La intensidad es separación, no una orden de compra o venta.")


def render_smallcaps_summary(pilot, model):
    k = model["smallcaps"]
    cols = st.columns(4)
    with cols[0]:
        metric("ETF que suben", f"{k['up']} de {k['total']}", "Direcciones diarias de IWM, IJR, IWO e IWN. Se avisa si el cierre disponible es antiguo.")
    for column, field, title in ((cols[1], "relative", "Fuerza relativa " + asset_label("IWM") + " / " + asset_label("^GSPC")),
                                 (cols[2], "growth_value", "Crecimiento frente a valor " + asset_label("IWO") + " / " + asset_label("IWN"))):
        with column:
            row = k[field]
            metric(title, f"{row['ratio']:.6f}" if row["ratio"] is not None else "Sin datos comunes",
                   "Cociente de cierres diarios comunes; su distancia a la media, percentil y tendencia se muestran en el detalle del ratio.",
                   f"{row['distance_pct']:+.2f}% vs media · {row['trend']}" if row["distance_pct"] is not None else None)
    with cols[3]:
        row = k["stretched"]
        metric("Mayor separación de la media", asset_label(row["symbol"]) if row else "Sin media válida",
               "Mayor separación absoluta de la EMA diaria normalizada por el desvío de 50 cierres. No equivale a fuerza relativa ni a reversión segura.",
               f"{row['distance_pct']:+.2f}% · {row['distance_std']:+.2f} desvíos" if row else None)


def render_argentina_summary(pilot, model):
    k = model["argentina"]
    median = k["median"]
    cols = st.columns(4)
    with cols[0]:
        metric("CCL implícito mediano", f"${median['median']:,.1f}" if median["median"] else "Historia insuficiente",
               f"Mediana de las {len(k['ccl_by_company'])} empresas el {median['last_session']}, con el cierre de cada mercado de esa misma fecha y la equivalencia configurada.",
               f"{median['change_5']:+.2f}% en {k['ccl_change_sessions']} ruedas" if median["change_5"] is not None else None)
    with cols[1]:
        metric("Distancia del CCL a su media", f"{median['distance_std']:+.2f}" if median["distance_std"] is not None else "Sin dispersión",
               f"Cociente entre la mediana y su media simple de {k['ccl_window']} sesiones, dividido por el desvío muestral de las mismas sesiones.")
    with cols[2]:
        metric("Acciones locales que suben", f"{k['local_up']} de {k['local_total']}",
               "Direcciones diarias de las cinco acciones locales en pesos. Los cierres atrasados se avisan; no es cotización en vivo.",
               f"{k['local_down']} bajan" if k["local_down"] else None)
    with cols[3]:
        row = k["stretched"]
        metric("Mayor separación de la media", asset_label(row["symbol"]) if row else "Sin media válida",
               "Mayor separación absoluta frente a la EMA de 50 cierres diarios, dividida por el desvío de 50 cierres. No es el CCL ni predice reversión.",
               f"{row['distance_pct']:+.2f}% · {row['distance_std']:+.2f} desvíos" if row else None)
    st.info("El CCL es un tipo de cambio con tendencia: un z alto indica que subió rápido, no que vaya a revertir.")
    st.subheader("Dólar implícito por empresa (CCL)")
    records = []
    for row in k["ccl_by_company"]:
        records.append({"Empresa": asset_label(row["local"]) if row.get("local") else row["company"], "CCL implícito": row["ccl"],
                        "% vs mediana": row["vs_median_pct"],
                        "Estado": "Se aleja de la mediana" if row["highlight"] else "Dentro del umbral"})
    table = pd.DataFrame(records)
    threshold = k["dispersion_threshold_pct"]
    yellow = k.get("dispersion_yellow_pct", threshold)
    def away(value):
        if not (isinstance(value, (int, float)) and pd.notna(value)):
            return ""
        size = abs(value)
        if size > threshold:
            return "background-color: #f8cbad"
        return "background-color: #ffe699" if size > yellow else ""
    styled = table.style.map(away, subset=["% vs mediana"])
    st.dataframe(styled.format({"CCL implícito": "{:,.1f}", "% vs mediana": "{:+.2f}%"}, na_rep="—"),
                 hide_index=True, width="stretch", column_config={
                     "Empresa": st.column_config.Column(help=help_text("activo")),
                     "CCL implícito": st.column_config.Column(help="Precio local en pesos multiplicado por las acciones del certificado y dividido por el precio del ADR, en la misma fecha."),
                     "% vs mediana": st.column_config.Column(help=f"Desvío de esa empresa contra la mediana de las cinco. Amarillo si supera {yellow:.0g}% y naranja si supera el umbral de {threshold:.0g}%."),
                     "Estado": st.column_config.Column(help="Solo describe separación entre empresas; no indica calidad ni precio justo."),
                     "_index": st.column_config.Column(help=help_text("fila"))})
    reference = k["dispersion_reference"]
    if reference.get("sessions"):
        counts = (f"naranja desde {threshold:.0g}% en {reference['above_threshold']} de {reference['sessions']} observaciones"
                  f" ({reference['above_threshold_share']:.1f}%)"
                  + (f" y amarillo desde {yellow:.0g}% en {reference['above_yellow']} ({reference['above_yellow_share']:.1f}%)"
                     if reference.get("above_yellow") is not None else ""))
        st.caption(f"Dispersión real de las últimas {reference['sessions']} sesiones (cinco empresas por sesión): "
                   f"mediana {reference['median']:.2f}%, percentil 90 {reference['p90']:.2f}%, percentil 95 {reference['p95']:.2f}%, "
                   f"percentil 99 {reference['p99']:.2f}%, máximo {reference['max']:.2f}%. Se superó el nivel " + counts + ".")
    window = k["intraday_window"]
    if window["start"]:
        st.caption(f"CCL intradía: velas de quince minutos solo dentro de la ventana común BYMA–NYSE de {window['start']} a {window['end']} UTC. "
                   "Fuera de esa ventana no hay CCL intradía y solo se usa el cierre del día.")
        rows_intraday = [{"Empresa": asset_label(row["local"]) if row.get("local") else row["company"],
                          "CCL intradía": k["intraday_ccl"].get(row["company"], {}).get("last"),
                          "Velas de 15m": k["intraday_ccl"].get(row["company"], {}).get("bars"),
                          "Corte UTC": k["intraday_ccl"].get(row["company"], {}).get("timestamp")}
                         for row in k["ccl_by_company"]]
        if rows_intraday:
            intraday_median = k["intraday_median"]["median"]
            st.dataframe(pd.DataFrame(rows_intraday), hide_index=True, width="stretch", column_config={
                "Empresa": st.column_config.Column(help=help_text("activo")),
                "CCL intradía": st.column_config.Column(help="Misma fórmula, con velas de quince minutos dentro de la ventana común de ambos mercados."),
                "Velas de 15m": st.column_config.Column(help="Velas comunes usadas; menos cantidad indica liquidez baja o huecos del proveedor."),
                "Corte UTC": st.column_config.Column(help="Última vela común de la ventana."),
                "_index": st.column_config.Column(help=help_text("fila"))})
            st.caption(f"Mediana intradía de esa ventana: {intraday_median:,.1f}." if intraday_median else "Sin mediana intradía en la ventana común.")
    else:
        st.info("No hay ventana común BYMA–NYSE con datos de ambos mercados en los últimos días; el CCL intradía queda sin mostrar y el diario sigue disponible.")


def render_ratios(pilot, daily, section):
    for spec in pilot.get("ratios", []):
        y, x = spec["y"], spec["x"]
        label = asset_label(y) + " / " + asset_label(x) if section == "smallcaps" else spec["label"]
        st.subheader(label, help=help_text("ratio", y, x))
        reading, result = ratio_reading(daily, spec)
        if result.empty or pd.isna(result["mean"].iloc[-1]):
            st.info("Historia común insuficiente para calcular el ratio y su distancia a la media.")
            continue
        last = result.iloc[-1]
        c1, c2, c3 = st.columns(3)
        with c1:
            metric("Ratio " + label, f"{last.ratio:.4f}", "Cociente de los cierres diarios de ambos instrumentos en la misma sesión.")
        with c2:
            metric("Distancia a la media del ratio", f"{last.distance_pct:+.2f}%", f"Separación del cociente frente a su media simple de {spec['window']} cierres comunes.")
        with c3:
            metric("Distancia por desvío del ratio", f"{last.distance_std:+.2f}" if pd.notna(last.distance_std) else "Sin dispersión",
                   f"Separación del cociente dividida por el desvío muestral de {spec['window']} cierres comunes; no se usa ATR sintético.")
        subject = "activo" if pilot.get("vwap_mode") == "utc" else "ETF" if section == "smallcaps" else "metal"
        st.caption(f"Última sesión común: {result.index[-1]} · Media y desvío: {spec['window']} cierres comunes. Si sube el ratio, el primer {subject} gana terreno frente al segundo; no es una señal automática.")
        if spec.get("percentile_window"):
            if pilot.get("exchanges"):
                st.caption("Exchanges del ratio: " + pilot_asset_label(pilot, y, exchange=reading.get("y_exchange")) + " / " + pilot_asset_label(pilot, x, exchange=reading.get("x_exchange")))
            else:
                st.caption("Fuentes del ratio: " + asset_label(y) + " / " + asset_label(x) + " · Yahoo, sobre cierres diarios comunes.")
            metric("Percentil de " + label, f"{reading['percentile']:.1f}%" if reading.get("percentile") is not None else "Historia insuficiente",
                   f"Posición de la distancia por desvío del ratio (con signo) frente a sus últimas {spec['percentile_window']} observaciones diarias válidas. No se usa ATR sintético.")
        if spec.get("trend_period"):
            st.caption("Tendencia del ratio: " + reading["trend"] + " · " + reading["trend_method"])
        visible = result.tail(spec.get("chart_sessions", 500))
        fig = go.Figure()
        for column, title in [("ratio", label), ("mean", f"Media de {spec['window']} cierres")]:
            fig.add_trace(go.Scatter(x=visible.index, y=visible[column], name=title))
        fig.update_layout(height=280, yaxis_title="Cociente de precios", xaxis_title="Sesión común")
        st.plotly_chart(fig, width="stretch", key=widget_key(section, f"pilot_ratio_{y}_{x}"))


def render_detail(db_path, signature, pilot, ops, frames, section="indices"):
    def pk(name):
        return widget_key(section, name)
    st.subheader("Detalle por activo")
    symbols = list(pilot["references"])
    c1, c2, c3 = st.columns(3)
    selected_tf = st.session_state.get(pk("pilot_tf"))
    crypto = pilot.get("vwap_mode") == "utc"
    regular = pilot.get("regular_session", False)
    symbol = c1.selectbox("Activo", symbols, format_func=lambda s: pilot_asset_label(pilot, s, selected_tf), key=pk("pilot_asset"), help=help_text("activo"))
    available_tfs = pilot.get("asset_timeframes", {}).get(symbol, TFS)
    tf = c2.selectbox("Temporalidad", available_tfs, index=available_tfs.index(pilot.get("default_timeframe", "1D")), format_func=lambda t: TF_LABELS[t], key=pk("pilot_tf"), help=help_text("temporalidad"))
    if symbol in pilot.get("asset_notices", {}):
        st.info(pilot["asset_notices"][symbol])
    period = c3.selectbox("Rango", ["Predeterminado", "Último mes", "Últimos 3 meses", "Último año", "Personalizado"], key=pk("pilot_range"),
                          help="El rango se mide en sesiones o tiempo, no en un número fijo de velas.")
    now = pd.Timestamp.now(tz="UTC")
    start, end = None, None
    if period != "Predeterminado" and period != "Personalizado":
        start = now - pd.DateOffset(months={"Último mes": 1, "Últimos 3 meses": 3, "Último año": 12}[period])
    if period == "Personalizado":
        chosen = st.date_input("Desde / hasta", value=(now.date()-pd.Timedelta(days=30), now.date()), key=pk("pilot_dates"))
        if len(chosen) != 2:
            st.info("Elegí el comienzo y el fin del rango.")
            return
        start = pd.to_datetime(chosen[0], utc=True)
        end = pd.to_datetime(chosen[1], utc=True) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    reference = symbol
    mode = "utc" if crypto else "regular" if regular else ops["cme_vwap_session"]["default"] or "complete"
    if crypto:
        st.caption("VWAP de cripto: reinicio a las 00:00 UTC · mercado 24/7 · precio y volumen de la misma exchange.")
    if regular:
        st.caption("Sesión regular: 09:30–16:00 Nueva York, sin premercado; ajustada a feriados, cierres anticipados y cambio de hora. VWAP del mismo ETF o acción.")
    if tf != "1D" and not crypto and not regular:
        options = pilot["references"][symbol] + ([] if tf == "4h" and policy(symbol) and policy(symbol)["method"] == "future_utc" else [symbol])
        c1, c2 = st.columns(2)
        reference = c1.selectbox("Instrumento del gráfico", options, format_func=asset_label, key=pk("pilot_reference_" + symbol),
            help="El gráfico, el precio y el volumen pertenecen siempre al mismo instrumento. El índice no recibe el VWAP de un futuro.")
        sessions = pilot.get("vwap_sessions", ["complete", "regular"])
        default_session = mode if reference.endswith("=F") else "regular"
        session_index = sessions.index(default_session) if default_session in sessions else 0
        selected = c2.selectbox("Sesión del VWAP de futuros", sessions, index=session_index,
            format_func=lambda s: "Completa: reinicio 18:00 Nueva York" if s == "complete" else "Regular: 09:30–16:00 Nueva York",
            disabled=not reference.endswith("=F"), key=pk("pilot_vwap_session_" + reference),
            help="Sesión completa hasta las 17:00 del día siguiente; sesión regular de acciones hasta las 16:00. Se ajusta al cambio de hora de Nueva York.")
        mode = selected if reference.endswith("=F") else "regular"
        st.caption("Sesión de VWAP: **configuración provisional** (elegida para empezar; la confirmás vos).")
    if reference == "NQ=F":
        st.info("Comparación de " + asset_label(reference) + " con tu CFD USTEC: pendiente de tu validación con el bróker.")
    cal = pilot["calendars"][reference]
    can_vwap = (reference in pilot["names"] or reference == "IWM" or reference in pilot.get("vwap_instruments", [])) and reference not in pilot.get("vwap_disabled", [])
    base_tf = "1h" if tf == "4h" else tf
    if tf == "1h" and mode == "regular" and reference.endswith("=F"):
        base_tf = "5m"
    data = None
    chart_label = asset_label(reference)
    if regular:
        base_tf = "5m" if tf == "1h" else tf
        session_spec = session_for(pilot, reference)
        if session_spec and tf == "4h":
            data = regular_stock_bars(raw_data(db_path, reference, "15m", signature), reference, tf, now, session_spec)
            st.caption(pilot_asset_label(pilot, reference, tf) + " · " + session_spec["four_hour_label"] +
                       " · construida desde velas de quince minutos de la misma sesión; la segunda puede ser más corta.")
            enough, required = sufficient_history(data[data.closed], configs(section)[1])
            if not enough:
                st.warning(f"Historia insuficiente en 4h de sesión: se requieren {required} velas.")
        else:
            data = regular_stock_bars(raw_data(db_path, reference, base_tf, signature), reference, tf, now, session_spec)
            chart_label = pilot_asset_label(pilot, reference, tf)
            if tf == "4h":
                with DatabaseManager(db_path)._get_connection() as conn:
                    descriptor = series_descriptor(reference, conn)
                st.caption(chart_label + " · " + descriptor["label"])
                enough, required = sufficient_history(data[data.closed], configs(section)[1])
                if not enough:
                    st.warning(f"Historia insuficiente en 4h de sesión: se requieren {required} velas.")
            if tf == "1h":
                st.caption(f"Horas de sesión reconstruidas desde {session_label(pilot, reference).split()[-3] if session_spec else '09:30'} usando velas de cinco minutos; el último bloque puede ser parcial.")
    elif crypto:
        raw, source_info = select_exchange(raw_data(db_path, reference, tf, signature), pilot["exchanges"][reference])
        data = prepare_stored(raw, reference, now, cal) if tf == "4h" else prepare_bars(raw, reference, tf, cal, now)
        chart_label = pilot_asset_label(pilot, reference, tf, source_info["exchange"])
        st.caption("Fuente del precio y volumen: " + chart_label)
        if source_info["changed"]:
            st.warning("Cambio de exchange para " + asset_label(reference) + ": historial " + ", ".join(source_info["sources"]) + "; fuente usada " + str(source_info["exchange"]) + "; preferida " + source_info["expected"] + ". No se mezclan volúmenes.")
    elif tf == "4h":
        spec = policy(symbol)
        storage = symbol if spec and spec["method"] == "future_utc" and reference == spec["reference"] else reference
        data = prepare_stored(raw_data(db_path, storage, "4h", signature), storage, now, cal)
        chart_label = asset_label(storage, "4h")
        with DatabaseManager(db_path)._get_connection() as conn:
            descriptor = series_descriptor(storage, conn)
        st.caption(chart_label + " · " + descriptor["label"])
        if descriptor["method"] == "future_utc":
            st.caption("Horario de plataforma: " + descriptor["timezone"] + " · " + "/".join(descriptor["starts"]) + " · validación pendiente.")
        enough, required = sufficient_history(data[data.closed], configs(section)[1])
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
    labels = visible.timestamp.tolist() if crypto else visible.timestamp.dt.strftime("%Y-%m-%d %H:%M UTC").tolist()
    fig = go.Figure(go.Candlestick(x=labels, open=visible.open, high=visible.high, low=visible.low, close=visible.close, name=chart_label))
    open_bars = visible[~visible.closed]
    if len(open_bars):
        fig.add_trace(go.Scatter(x=open_bars.timestamp if crypto else open_bars.timestamp.dt.strftime("%Y-%m-%d %H:%M UTC"), y=open_bars.close,
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
            if crypto:
                raw, _ = select_exchange(raw, pilot["exchanges"][reference], requested=source_info["exchange"])
            prepared = prepare_bars(raw, reference, candidate, cal, now, regular=regular or (mode == "regular" and reference.endswith("=F")))
            if len(prepared) and prepared.timestamp.min() <= visible.timestamp.min() - pd.Timedelta(days=1):
                source, chosen_tf = prepared, candidate
                break
        if source is None:
            raw = raw_data(db_path, reference, base_tf, signature)
            if crypto:
                raw, _ = select_exchange(raw, pilot["exchanges"][reference], requested=source_info["exchange"])
            source = prepare_bars(raw, reference, base_tf, cal, now,
                regular=regular or (mode == "regular" and reference.endswith("=F")))
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
        if crypto:
            st.caption(f"VWAP de {pilot_asset_label(pilot, reference, exchange=source_info['exchange'])} · precio típico y volumen de la misma exchange · base: {TF_LABELS[chosen_tf]} · sesión UTC, reinicio 00:00.")
        else:
            st.caption(f"VWAP de {reference} — {asset_label(reference)} · precio típico y volumen del mismo instrumento · base: {TF_LABELS[chosen_tf]} · sesión {mode}.")
    else:
        st.info("VWAP no disponible para este índice. No se mezcla su precio con el volumen de otro instrumento.")
    axis = {"type": "date", "rangeslider": {"visible": False}, "nticks": 8} if crypto else {"type": "category", "categoryorder": "array", "categoryarray": labels, "rangeslider": {"visible": False}, "nticks": 8}
    fig.update_layout(height=520, xaxis=axis,
                      title=chart_label + " — " + TF_LABELS[tf], yaxis_title="Precio", legend={"orientation": "h"})
    st.plotly_chart(fig, width="stretch", key=pk("pilot_price_chart"))
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
        subject = pilot.get("detail_subject", "El índice")
        st.write(f"{subject} está {abs(pct):.2f}% {'sobre' if pct >= 0 else 'bajo'} su media de 50 cierres.")
    if tf != "1D":
        raw = raw_data(db_path, reference, "1D", signature)
        if crypto:
            raw, _ = select_exchange(raw, pilot["exchanges"][reference], requested=source_info["exchange"])
        long_daily = daily_means(prepare_bars(raw, reference, "1D", cal, now))
        if len(long_daily) and pd.notna(long_daily.ema200.iloc[-1]):
            long_pct = (visible.close.iloc[-1] / long_daily.ema200.iloc[-1] - 1) * 100
            st.caption(f"Línea base larga del mismo instrumento: {long_pct:+.2f}% frente a la media de 200 cierres diarios, hasta {long_daily.session.iloc[-1]}.")


def render_cointegration(db_path, signature, settings_json, minute, pilot, pairs, section="indices", model=None):
    def pk(name):
        return widget_key(section, name)
    with st.expander(f"Relaciones entre {pilot.get('noun', 'índices')}: corto y largo plazo"):
        crypto = pilot.get("vwap_mode") == "utc"
        if crypto:
            records = []
            for item in model["pair_coverage"]:
                records.append({"Par": pilot_asset_label(pilot, item["y"], exchange=item["exchanges"][0]) + " / " + pilot_asset_label(pilot, item["x"], exchange=item["exchanges"][1]),
                                "Escala": TF_LABELS[item["tf"]], "Cierres comunes": item["bars"],
                                "Bloques disponibles": item["blocks"], "Velas por bloque": item["block_size"],
                                "Bloques requeridos": item["required_blocks"], "Último cierre común": item["last_common"],
                                "Cobertura": ("Historia limitada / provisional" if item["required_blocks"] < pilot["cointegration"]["required_blocks"] else "Suficiente") if item["enough"] else "Historia insuficiente"})
            coverage = pd.DataFrame(records)
            st.dataframe(coverage, hide_index=True, width="stretch", column_config={
                **{column: st.column_config.Column(help="Cobertura de cierres comunes terminados y positivos, de la exchange indicada. Los bloques son disjuntos; Solana usa cuatro solo cuando no llega a cinco, con aviso de historia limitada.") for column in coverage.columns},
                "_index": st.column_config.Column(help="Número de fila de la cobertura del par.")})
            st.caption("Bloques: 1000 velas en 1h y 500 en 4h y diario. Se evalúan todos los bloques completos disponibles, y el estado reciente se basa en los últimos cinco. Solana usa cuatro únicamente cuando su historia tiene entre cuatro y cinco bloques, con estado máximo Estable (provisional).")
        scales = pilot.get("cointegration_scales", ["1D", "1h", "4h"])
        tf = st.selectbox("Escala de la relación", scales, format_func=lambda t: TF_LABELS[t], key=pk("pilot_pair_tf"),
                          help="Bloques disjuntos de 1000 velas en 1h y 500 en 4h y diario. La regla normal requiere cinco; Solana admite cuatro con historia limitada cuando no llega a cinco." if crypto else "La estabilidad se evalúa solo en diario. En una y cuatro horas se informa historia insuficiente.")
        if tf != "1D" and not crypto:
            st.info("Historia insuficiente para evaluar estabilidad")
            return
        pair = st.selectbox(pilot.get("pair_selector_label", "Par de índices"), list(range(len(pairs))),
                            format_func=lambda i: (pilot_asset_label(pilot, pairs[i]["y"]) + " / " + pilot_asset_label(pilot, pairs[i]["x"])) if crypto else pair_label(pairs[i]["y"], pairs[i]["x"]),
                            key=pk("pilot_pair"), help=help_text("par", "cointegración"))
        p = pairs[pair]
        requested = (p["y"], p["x"])
        if crypto:
            requested += (tf,)
        if st.button("Mostrar comparación y gráficos del par", key=pk("pilot_load_pair"),
                     help="Calcula la relación en la escala seleccionada solo con historia suficiente. La primera consulta puede tardar; después queda en caché." if crypto else "Calcula la relación diaria y los gráficos móviles. La primera consulta puede tardar; después queda en caché."):
            st.session_state[pk("pilot_loaded_pair")] = requested
        if st.session_state.get(pk("pilot_loaded_pair")) != requested:
            st.caption("Elegí el par y pedí la comparación. Así no se recalcula su historia mientras mirás los indicadores principales.")
            return
        with st.spinner("Comparando ventanas y la línea base larga..."):
            result = cointegration_model(db_path, signature, settings_json, minute, p["y"], p["x"], tf=tf)
        st.write("**Estado: " + result["state"] + "**")
        if result.get("binomial_evidence"):
            evidence = result["binomial_evidence"]
            threshold = evidence["minimum_confirmed"]
            st.caption(f"Evidencia binomial: {evidence['confirmed']} bloques confirmados de {evidence['evaluated']} evaluados · esperables por azar: {evidence['expected_by_chance']:.2f} · mínimo significativo: {threshold if threshold is not None else 'no disponible'} · {evidence['conclusion']}.")
        if result.get("all_block_statistics") is not None:
            statistics = result["all_block_statistics"]
            if statistics["confirmation_pct"] is not None:
                st.caption(f"Confirmó {statistics['confirmation_pct']:.1f}% de {statistics['available']} bloques disponibles · {statistics['evaluated']} evaluados · {statistics['confirmed']} confirmados en ambos órdenes.")
            else:
                st.caption(f"Porcentaje de todos los bloques no comprobable: {statistics['evaluated']} de {statistics['available']} evaluados · {statistics['confirmed']} confirmados · {statistics['failed']} pruebas inválidas.")
            recent = result["recent_block_statistics"]
            st.caption(f"Tramo reciente: {recent['confirmed']} confirmados de {recent['available']} bloques disponibles · {recent['evaluated']} evaluados · objetivo {recent['requested']} bloques.")
            if result.get("limited_history"):
                st.warning("Historia limitada: solo cuatro bloques disjuntos completos. La evaluación usa los cuatro y exige confirmación de todos para Estable (provisional); no equivale a la evidencia de la regla normal de cinco bloques.")
        if crypto:
            st.caption(f"{result['bars']} cierres comunes · {result['blocks']} bloques disponibles de {result['block_size']} velas · se requieren {result['required_blocks']}. Exchanges: " + " / ".join(s or "sin datos" for s in result["exchanges"]))
        if result.get("reason"):
            st.info(result["reason"])
        if result["state"] == "no calculable":
            return
        c1, c2, c3 = st.columns(3)
        with c1:
            explanation = f"Factor ajustado usando solo la historia en {TF_LABELS[tf]} hasta el último cierre disponible; se usa la misma beta para ambas comparaciones." if crypto and tf != "1D" else "Factor ajustado usando solo la historia diaria disponible hasta este último cierre, idéntico para las dos comparaciones."
            metric("Beta larga fija", f"{result['beta']:.3f}", explanation)
        with c2:
            metric("Últimas 250 velas", f"{result['z_short']:+.2f}", "Distancia frente a media y desvío recientes; no cambia la beta.")
        with c3:
            metric("Historia larga", f"{result['z_long']:+.2f}", "Distancia del mismo spread frente a toda la historia válida disponible.")
        required_blocks = result["evaluated_blocks"] if crypto else 5
        st.caption(f"Bloques sin solape: {result['confirmed_blocks']} de {required_blocks} confirmaron ambos órdenes. Base larga: {result['start']} → {result['end']} ({result['bars']} cierres).")
        fig = go.Figure(go.Scatter(x=result["spread"].index, y=result["spread"], name="Diferencia con beta larga fija"))
        fig.add_hline(y=result["mean_long"], line_dash="dash", annotation_text="Media larga")
        fig.add_hline(y=result["mean_short"], line_dash="dot", annotation_text="Media reciente")
        fig.update_layout(height=260, title="Mismo spread: referencia reciente y larga")
        st.plotly_chart(fig, width="stretch", key=pk("pilot_spread"))
        r = result["rolling"]
        fig = go.Figure()
        for col, label in [("p_yx", "Primero respecto del segundo"), ("p_xy", "Segundo respecto del primero")]:
            fig.add_trace(go.Scatter(x=r.date, y=r[col], name=label))
        fig.add_hline(y=.05, line_dash="dash", line_color="red", annotation_text="Umbral 0,05")
        params = cointegration_parameters(pilot, p["y"], p["x"], tf, result["bars"])
        title = f"p-valor móvil: {params['primary_window']} cierres, cada {params['rolling_step']} velas" if crypto else "p-valor móvil: 500 cierres, cada 21 ruedas"
        fig.update_layout(height=260, title=title, yaxis_range=[0, 1])
        st.plotly_chart(fig, width="stretch", key=pk("pilot_pvalue"))
        with st.expander("Pruebas y regla del estado"):
            st.json({"ventana_principal": result["primary"], "contraste": result["contrast"], "parámetros": params if crypto else pilot["cointegration"]})
            st.write("Estable (provisional) exige cuatro de cuatro bloques confirmados en ambos órdenes, contraste concordante y Johansen con una relación. La historia es limitada y el resultado no equivale a la regla normal." if result.get("limited_history") else "Estable exige confirmación en ambos órdenes, contraste concordante, Johansen con una relación y al menos cuatro de cinco bloques confirmados. Intermitente indica confirmaciones parciales o discrepancias. Sin relación significa sin confirmación en los períodos evaluados.")
            if result.get("all_block_statistics") is not None:
                st.json({"todos_los_bloques": result["all_block_statistics"], "tramo_reciente": result["recent_block_statistics"]})
            if result.get("binomial_evidence"):
                st.json({"evidencia_binomial": result["binomial_evidence"]})
                st.write("Intermitente requiere evidencia binomial significativa en todos los bloques evaluados; un p-valor aislado o una confirmación compatible con azar no basta. Estable mantiene además sus condiciones recientes, contraste y Johansen aprobados.")
        academic = "**Contexto académico — no interviene en los números:** Engle y Granger (1987) desarrollaron pruebas para estudiar un equilibrio entre series con tendencia; no estudiaron específicamente estos pares de índices. [Referencia verificada](https://doi.org/10.2307/1913236)."
        if pilot.get("regular_session"):
            academic = academic.replace("pares de índices", "pares de ETF")
        st.markdown(academic.replace("pares de índices", "pares de criptomonedas") if crypto else academic)


def render_section_pilot(db_path, legacy_render, section="indices"):
    assets, calc, pilot, ops, pairs = configs(section)
    label = pilot.get("label", "Índices")
    noun = pilot.get("noun", "índices")
    noun_singular = pilot.get("noun_singular", "Índice")
    macro_ids = pilot.get("macro_series", ["DGS10", "T10Y2Y", "VIXCLS"])
    benchmark_label = pilot.get("benchmark_label", "S&P 500")
    benchmark_hover = pilot.get("benchmark_hover", "S&P")
    def pk(name):
        return widget_key(section, name)
    signature = DatabaseManager(db_path).data_signature()
    minute = pd.Timestamp.now(tz="UTC").floor("min").isoformat()
    settings_json = json.dumps([assets, calc, pilot, ops, pairs], sort_keys=True)
    with st.spinner(f"Preparando la lectura de {label} y su calendario..."):
        model = view_model(db_path, signature, settings_json, minute, section=section)
    # Las edades corresponden a la hora de cálculo visible. La lectura se
    # renueva al cambiar precios o al vencer su caché, sin recalcular en cada clic.
    data_end = max((r["last_data"] for r in model["rows"] if r["last_data"] != "—"), default="Sin datos")
    calculated = pd.to_datetime(model["calculated_at"], utc=True).tz_convert("America/Argentina/Buenos_Aires")
    st.caption(f"Datos al: {data_end} · Calculado: {calculated.strftime('%d/%m/%Y %H:%M:%S')} Buenos Aires")
    c1, c2 = st.columns(2)
    if c1.button(f"Actualizar {label} y referencias", key=pk("pilot_update_all"), help=f"Descarga y calcula solo {label}; las referencias tienen precio y volumen propios."):
        update_section_pilot(db_path, section=section)
    if c2.button(f"Actualización rápida de {label}", key=pk("pilot_update_quick"), help="Solo una hora y diario; las escalas cortas pueden seguir atrasadas."):
        update_section_pilot(db_path, True, section=section)
    if st.session_state.get(pk("pilot_update_message")):
        st.info(st.session_state[pk("pilot_update_message")])
        for err in st.session_state.get(pk("pilot_update_errors"), []):
            st.error(err)
    rows = model["rows"]
    crypto = pilot.get("vwap_mode") == "utc"
    regular = pilot.get("regular_session", False)
    stale = sum(r["daily_stale"] for r in rows)
    if stale:
        st.warning(f"{stale} {noun} tienen cierres diarios atrasados o no comprobables. Los conteos describen sus últimos datos, no una cotización en vivo.")
    up = sum(r["direction"].startswith("alcista") for r in rows)
    down = sum(r["direction"].startswith("bajista") for r in rows)
    aligned = max(model["alignment"], key=lambda s: model["alignment"][s]["score"], default=None)
    performance = model["performance"].dropna(subset=["relative_pp"])
    leader = performance.sort_values("relative_pp", ascending=False).iloc[0] if len(performance) else None
    between = model.get("performance_between")
    if between is not None:
        ranked_between = between.dropna(subset=["return_pct"]).sort_values("return_pct", ascending=False)
        leader = ranked_between.iloc[0] if len(ranked_between) else None
    distances = [r for r in rows if r["distance_std"] is not None]
    stretched = max(distances, key=lambda r: abs(r["distance_std"])) if distances else None
    if crypto:
        render_crypto_summary(pilot, model)
        for symbol in assets[section]["activos"]:
            changed = [info for (sym, tf), info in model["exchanges"].items() if sym == symbol and info["changed"]]
            if changed:
                observed = sorted({source for info in changed for source in info["sources"]})
                st.warning("Cambio de fuente para " + asset_label(symbol) + ": " + ", ".join(observed) + "; preferida " + pilot["exchanges"][symbol] + ". Cada lectura y VWAP usa una sola exchange; revisá Fuentes y calidad.")
    elif pilot.get("summary_layout") == "smallcaps":
        render_smallcaps_summary(pilot, model)
    elif pilot.get("summary_layout") == "argentina":
        render_argentina_summary(pilot, model)
    elif regular:
        render_equity_summary(pilot, model, section)
    else:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            metric("Dirección", f"{up} suben / {down} bajan", "Dirección de los últimos cierres diarios, con las mismas reglas anteriores; las débiles cuentan y los datos atrasados se avisan. Ayuda a ver amplitud.")
        with c2:
            metric("Más alineado", asset_label(aligned) if aligned and model["alignment"][aligned]["available"] else "Sin escalas vigentes", ALIGNMENT_LEGEND,
                   model["alignment"][aligned]["label"] if aligned else None)
        with c3:
            if between is not None:
                metric("Más fuerte entre metales", asset_label(leader.symbol) if leader is not None else "Historia común insuficiente",
                       "Mayor rendimiento entre los cuatro metales sobre exactamente las mismas 20 ruedas comunes. Se compara rendimiento del precio, no distancia a la media ni al dólar.",
                       f"{leader.return_pct:+.2f}%" if leader is not None else None)
            else:
                metric("Más fuerte", asset_label(leader.symbol) if leader is not None else "Historia insuficiente",
                        f"Mayor diferencia de rendimiento frente al {benchmark_label} en las últimas 20 ruedas comunes. No es simplemente el más separado de su media.",
                        f"{leader.relative_pp:+.2f} puntos" if leader is not None else None)
        with c4:
            metric("Más alejado", asset_label(stretched["symbol"]) if stretched else "Sin media válida",
                   "Mayor separación absoluta de la media exponencial de 50 cierres, dividida por el desvío de 50 cierres. Ayuda a detectar precios estirados, no a predecir reversión.",
                   f"{stretched['distance_std']:+.2f} desvíos" if stretched else None)
    st.subheader("Contexto económico")
    with DatabaseManager(db_path)._get_connection() as conn:
        macro = pd.read_sql_query(f"SELECT * FROM calc_macro WHERE series_id IN ({','.join('?' * len(macro_ids))}) ORDER BY timestamp DESC", conn, params=list(macro_ids)).drop_duplicates("series_id")
    for col, sid in zip(st.columns(len(macro_ids)), macro_ids):
        with col:
            m = macro[macro.series_id == sid]
            if m.empty:
                metric(asset_label(sid), "Sin datos", help_text(sid))
            else:
                r = m.iloc[0]
                metric(asset_label(sid), f"{r.current_value:.2f}", help_text(sid, "cambio a un mes"), f"{r.change_1m:+.2f} en un mes")
                st.caption("Fecha del dato: " + str(r.timestamp)[:10])
    if between is not None:
        st.subheader("Rendimiento entre los cuatro metales — 20 ruedas comunes")
        if len(ranked_between):
            ranked = ranked_between.sort_values("return_pct")
            fig = go.Figure(go.Bar(x=ranked.return_pct, y=[asset_label(s) for s in ranked.symbol], orientation="h",
                                  marker_color=["seagreen" if x >= 0 else "indianred" for x in ranked.return_pct],
                                  hovertemplate="%{y}<br>Rendimiento: %{x:+.2f}%<extra></extra>"))
            fig.update_layout(height=280, xaxis_title="Rendimiento porcentual sobre el mismo período")
            st.plotly_chart(fig, width="stretch", key=pk("pilot_between_assets"))
            st.caption(f"Período común de los cuatro: {leader.start_session} → {leader.last_session}. Son 20 cambios entre 21 cierres comunes.")
        else:
            st.info("No hay 21 cierres diarios comunes válidos para comparar los cuatro metales.")
    if pilot.get("show_relative_strength", True):
        st.subheader(f"Fuerza relativa frente al {benchmark_label} — 20 ruedas")
        if pilot.get("benchmark_notice"):
            st.caption(pilot["benchmark_notice"] + " Último dato disponible: " + (model["benchmark_last_session"] or "sin datos"))
        if len(performance):
            ranked = performance.sort_values("relative_pp")
            fig = go.Figure(go.Bar(x=ranked.relative_pp, y=[asset_label(s) for s in ranked.symbol], orientation="h",
                marker_color=["seagreen" if x >= 0 else "indianred" for x in ranked.relative_pp],
                customdata=ranked[["return_pct", "benchmark_pct", "last_session"]].to_numpy(),
                hovertemplate=f"%{{y}}<br>Diferencia: %{{x:+.2f}} puntos porcentuales<br>{noun_singular}: %{{customdata[0]:+.2f}}% · {benchmark_hover}: %{{customdata[1]:+.2f}}%<br>Hasta %{{customdata[2]}}<extra></extra>"))
            fig.update_layout(height=280, margin={"l": 0, "r": 15, "t": 10, "b": 35}, xaxis_title=f"Puntos porcentuales frente al {benchmark_label}")
            st.plotly_chart(fig, width="stretch", key=pk("pilot_relative_strength"))
    summary = pd.DataFrame([{"Activo": asset_label(r["symbol"]), "Dirección": r["direction"], "Alineación": model["alignment"][r["symbol"]]["label"],
        "Distancia": f"{r['distance_pct']:+.2f}% · {r['distance_std']:+.2f} desvíos" if r["distance_pct"] is not None and r["distance_std"] is not None else "No disponible", "Dato": r["age"]} for r in rows])
    if crypto:
        for index, row in enumerate(rows):
            summary.loc[index, "Activo"] = pilot_asset_label(pilot, row["symbol"], exchange=row.get("exchange"))
            vwap = model["session_vwaps"].get(row["symbol"], {})
            if vwap.get("usable"):
                text = f"{vwap['distance_pct']:+.2f}%"
                if vwap.get("distance_bands") is not None:
                    text += f" · {vwap['distance_bands']:+.2f} bandas"
                text += " · " + vwap["exchange"].title()
                summary.loc[index, "Distancia"] = text
            else:
                summary.loc[index, "Distancia"] = "VWAP parcial o no disponible"
    st.dataframe(summary, hide_index=True, width="stretch", column_config={
        "Activo": st.column_config.Column(help=help_text("activo")), "Dirección": st.column_config.Column(help=help_text("régimen")),
        "Alineación": st.column_config.Column(help=ALIGNMENT_LEGEND), "Distancia": st.column_config.Column(help="VWAP de la sesión UTC y corte común de cierres: porcentaje y desvíos ponderados (bandas), con exchange explícita." if crypto else "Lectura diaria: media de 50 cierres y desvío de 50 cierres. El VWAP de sesión se muestra abajo, en su propio instrumento."),
        "Dato": st.column_config.Column(help="Antigüedad diaria en mercado 24/7; no se descuentan noches, feriados ni fines de semana." if crypto else "Antigüedad calculada según ruedas, cierres y feriados reales del mercado."),
        "_index": st.column_config.Column(help=help_text("fila"))})
    with st.expander("Alineación por grupo de escalas"):
        st.write(ALIGNMENT_LEGEND)
        for symbol, a in model["alignment"].items():
            st.write("**" + pilot_asset_label(pilot, symbol) + "** — " + a["label"])
            st.caption("Componente 4h: " + pilot_asset_label(pilot, symbol, "4h"))
            for group, v in a["groups"].items():
                st.caption(f"{group}: {v['available']} de {v['total']} disponibles; {v['up']} hacia arriba, {v['down']} hacia abajo, {v['weak']} débiles.")
    for notice in pilot.get("notices", [FUTURES_NOTICE]):
        st.info(notice)
    render_ratios(pilot, model["daily"], section)
    render_detail(db_path, signature, pilot, ops, model["frames"], section)
    if pilot.get("cointegration"):
        render_cointegration(db_path, signature, settings_json, minute, pilot, pairs[section], section, model)
    else:
        with st.expander(f"Relaciones entre {pilot.get('noun', 'índices')}"):
            st.write("No se usa cointegración entre la acción local y su ADR: el CCL implícito depende del dólar entre dos mercados que no comparten sesión, por lo que no es una relación estable. Se muestra el CCL implícito, su mediana y la dispersión entre empresas.")
            st.write("Brecha contra el CCL oficial del BCRA: propuesta documentada, no implementada. Ver docs/paso6_argentina.md.")
    with st.expander("Fuentes, fechas, parámetros y calidad de los datos"):
        st.dataframe(model["quality"], hide_index=True, width="stretch", column_config={**{c: st.column_config.Column(help="Trazabilidad de la lectura del piloto: calendario, fuente y fecha usada.") for c in model["quality"].columns}, "_index": st.column_config.Column(help="Número de fila.")})
        diagnostic = {key: pilot[key] for key in pilot.get("diagnostic_fields", pilot) if key in pilot}
        if pilot.get("sessions"):
            hours = {spec["label"]: {"timezone": spec["timezone"], "starts": [part.split("-")[0] for part in spec["four_hour"]],
                                     "label": spec["four_hour_label"]} for spec in pilot["sessions"].values()}
            session = {spec["label"]: {"mode": "regular", "opening": spec["open"], "close": spec["close"],
                                       "calendar": spec["calendar"], "include_premarket": False}
                       for spec in pilot["sessions"].values()}
        else:
            hours = {"timezone": "America/New_York", "starts": ["09:30", "13:30"], "label": "4h de sesión"} if regular else ops["platform_4h"]
            session = {"mode": "regular", "opening": "09:30", "close": "16:00", "calendar": "NYSE"} if regular else ops["cme_vwap_session"]
        st.json({"parámetros diarios": calc["regime"], "lectura piloto": diagnostic, "horario 4h": hours, "sesión": session})
        ref_rows = []
        for reference in (assets[section]["activos"] if regular else pilot["names"]):
            for tf in TFS:
                df = raw_data(db_path, reference, tf, signature)
                source = model["exchanges"].get((reference, tf), {}).get("exchange") if crypto else None
                ref_rows.append({"Instrumento": pilot_asset_label(pilot, reference, exchange=source), "Escala": TF_LABELS[tf], "Fuente": source.title() if crypto and source else "Sin exchange registrada" if crypto else "Yahoo",
                    "Última marca UTC": str(df.timestamp.max()) if len(df) else "Sin datos", "Velas": len(df)})
        st.dataframe(pd.DataFrame(ref_rows), hide_index=True, width="stretch", column_config={
            **{c: st.column_config.Column(help="Cobertura del instrumento de referencia; precio y volumen no se mezclan con el índice.") for c in ["Instrumento", "Escala", "Fuente", "Última marca UTC", "Velas"]},
            "_index": st.column_config.Column(help="Número de fila.")})
        st.write("Las recepciones antiguas, anteriores al formato UTC verificado de C0, no permiten comprobar retrospectivamente si la última vela se recibió terminada. Las nuevas recepciones sí distinguen valores provisionales.")
        st.write("La hora de cálculo corresponde a esta lectura en caché; las fotos se generan únicamente al actualizar.")
        notices = DatabaseManager(db_path).get_data_notices()
        wanted = set(assets[section]["activos"]) | set(pilot["names"])
        for n in notices:
            if n["asset"] in wanted:
                st.write(f"{asset_label(n['asset'])}: {n['message']}")
    with st.expander("Cómo leer esto"):
        notes = pilot.get("reading_notes", "Primero mirá si varios índices y escalas coinciden. La fuerza relativa compara rendimientos; estar lejos de una media no equivale a ser más fuerte. Las bandas de sesión describen distancia, no aseguran reversión. Revisá fechas, fuente y velas abiertas antes de comparar con tu plataforma.")
        if pilot.get("cointegration", {}).get("primary_window"):
            notes = notes + " " + MULTIPLE_PAIRS_NOTE
        st.write(explain_symbols(notes) if pilot.get("summary_layout") in ("smallcaps", "argentina") else notes)
    with st.expander("Glosario"):
        for term in section_terms(section, macro_ids):
            try:
                label = pilot_asset_label(pilot, term) if term in pilot.get("exchanges", {}) else asset_label(term)
            except KeyError:
                label = term
            text = ("Promedio de sesión UTC ponderado por el volumen del mismo instrumento y exchange; reinicia a las 00:00 UTC." if crypto else "Promedio de sesión ponderado por el volumen del mismo instrumento; reinicio según la sesión elegida.") if term == "VWAP" else definition(term)
            st.markdown("**" + rich_text(label) + "** — " + rich_text(text), unsafe_allow_html=True)
    with st.expander("Vista anterior (para comparar)"):
        legacy_render(section)
