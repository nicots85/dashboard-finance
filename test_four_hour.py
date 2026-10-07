"""Verificación de la corrección 4h sobre bases temporales, sin tocar datos reales."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from src.data.db_manager import DatabaseManager
from src.data.four_hour import (build_session, build_future, rebuild_one, series_descriptor,
                               market_results, prepare_stored, sufficient_history)
from src.data.snapshots import take_snapshot, get_photo, ensure_table, section_snapshot
from install_daily_backup import daily_mac_definition, daily_windows_definition
from daily_run import timing, main as daily_main
from datetime import datetime, timezone
import xml.etree.ElementTree as ET


def hours(start, periods=7, tz="America/New_York"):
    ts = pd.date_range(start, periods=periods, freq="h", tz=tz).tz_convert("UTC")
    close = np.arange(periods, dtype=float) + 100
    return pd.DataFrame({"timestamp": ts, "open": close-.1, "high": close+1,
                         "low": close-1, "close": close, "volume": np.ones(periods)})


class FourHourTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "test.db"
        self.db = DatabaseManager(self.path)
    def tearDown(self):
        self.tmp.cleanup()

    def test_two_session_bars_from_hours(self):
        frame, quality = build_session(hours("2026-10-05 09:30"), "2026-10-06")
        self.assertEqual(frame.timestamp.tolist(), [pd.Timestamp("2026-10-05 13:30Z"), pd.Timestamp("2026-10-05 17:30Z")])
        self.assertEqual(frame.volume.tolist(), [4, 3])
        self.assertEqual(frame.close.tolist(), [103, 106])
        self.assertEqual(quality["omitted"], 0)

    def test_session_dst_and_short_second_bar(self):
        frame, _ = build_session(hours("2026-11-02 09:30"), "2026-11-03")
        frame["source"] = "session_4h_us"
        prepared = prepare_stored(frame, "IWM", "2026-11-03")
        self.assertEqual(frame.timestamp.iloc[0], pd.Timestamp("2026-11-02 14:30Z"))
        self.assertEqual((prepared.bar_end-prepared.timestamp).dt.total_seconds().tolist(), [14400, 9000])

    def test_early_close_has_only_first_partial_session(self):
        frame, _ = build_session(hours("2026-11-27 09:30", 4), "2026-11-28")
        self.assertEqual(len(frame), 1)
        frame["source"] = "session_4h_us"
        self.assertEqual(prepare_stored(frame, "AAPL", "2026-11-28").bar_end.iloc[0], pd.Timestamp("2026-11-27 18:00Z"))

    def test_future_utc_and_overnight_are_not_clipped_to_index_market(self):
        raw = hours("2026-10-05 20:00", 4, "UTC")
        # 21 UTC es mantenimiento: el grupo conserva 20,22,23 del futuro.
        raw = raw[raw.timestamp.dt.hour != 21]
        frame, _ = build_future(raw, {"timezone":"UTC", "starts":[f"{h:02}:00" for h in range(0,24,4)]}, "2026-10-06 01:00Z")
        self.assertEqual(len(frame), 1)
        frame["source"] = "via NQ=F"
        p = prepare_stored(frame, "^NDX", "2026-10-06 01:00Z")
        self.assertEqual(p.bar_end.iloc[0], pd.Timestamp("2026-10-06 00:00Z"))
        self.assertEqual(p.session.iloc[0], "2026-10-06")

    def test_missing_hour_is_not_fabricated(self):
        raw = hours("2026-10-05 09:30").drop(index=1)
        frame, quality = build_session(raw, "2026-10-06")
        self.assertEqual(len(frame), 1)
        self.assertEqual(quality["omitted"], 1)

    def test_existing_utc_bar_before_market_open_is_preserved(self):
        frame = hours("2026-10-05 04:00", 1, "UTC")
        frame["source"] = "yahoo"
        prepared = prepare_stored(frame, "^GDAXI", "2026-10-06")
        self.assertEqual(len(prepared), 1)
        self.assertEqual(prepared.bar_end.iloc[0], pd.Timestamp("2026-10-05 08:00Z"))
        self.assertTrue(prepared.closed.iloc[0])

    def test_guard_needs_250_valid_atr_not_250_total(self):
        df = hours("2025-01-01", 262, "UTC")
        self.assertFalse(sufficient_history(df, {})[0])
        reg, z = market_results(df, {})
        self.assertEqual(reg["regime"], "Historia insuficiente en 4h")
        self.assertEqual(reg["direction"], "sin datos")
        self.assertIsNone(z["z_atr"])
        self.assertTrue(sufficient_history(hours("2025-01-01", 263, "UTC"), {})[0])

    def test_guard_rejects_invalid_atr_even_with_enough_rows(self):
        frame = hours("2025-01-01", 263, "UTC")
        frame.loc[frame.index[-1], ["high", "low", "close"]] = np.nan
        self.assertFalse(sufficient_history(frame, {})[0])
        regime, z = market_results(frame, {})
        self.assertEqual(regime["direction"], "sin datos")
        self.assertIsNone(z["z_percentile"])

    def test_rebuild_archives_legacy_and_is_idempotent(self):
        raw = hours("2026-10-05 09:30")
        self.db.save_candles(raw, "IWM", "1h", "yahoo")
        old = raw.iloc[[0]].copy()
        self.db.save_candles(old, "IWM", "4h", "yahoo")
        first = rebuild_one(self.db, "IWM", "2026-10-06")
        self.assertTrue(first["changed"])
        self.assertEqual(len(self.db.load_candles("IWM", "4h_legacy")), 1)
        before = self.db.load_candles("IWM", "4h").attrs["data_version"]["revision"]
        again = rebuild_one(self.db, "IWM", "2026-10-06")
        self.assertFalse(again["changed"])
        self.assertEqual(self.db.load_candles("IWM", "4h").attrs["data_version"]["revision"], before)
        self.assertEqual(len(self.db.load_candles("IWM", "4h_legacy")), 1)

    def test_empty_source_does_not_remove_existing_series(self):
        old = hours("2026-10-05", 1, "UTC")
        self.db.save_candles(old, "^NDX", "4h", "yahoo")
        with self.assertRaises(ValueError):
            rebuild_one(self.db, "^NDX")
        self.assertEqual(len(self.db.load_candles("^NDX", "4h")), 1)

    def test_old_photo_is_marked_without_editing_json(self):
        payload = json.dumps({"schema_version":1,"sections":{}})
        with sqlite3.connect(self.path) as conn:
            ensure_table(conn)
            conn.execute("INSERT INTO snapshot_photos VALUES (?,?,?,?,?,?,?,?,?,?,?)", ("old","2026-10-01T00:00:00Z","Mac","daily","ok",0,"v1","hash","[]","[]",payload))
        photo = get_photo("old", str(self.path))
        self.assertEqual(photo["four_hour_label"], "4h antigua")
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute("SELECT sections_json FROM snapshot_photos WHERE id='old'").fetchone()[0], payload)

    def test_new_photo_records_actual_calculation_series(self):
        self.db.save_candles(hours("2026-10-05 09:30"), "IWM", "1h", "yahoo")
        rebuilt = rebuild_one(self.db, "IWM", "2026-10-06")
        frame = self.db.load_candles("IWM", "4h")
        regime, _ = market_results(frame, {})
        regime["series_version"] = rebuilt["version"]
        self.db.save_regime_result("IWM", "4h", regime, [frame.attrs["data_version"]], {})
        photo = get_photo(take_snapshot(str(self.path)), str(self.path))
        asset = next(a for a in photo["content"]["sections"]["smallcaps"]["assets"] if a["symbol"] == "IWM")
        descriptor = asset["timeframes"]["4h"]["series_4h"]
        self.assertEqual(photo["four_hour_label"], "4h versionada")
        self.assertEqual(descriptor["version"], rebuilt["version"])
        self.assertEqual(descriptor["method"], "session_us")
        self.assertEqual(descriptor["reference"], "IWM")
        self.assertEqual(descriptor["starts"], ["09:30", "13:30"])

    def test_unversioned_result_does_not_claim_current_future_source(self):
        frame = hours("2026-10-05 20:00", 4, "UTC")
        self.db.save_candles(frame, "NQ=F", "1h", "yahoo")
        rebuild_one(self.db, "^NDX", "2026-10-06")
        regime, _ = market_results(frame, {})
        self.db.save_regime_result("^NDX", "4h", regime)
        with sqlite3.connect(self.path) as conn:
            section = section_snapshot(conn, "indices", {"indices": {"activos": ["^NDX"]}})
        tf = section["assets"][0]["timeframes"]["4h"]
        self.assertEqual(tf["series_4h"]["version"], "4h-antigua")
        self.assertEqual(tf["series_4h"]["method"], "legacy")
        self.assertEqual(tf["series_4h"]["reference"], "^NDX")
        self.assertNotIn("vía", tf["display_name"])

    def test_due_uses_buenos_aires_and_catchup_is_late(self):
        activation = datetime(2026,10,1,tzinfo=timezone.utc)
        now = datetime(2026,10,6,13,0,tzinfo=timezone.utc)  # volvió a las 10 ART
        due, active, late = timing(now, activation)
        self.assertEqual(due.isoformat(), "2026-10-05T21:15:00-03:00")
        self.assertTrue(active)
        self.assertTrue(late)
        _, _, punctual = timing(datetime(2026,10,6,0,15,tzinfo=timezone.utc), activation)
        self.assertFalse(punctual)

    def test_daily_run_is_once_and_slow_update_marks_actual_photo_late(self):
        times = iter([datetime(2026, 10, 7, 0, 15, tzinfo=timezone.utc),
                      datetime(2026, 10, 7, 1, 15, tzinfo=timezone.utc),
                      datetime(2026, 10, 7, 1, 16, tzinfo=timezone.utc)])
        class FixedClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return next(times)
        args = ["daily_run.py", "--scheduled", "--db", str(self.path),
                "--activated-at", "2026-10-06T00:00:00+00:00"]
        with patch("sys.argv", args), patch("daily_run.datetime", FixedClock), patch(
            "daily_run.subprocess.run"
        ) as run, patch("daily_run.take_snapshot", return_value="real-photo") as snapshot:
            run.return_value.returncode = 0
            self.assertEqual(daily_main(), 0)
            self.assertEqual(daily_main(), 0)
            self.assertEqual(run.call_count, 3)
            snapshot.assert_called_once()
            self.assertTrue(snapshot.call_args.kwargs["late"])

    def test_schedule_prepared_not_installed_and_contains_real_zone(self):
        args = ("/venv/python", "/repo/daily_run.py", Path(self.tmp.name), 21, 15, "America/Argentina/Buenos_Aires", "2026-10-01T00:00:00+00:00")
        definition = daily_mac_definition(*args)
        self.assertIn("--scheduled", definition["ProgramArguments"])
        self.assertIn("America/Argentina/Buenos_Aires", definition["ProgramArguments"])
        self.assertEqual(definition["StartInterval"], 60)
        xml = daily_windows_definition(args[0], args[1], *args[3:], username="PC\\Nico")
        root = ET.fromstring(xml)
        ns={"t":"http://schemas.microsoft.com/windows/2004/02/mit/task"}
        self.assertIn("America/Argentina/Buenos_Aires", root.find(".//t:Arguments",ns).text)
        self.assertEqual(root.find(".//t:Interval",ns).text,"PT1M")


if __name__ == "__main__":
    unittest.main(verbosity=2)
