"""Indicadores nuevos de sección: misma fórmula que la pantalla, sin Streamlit."""
import pandas as pd

from src.indices_math import prepare_bars, daily_means, relative_performance, freshness, alignment, pair_analysis
from src.calc.regime import get_latest_market_regime
from src.data.four_hour import prepare_stored, market_results
from src.pilot_math import common_performance, ratio_reading, select_exchange, crypto_vwap_readings, crypto_kpis, pair_coverage, cointegration_parameters
from src.equity_math import regular_stock_bars, equity_indicators


def pair_indicators(conn, pilot, pairs, now, frames=None):
    frames = {} if frames is None else frames
    readings = []
    crypto = pilot.get("vwap_mode") == "utc"
    for pair in pairs:
        for tf in (pilot["cointegration_scales"] if crypto else ["1D"]):
            values = []
            for symbol in (pair["y"], pair["x"]):
                if (symbol, tf) not in frames:
                    raw = pd.read_sql_query("SELECT * FROM candles WHERE symbol=? AND timeframe=? ORDER BY timestamp", conn, params=(symbol, tf))
                    if crypto:
                        raw, _ = select_exchange(raw, pilot["exchanges"][symbol])
                    frames[(symbol, tf)] = prepare_stored(raw, symbol, now, pilot["calendars"][symbol]) if tf == "4h" else prepare_bars(raw, symbol, tf, pilot["calendars"][symbol], now)
                bars = frames[(symbol, tf)]
                closed = bars[bars.closed]
                if tf == "1D" and pilot.get("deduplicate_daily_sessions"):
                    closed = closed.drop_duplicates("session", keep="last")
                values.append(closed.set_index("session" if tf == "1D" else "timestamp").close)
            common = pd.concat([v.rename(str(i)) for i, v in enumerate(values)], axis=1, join="inner").dropna()
            common = common[(common > 0).all(axis=1)]
            params = {**cointegration_parameters(pilot, pair["y"], pair["x"], tf, len(common)), "include_rolling": False}
            result = pair_analysis(*values, params)
            readings.append({"y": pair["y"], "x": pair["x"], "tf": tf,
                             **{key: value for key, value in result.items() if key not in ("spread", "rolling")}})
    return readings


