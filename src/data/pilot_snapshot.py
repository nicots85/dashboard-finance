"""Indicadores nuevos de sección: misma fórmula que la pantalla, sin Streamlit."""
import pandas as pd

from src.indices_math import prepare_bars, daily_means, relative_performance
from src.pilot_math import common_performance, ratio_reading


def section_indicators(conn, section, assets, pilot, now):
    daily = {}
    for symbol in assets:
        raw = pd.read_sql_query("SELECT * FROM candles WHERE symbol=? AND timeframe='1D' ORDER BY timestamp",
                                conn, params=(symbol,))
        bars = prepare_bars(raw, symbol, "1D", pilot["calendars"][symbol], now)
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
    benchmark_id = pilot.get("benchmark")
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
    return {"ratios": ratios, "relative_strength": relative, "kpis": kpis,
            "pilot_indicators_calculated_at": now.isoformat()}
