"""Pruebas de protección y trazabilidad usando únicamente bases temporales."""
import json
import sqlite3
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from src.data.db_manager import DatabaseManager
from src.data.backup import create_backup, restore_backup, database_summary, prune_backups, ensure_daily_backup
from src.data.audit import candle_end, recent_gaps
from src.calc.regime import compute_market_regime_history, get_latest_market_regime
from src.calc.zscore import compute_zscore_history, get_latest_zscore
from src.calc.cointegration import evaluate_pair_cointegration
from install_daily_backup import mac_definition, windows_definition
from src.data.crypto_adapter import CryptoAdapter
from src.data.yahoo_adapter import YahooAdapter


def fixture(n=80, start="2025-01-01", freq="D"):
    rng = np.random.default_rng(41)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame({"timestamp": pd.date_range(start, periods=n, freq=freq, tz="UTC"),
                        "open": close - .2, "high": close + 1, "low": close - 1, "close": close, "volume": 1000.0})


class ProtectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = DatabaseManager(self.root / "source.db")
        self.df = fixture()
        self.db.save_candles(self.df, "BTC/USDT", "1D", "binance")

    def tearDown(self):
        self.tmp.cleanup()

    def test_backup_restores_every_table_and_last_data_without_changing_source(self):
        before = database_summary(self.db.db_path)
        backup = create_backup(self.db.db_path, self.root / "backups")
        restored = restore_backup(backup["archive"], self.root / "trial.db")
        self.assertEqual(restored["counts"], before["counts"])
        self.assertEqual(restored["last_candle"], before["last_candle"])
        self.assertEqual(database_summary(self.db.db_path), before)
        self.assertLess(backup["compressed_bytes"], backup["raw_bytes"])

    def test_backup_reads_committed_wal_data_not_pending_write(self):
        writer = sqlite3.connect(self.db.db_path)
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("INSERT INTO candles(symbol,timeframe,timestamp,close) VALUES ('X','1D','2090-01-01',1)")
        try:
            backup = create_backup(self.db.db_path, self.root / "backups")
            self.assertEqual(backup["candles"], len(self.df))
        finally:
            writer.rollback()
            writer.close()

    def test_damaged_backup_never_replaces_destination(self):
        backup = create_backup(self.db.db_path, self.root / "backups")
        bad = self.root / "bad.zip"
        with zipfile.ZipFile(backup["archive"]) as original, zipfile.ZipFile(bad, "w") as corrupted:
            corrupted.writestr("finance.db", original.read("finance.db"))
            manifest = json.loads(original.read("manifest.json"))
            manifest["sha256"] = "not-the-hash"
            corrupted.writestr("manifest.json", json.dumps(manifest))
        target = self.root / "target.db"
        restore_backup(backup["archive"], target)
        before = target.read_bytes()
        with self.assertRaises(ValueError):
            restore_backup(bad, target, replace=True)
        self.assertEqual(target.read_bytes(), before)

    def test_replace_creates_safety_backup(self):
        backup = create_backup(self.db.db_path, self.root / "backups")
        target = self.root / "target.db"
        restore_backup(backup["archive"], target)
        result = restore_backup(backup["archive"], target, replace=True, safety_dir=self.root / "safety")
        self.assertTrue(Path(result["safety_backup"]).exists())

    def test_restore_refuses_destination_with_pending_writer(self):
        backup = create_backup(self.db.db_path, self.root / "backups")
        writer = sqlite3.connect(self.db.db_path)
        writer.execute("INSERT INTO candles(symbol,timeframe,timestamp,close) VALUES ('PENDING','1D','2090-01-01',1)")
        try:
            with self.assertRaises(RuntimeError):
                restore_backup(backup["archive"], self.db.db_path, replace=True, safety_dir=self.root / "safety")
        finally:
            writer.rollback()
            writer.close()
        self.assertEqual(database_summary(self.db.db_path)["candles"], len(self.df))

    def test_retention_keeps_periods_not_seven_runs_and_preserves_other_files(self):
        for period, keep in [("daily", 7), ("weekly", 4), ("monthly", 3)]:
            folder = self.root / period
            folder.mkdir()
            for day in range(180):
                for hour in [8, 20]:
                    when = datetime(2026, 1, 1, hour, tzinfo=timezone.utc) + timedelta(days=day)
                    (folder / ("finance_" + when.strftime("%Y%m%dT%H%M%S.%fZ") + ".zip")).touch()
            unrelated = folder / "otra_copia.zip"
            unrelated.touch()
            prune_backups(folder, keep, period)
            self.assertEqual(len(list(folder.glob("finance_*.zip"))), keep)
            self.assertTrue(unrelated.exists())

    def test_daily_backup_is_not_duplicated_on_each_update(self):
        a = ensure_daily_backup(self.db.db_path, self.root / "backups")
        self.assertIsNotNone(a)
        self.assertIsNone(ensure_daily_backup(self.db.db_path, self.root / "backups"))

    def test_correction_is_logged_once_and_changes_input_revision(self):
        source = self.db.load_candles("BTC/USDT", "1D")
        version = source.attrs["data_version"]
        result = get_latest_zscore(source)
        config = {"zscore": {"period": 50}}
        self.db.save_zscore_result("BTC/USDT", "1D", result, [version], config["zscore"])
        self.assertEqual(self.db.get_calculation_health(config)[0]["status"], "ok")
        corrected = self.df.copy()
        corrected.loc[5, "close"] += 1  # No cambia la fecha más reciente.
        self.db.save_candles(corrected, "BTC/USDT", "1D", "binance")
        self.assertEqual(self.db.get_calculation_health(config)[0]["status"], "stale")
        self.db.save_candles(corrected, "BTC/USDT", "1D", "binance")
        with self.db._get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM candle_corrections").fetchone()[0], 1)
            before, after = conn.execute("SELECT old_values,new_values FROM candle_corrections").fetchone()
            self.assertEqual(json.loads(after)["close"] - json.loads(before)["close"], 1)

    def test_identical_download_and_parameter_change_are_distinguished(self):
        source = self.db.load_candles("BTC/USDT", "1D")
        self.db.save_zscore_result("BTC/USDT", "1D", get_latest_zscore(source), [source.attrs["data_version"]], {})
        self.db.save_candles(self.df, "BTC/USDT", "1D", "binance")
        self.assertEqual(self.db.get_calculation_health({"zscore": {}})[0]["status"], "ok")
        self.assertEqual(self.db.get_calculation_health({"zscore": {"period": 100}})[0]["status"], "stale")

    def test_open_candle_finalization_is_not_logged_as_historical_correction(self):
        row = fixture(1, "2026-10-05 12:00", "min")
        self.db.save_candles(row, "NEW/USDT", "1m", "binance", datetime(2026, 10, 5, 12, 0, 30, tzinfo=timezone.utc))
        row.loc[0, "close"] += 1
        self.db.save_candles(row, "NEW/USDT", "1m", "binance", datetime(2026, 10, 5, 12, 2, tzinfo=timezone.utc))
        with self.db._get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM candle_corrections WHERE symbol='NEW/USDT'").fetchone()[0], 0)

    def test_failed_cointegration_is_not_a_negative_test(self):
        with patch("src.calc.cointegration.coint", side_effect=RuntimeError("fallo simulado")):
            res = evaluate_pair_cointegration(self.df, self.df.assign(close=self.df.close * 2))
        self.assertIsNone(res["p_value"])
        self.assertEqual(res["calc_status"], "no_calculable")
        self.assertIn("fallo simulado", res["error_message"])

    def test_undefined_pvalue_is_no_calculable(self):
        with patch("src.calc.cointegration.coint", return_value=(-2.0, np.nan, None)):
            result = evaluate_pair_cointegration(self.df, self.df.assign(close=self.df.close * 2))
        self.assertEqual(result["calc_status"], "no_calculable")
        self.assertIsNone(result["p_value"])

    def test_no_aligned_data_does_not_invent_a_last_used_date(self):
        source = self.db.load_candles("BTC/USDT", "1D")
        other = source.copy()
        other["timestamp"] += pd.Timedelta(days=1000)
        res = evaluate_pair_cointegration(source, other)
        self.db.save_cointegration_result("NO_MATCH", "1D", source.timestamp.iloc[-1], res,
            [source.attrs["data_version"]], {})
        health = self.db.get_calculation_health({"cointegration": {}})[0]
        self.assertEqual(health["status"], "no_calculable")
        self.assertIsNone(health["last_data_timestamp"])

    def test_macro_revision_detects_a_corrected_observation(self):
        df = pd.DataFrame({"timestamp": self.df.timestamp, "value": self.df.close})
        self.db.save_fred_series(df, "DGS10")
        source = self.db.load_fred_series("DGS10")
        res = {"timestamp": source.timestamp.iloc[-1], "current_value": float(source.value.iloc[-1])}
        self.db.save_macro_result("DGS10", res, [source.attrs["data_version"]], {})
        df.loc[2, "value"] += .1
        self.db.save_fred_series(df, "DGS10")
        self.assertEqual(self.db.get_calculation_health({"macro": {}})[0]["status"], "stale")

    def test_calculation_clock_is_utc_without_second_timezone_conversion(self):
        source = self.db.load_candles("BTC/USDT", "1D")
        self.db.save_zscore_result("BTC/USDT", "1D", get_latest_zscore(source), [source.attrs["data_version"]], {})
        with self.db._get_connection() as conn:
            updated, calculated = conn.execute("SELECT updated_at,calculated_at FROM calc_zscores").fetchone()
        delta = abs((pd.to_datetime(updated, utc=True) - pd.to_datetime(calculated, utc=True)).total_seconds())
        self.assertLess(delta, 2)

    def test_crypto_page_limit_reports_partial_history(self):
        class Exchange:
            markets = {"BTC/USDT": {}}
            def parse_timeframe(self, tf):
                return 60
            def fetch_ohlcv(self, symbol, timeframe, since, limit):
                return [[since + i * 60000, 100, 101, 99, 100, 1] for i in range(limit)]
        adapter = CryptoAdapter()
        old = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=190)
        with patch.object(adapter, "_get_exchange", return_value=Exchange()):
            df = adapter._fetch_ccxt_paginated("binance", "BTC/USDT", "1m", since=old)
        self.assertEqual(len(df), 200000)
        self.assertTrue(any(n["kind"] == "download_limit" for n in adapter.fetch_notices[("BTC/USDT", "1m")]))

    def test_yahoo_source_limit_is_visible_and_preserves_existing_rows(self):
        raw = fixture(3, "2026-10-01", "min").set_index("timestamp")
        raw.index.name = "Datetime"
        raw.columns = [name.title() for name in raw.columns]
        adapter = YahooAdapter()
        with patch("src.data.yahoo_adapter.yf.Ticker") as ticker:
            ticker.return_value.history.return_value = raw
            adapter.fetch_ohlcv("^NDX", "1m", since=pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=100))
        self.assertTrue(adapter.fetch_notices[("^NDX", "1m")])
        self.assertEqual(database_summary(self.db.db_path)["candles"], 80)

    def test_pair_health_tracks_both_assets(self):
        self.db.save_candles(self.df.assign(close=self.df.close * 2), "ETH/USDT", "1D", "binance")
        dy, dx = self.db.load_candles("BTC/USDT", "1D"), self.db.load_candles("ETH/USDT", "1D")
        res = {"timestamp": dy.timestamp.iloc[-1], "p_value": .2, "beta": 1, "is_cointegrated": False, "pct_coint_windows": 0}
        self.db.save_cointegration_result("BTC/ETH", "1D", res["timestamp"], res,
            [dy.attrs["data_version"], dx.attrs["data_version"]], {})
        self.db.save_candles(self.df.assign(close=self.df.close * 2 + 1), "ETH/USDT", "1D", "binance")
        self.assertEqual(self.db.get_calculation_health({"cointegration": {}})[0]["status"], "stale")

    def test_gap_detection_and_dst_do_not_treat_weekend_as_missing_bars(self):
        missing = fixture(4, "2026-10-02 14:00", "min").drop(index=1)
        self.assertTrue(recent_gaps(missing, "BTC/USDT", "1m", "binance"))
        market = fixture(2, "2026-10-02", "D")
        market["timestamp"] = pd.to_datetime(["2026-10-02 19:59Z", "2026-10-05 13:30Z"])
        self.assertEqual(recent_gaps(market, "^NDX", "1m", "yahoo"), [])
        self.assertEqual(candle_end("2026-10-30 04:00Z", "^NDX", "1D", "yahoo").hour, 20)
        self.assertEqual(candle_end("2026-11-02 05:00Z", "^NDX", "1D", "yahoo").hour, 21)
        lunch = pd.DataFrame({"timestamp": pd.to_datetime(["2026-10-02 02:29Z", "2026-10-02 03:30Z"])})
        self.assertEqual(recent_gaps(lunch, "^N225", "1m", "yahoo"), [])

    def test_latest_formulas_match_full_history_with_nondefault_parameters(self):
        df = fixture(600)
        cfg = {"ema_period": 34, "adx_period": 12, "atr_period": 10, "atr_percentile_window": 120,
               "volatility_low_pct": 20, "volatility_high_pct": 80, "adx_threshold_lateral": 18, "weak_trend_z": 2.5}
        history = compute_market_regime_history(df, **cfg).iloc[-1]
        latest = get_latest_market_regime(df, cfg)
        self.assertEqual(latest["regime"], history["regime"])
        for key in ["ema", "adx", "atr", "atr_percentile"]:
            self.assertAlmostEqual(latest[key], history[key], places=10)
        for mean_type in ["ema", "sma"]:
            zcfg = {"mean_type": mean_type, "period": 34, "std_period": 40, "atr_period": 10, "percentile_window": 120}
            hist = compute_zscore_history(df, **zcfg).iloc[-1]
            z = get_latest_zscore(df, zcfg)
            for key in ["z_atr", "z_std", "z_percentile"]:
                self.assertAlmostEqual(z[key], hist[key], places=10)

    def test_scheduler_paths_with_spaces_and_no_automatic_install(self):
        mac = mac_definition("/Users/nico/Mis cosas/.venv/bin/python", "/Users/nico/Mis cosas/backup_data.py", self.root, 21, 15)
        self.assertEqual(len(mac["ProgramArguments"]), 2)
        self.assertEqual(mac["StartCalendarInterval"]["Minute"], 15)
        xml = windows_definition(r"C:\Mis cosas\.venv\Scripts\python.exe", r"C:\Mis cosas\backup_data.py", 21, 15, r"PC\nico")
        tree = ET.fromstring(xml)
        ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        self.assertEqual(tree.find(".//t:Arguments", ns).text, '"C:\\Mis cosas\\backup_data.py"')
        self.assertEqual(tree.find(".//t:StartWhenAvailable", ns).text, "true")

    def test_missing_last_close_remains_missing_not_an_invented_number(self):
        df = fixture(100)
        df.loc[df.index[-1], "close"] = np.nan
        reg = get_latest_market_regime(df)
        z = get_latest_zscore(df)
        self.assertIsNone(reg["close"])
        self.assertIsNone(z["close"])
        self.assertIsNone(z["z_atr"])
        self.assertEqual(reg["direction"], compute_market_regime_history(df).direction.iloc[-1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
