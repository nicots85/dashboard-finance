"""C2: ejemplos conocidos de VWAP, bandas, calendario, alineación y rangos."""
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import yaml
from src.presentation import ROOT
from src.indices_math import (session_vwap, alignment, prepare_bars, freshness, select_range,
    aggregate_4h, aggregate_regular_hours, daily_means, relative_performance, unexpected_gaps, pair_analysis)


def prices(values, timestamps, volume=None, sessions=None):
    values = np.array(values, dtype=float)
    return pd.DataFrame({"timestamp": pd.to_datetime(timestamps, utc=True), "open": values,
        "high": values, "low": values, "close": values, "volume": volume if volume is not None else 1.,
        **({"session": sessions} if sessions else {})})


class IndicesPilotTests(unittest.TestCase):
    def test_weighted_vwap_and_population_bands(self):
        df = prices([10, 20], ["2026-10-05 22:00Z", "2026-10-05 22:01Z"], [1, 3], ["a", "a"])
        r = session_vwap(df)
        self.assertAlmostEqual(r.vwap.iloc[-1], 17.5)
        self.assertAlmostEqual(r.sigma.iloc[-1], np.sqrt(18.75))
        self.assertAlmostEqual(r.upper2.iloc[-1], 17.5 + 2*np.sqrt(18.75))

    def test_reset_does_not_carry_previous_session(self):
        r = session_vwap(prices([10, 20, 100], pd.date_range("2026-10-05 22:00", periods=3, freq="min", tz="UTC"), [1, 3, 1], ["a", "a", "b"]))
        self.assertEqual(r.vwap.iloc[-1], 100)
        self.assertEqual(r.sigma.iloc[-1], 0)

    def test_zero_volume_is_not_a_fabricated_vwap(self):
        r = session_vwap(prices([10, 20], pd.date_range("2026-10-05", periods=2, freq="min", tz="UTC"), [0, 0], ["a", "a"]))
        self.assertTrue(r.vwap.isna().all())

    def test_large_constant_price_has_zero_variance(self):
        r = session_vwap(prices([30000.123456]*20, pd.date_range("2026-10-05", periods=20, freq="min", tz="UTC"), list(range(1,21)), ["a"]*20))
        self.assertTrue((r.sigma==0).all())

    def test_mixed_instruments_rejected(self):
        df = prices([10, 20], pd.date_range("2026-10-05", periods=2, freq="min", tz="UTC"), [1, 3], ["a", "a"])
        df["symbol"] = ["NQ=F", "QQQ"]
        with self.assertRaises(ValueError):
            session_vwap(df)

    def test_full_session_reset_uses_new_york_dst(self):
        for opening, expected in [("2026-10-25 22:00Z", "2026-10-26"), ("2026-11-01 23:00Z", "2026-11-02")]:
            df = prepare_bars(prices([10], [opening]), "NQ=F", "1m", "CME_Equity", "2026-11-03")
            self.assertEqual(df.session.iloc[0], expected)

    def test_regular_session_filters_overnight_and_moves_in_utc(self):
        raw = prices([1,2,3,4], ["2026-10-26 01:00Z", "2026-10-26 13:30Z", "2026-11-02 01:00Z", "2026-11-02 14:30Z"])
        df = prepare_bars(raw, "NQ=F", "1m", "CME_Equity", "2026-11-03", regular=True)
        self.assertEqual(df.close.tolist(), [2,4])

    def test_weekend_holiday_and_half_day_age(self):
        raw = prices([10], ["2026-11-27 05:00Z"])
        df = prepare_bars(raw, "^NDX", "1D", "NASDAQ", "2026-11-29 18:00Z")
        self.assertEqual(df.bar_end.iloc[0].hour, 18)  # Black Friday cierra a las 13 NY.
        self.assertFalse(freshness(df,"1D","NASDAQ","2026-11-29 18:00Z")["stale"])
        self.assertTrue(freshness(df,"1D","NASDAQ","2026-11-30 22:00Z")["stale"])

    def test_receipt_during_open_candle_is_marked_provisional(self):
        raw = prices([10], ["2026-10-05 13:30Z"])
        raw["updated_at"] = "2026-10-05T13:30:30+00:00"
        df = prepare_bars(raw,"^NDX","1m","NASDAQ","2026-10-05 14:00Z")
        self.assertFalse(df.closed.iloc[0])

    def test_alignment_counts_weak_and_omits_absent(self):
        a = alignment({"1m":"alcista","5m":"alcista (débil)","15m":"sin datos","1h":"bajista","4h":"sin datos","1D":"lateral"})
        self.assertEqual((a["up"],a["down"],a["weak"],a["available"],a["missing"]),(2,1,1,4,2))
        self.assertEqual(a["groups"]["Corto plazo"]["available"],2)

    def test_default_range_is_sessions_not_500_bars(self):
        df = prices(list(range(12)), pd.date_range("2026-10-01", periods=12, freq="h", tz="UTC"), sessions=["a"]*4+["b"]*4+["c"]*4)
        df["bar_end"]=df.timestamp+pd.Timedelta(hours=1)
        df["closed"]=True
        r,info=select_range(df,"1m",{"1m":{"sessions":2}},"2026-11-01")
        self.assertEqual(len(r),8)
        self.assertEqual(r.session.unique().tolist(),["b","c"])
        self.assertFalse(info["short_history"])

    def test_short_history_is_reported(self):
        df=prices([1,2],pd.date_range("2026-10-01",periods=2,freq="h",tz="UTC"),sessions=["a","a"])
        df["bar_end"]=df.timestamp+pd.Timedelta(hours=1)
        _,info=select_range(df,"1m",{"1m":{"sessions":2}},"2026-11-01")
        self.assertTrue(info["short_history"])

    def test_warmup_calculates_before_crop(self):
        df=prices(list(range(1,301)),pd.date_range("2025-01-01",periods=300,freq="D",tz="UTC"),sessions=[str(i) for i in range(300)])
        df["closed"]=True
        self.assertTrue(daily_means(df).tail(10).ema200.notna().all())
        self.assertTrue(daily_means(df.tail(10)).ema200.isna().all())

    def test_utc_4h_candle_is_not_closed_before_its_end(self):
        df=prepare_bars(prices([1,2], ["2026-10-05 22:00Z","2026-10-05 23:00Z"]),"NQ=F","1h","CME_Equity","2026-10-05 23:30Z")
        r=aggregate_4h(df,calendar_name="CME_Equity",now="2026-10-05 23:30Z")
        self.assertFalse(r.closed.iloc[-1])
        self.assertEqual(r.bar_end.iloc[-1],pd.Timestamp("2026-10-06 00:00Z"))

    def test_4h_platform_apertures_are_validated(self):
        df=prices([1], ["2026-10-05 22:00Z"])
        with self.assertRaises(ValueError):
            aggregate_4h(df,open_times=["00:00","03:00"])

    def test_regular_hourly_candles_start_at_0930(self):
        df=prepare_bars(prices(range(12),pd.date_range("2026-11-02 14:30",periods=12,freq="5min",tz="UTC")),"NQ=F","5m","CME_Equity","2026-11-02 16:00Z",regular=True)
        r=aggregate_regular_hours(df,"2026-11-02 16:00Z")
        self.assertEqual(r.timestamp.iloc[0],pd.Timestamp("2026-11-02 14:30Z"))
        self.assertEqual(len(r),1)
        self.assertEqual(r.volume.iloc[0],12)

    def test_relative_strength_uses_same_20_common_sessions(self):
        dates=pd.date_range("2026-01-01",periods=21).strftime("%Y-%m-%d")
        y=pd.Series(np.linspace(100,120,21),index=dates)
        x=pd.Series(np.linspace(100,110,21),index=dates)
        r=relative_performance({"asset":y},x).iloc[0]
        self.assertAlmostEqual(r.relative_pp,10)

    def test_open_market_gap_is_not_hidden_as_a_weekend(self):
        raw=prices([1,2,3],["2026-10-02 19:58Z","2026-10-02 19:59Z","2026-10-05 13:32Z"])
        df=prepare_bars(raw,"^NDX","1m","NASDAQ","2026-10-06")
        self.assertTrue(unexpected_gaps(df,"1m","NASDAQ"))  # faltan los minutos 09:30/09:31 del lunes

    def test_pair_short_and_long_share_exact_beta(self):
        cfg=yaml.safe_load((ROOT/"config/sections.yaml").read_text())["indices"]["cointegration"]
        cfg={**cfg,"primary_window":50,"contrast_window":100,"short_spread_window":25,"rolling_step":50}
        rng=np.random.default_rng(10)
        x=np.cumsum(rng.normal(0,.01,300))+5
        y=1.5*x+rng.normal(0,.01,300)
        a,b=pd.Series(np.exp(y)),pd.Series(np.exp(x))
        with patch("src.indices_math._pair_test",return_value={"p_yx":.01,"p_xy":.01,"johansen_rank":1}):
            result=pair_analysis(a,b,cfg)
        self.assertEqual(result["state"],"estable")
        expected=y-result["beta"]*x
        np.testing.assert_allclose(result["spread"],expected)
        self.assertAlmostEqual(result["z_short"],(expected[-1]-expected[-25:].mean())/expected[-25:].std(ddof=1))
        self.assertAlmostEqual(result["z_long"],(expected[-1]-expected.mean())/expected.std(ddof=1))
        self.assertEqual(result["evaluated_blocks"],5)

    def test_insufficient_history_and_errors_are_no_calculable(self):
        cfg=yaml.safe_load((ROOT/"config/sections.yaml").read_text())["indices"]["cointegration"]
        short=pd.Series(np.linspace(1,2,100))
        self.assertEqual(pair_analysis(short,short,cfg)["state"],"no calculable")
        long=pd.Series(np.linspace(1,2,2500))
        with patch("src.indices_math._pair_test",side_effect=RuntimeError("fallo simulado")):
            r=pair_analysis(long,long,cfg)
        self.assertEqual(r["state"],"no calculable")
        self.assertIn("fallo simulado",r["reason"])


if __name__=="__main__":
    unittest.main(verbosity=2)
