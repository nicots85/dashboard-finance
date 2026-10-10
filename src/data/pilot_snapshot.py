"""Indicadores nuevos de sección: misma fórmula que la pantalla, sin Streamlit."""
import pandas as pd

from src.indices_math import prepare_bars, daily_means, relative_performance, freshness, alignment
from src.calc.regime import get_latest_market_regime
from src.data.four_hour import prepare_stored, market_results
from src.pilot_math import common_performance, ratio_reading, select_exchange, crypto_vwap_readings, crypto_kpis, pair_coverage


def section_indicators(conn, section, assets, pilot, now, calc_config=None, pairs=None):
    daily, frames, exchange_sources = {}, {}, {}
    crypto = pilot.get("vwap_mode") == "utc"
    for symbol in assets:
        for tf in (["1m", "5m", "15m", "1h", "4h", "1D"] if crypto else ["1D"]):
            raw = pd.read_sql_query("SELECT * FROM candles WHERE symbol=? AND timeframe=? ORDER BY timestamp",
                                    conn, params=(symbol, tf))
            if crypto:
                raw, info = select_exchange(raw, pilot["exchanges"][symbol])
                exchange_sources.setdefault(symbol, {})[tf] = info
            bars = prepare_stored(raw, symbol, now, pilot["calendars"][symbol]) if tf == "4h" else prepare_bars(raw, symbol, tf, pilot["calendars"][symbol], now)
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
    return result