def section_indicators(conn, section, assets, pilot, now, calc_config=None, pairs=None):
    daily, frames, exchange_sources = {}, {}, {}
    crypto = pilot.get("vwap_mode") == "utc"
    regular = pilot.get("regular_session", False)
    for symbol in assets:
        for tf in (["1m", "5m", "15m", "1h", "4h", "1D"] if crypto or regular else ["1D"]):
            raw = pd.read_sql_query("SELECT * FROM candles WHERE symbol=? AND timeframe=? ORDER BY timestamp",
                                    conn, params=(symbol, "5m" if regular and tf == "1h" else tf))
            if crypto:
                raw, info = select_exchange(raw, pilot["exchanges"][symbol])
                exchange_sources.setdefault(symbol, {})[tf] = info
            bars = regular_stock_bars(raw, symbol, tf, now) if regular else prepare_stored(raw, symbol, now, pilot["calendars"][symbol]) if tf == "4h" else prepare_bars(raw, symbol, tf, pilot["calendars"][symbol], now)
            frames[(symbol, tf)] = bars
        bars = frames[(symbol, "1D")]
        if pilot.get("deduplicate_daily_sessions"):
            bars = bars.drop_duplicates("session", keep="last")
        daily[symbol] = daily_means(bars)
    series = {symbol: frame.set_index("session").close for symbol, frame in daily.items()}
    ratios = [ratio_reading(daily, spec)[0] for spec in pilot.get("ratios", [])]
    relative = {}
    kpis = {}
    if pilot.get("compare_all_assets"):
        ranking = common_performance(series, pilot["relative_strength_sessions"])
        relative["between_assets"] = ranking.to_dict("records")
        valid = ranking.dropna(subset=["return_pct"]).sort_values("return_pct", ascending=False)
        if len(valid):
            kpis["strongest_20_sessions"] = {"symbol": valid.iloc[0].symbol, "return_pct": float(valid.iloc[0].return_pct),
                                             "start_session": valid.iloc[0].start_session, "last_session": valid.iloc[0].last_session}
    benchmark_id = pilot.get("benchmark") if pilot.get("show_relative_strength", True) else None
    if benchmark_id:
        fred = pd.read_sql_query("SELECT timestamp,value FROM fred_series WHERE series_id=? ORDER BY timestamp",
                                 conn, params=(benchmark_id,))
        if len(fred):
            fred = fred[pd.to_datetime(fred.timestamp, utc=True) <= now]
            dates = pd.to_datetime(fred.timestamp, utc=True).dt.strftime("%Y-%m-%d")
            benchmark = pd.Series(fred.value.to_numpy(dtype=float), index=dates.to_numpy()).groupby(level=0).last()
        else:
            benchmark = series.get(benchmark_id, pd.Series(dtype=float))
        performance = relative_performance(series, benchmark, pilot["relative_strength_sessions"])
        relative["benchmark"] = benchmark_id
        relative["benchmark_last_session"] = str(benchmark.index.max()) if len(benchmark) else None
        relative["against_benchmark"] = performance.astype(object).where(pd.notna(performance), None).to_dict("records")
    result = {"ratios": ratios, "relative_strength": relative, "kpis": kpis,
              "pilot_indicators_calculated_at": now.isoformat()}
    if crypto:
        directions, rows = {}, []
        for symbol in assets:
            states = {}
            for tf in ["1m", "5m", "15m", "1h", "4h", "1D"]:
                bars = frames[(symbol, tf)]
                closed = bars[bars.closed]
                reading = market_results(closed, calc_config)[0] if tf == "4h" else get_latest_market_regime(closed, calc_config["regime"])
                age = freshness(bars, tf, "24/7", now)
                states[tf] = reading["direction"] if not age["stale"] else "sin datos"
                if tf == "1D":
                    rows.append({"symbol": symbol, "direction": reading["direction"]})
            directions[symbol] = alignment(states)
        vwaps = crypto_vwap_readings(frames, assets, pilot["vwap"]["minimum_volume_coverage"])
        result.update({"kpis": crypto_kpis(rows, directions, {r["label"]: r for r in ratios}, vwaps),
                       "session_vwaps": vwaps, "exchange_sources": exchange_sources,
                       "pair_coverage": pair_coverage(frames, pairs, pilot)})
    if regular:
        raw = pd.read_sql_query("SELECT * FROM candles WHERE symbol=? AND timeframe='1D' ORDER BY timestamp", conn, params=(pilot["benchmark"],))
        bars = prepare_bars(raw, pilot["benchmark"], "1D", "NYSE", now)
        benchmark = daily_means(bars).set_index("session").close
        rows = []
        for symbol, data in daily.items():
            reading = get_latest_market_regime(data, calc_config["regime"])
            last = data.iloc[-1] if len(data) else None
            rows.append({"symbol": symbol, "direction": reading["direction"],
                         "distance_pct": float(last.distance_pct) if last is not None and pd.notna(last.distance_pct) else None,
                         "distance_std": float(last.distance_std) if last is not None and pd.notna(last.distance_std) else None})
        equity = equity_indicators(rows, daily, frames, benchmark, pilot)
        result.update({"kpis": equity["kpis"], "sector_performance": equity["sector_performance"].astype(object).where(pd.notna(equity["sector_performance"]), None).to_dict("records"),
                       "sector_heatmap": equity["heatmap"].astype(object).where(pd.notna(equity["heatmap"]), None).to_dict("records"),
                       "regular_session": {"timezone": "America/New_York", "opening": "09:30", "close": "16:00", "include_premarket": False}})
    if pilot["cointegration"].get("binomial_gate"):
        result["pilot_cointegration"] = pair_indicators(conn, pilot, pairs, now, frames)
    return result
