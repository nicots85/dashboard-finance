"""Argentina: CCL implícito, dispersión, sesiones BYMA/NY y foto versionada."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from src.argentina_math import common_window, ccl_series, session_four_hour, dispersion, median_reading
from src.data.backup import ROOT, snapshot_database
from src.data.db_manager import DEFAULT_DB_PATH, DatabaseManager
from src.data.snapshots import list_photos, take_snapshot, get_photo, SCHEMA_VERSION
from testing_clock import monotonic_apptest_wait


def bars(index, closes, session=None):
    index = pd.to_datetime(index, utc=True)
    return pd.DataFrame({"timestamp": index, "open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": 100., "session": session or index.strftime("%Y-%m-%d"),
                         "bar_end": index + pd.Timedelta(minutes=15), "closed": True})


BYMA = {"calendar": "XBUE", "timezone": "America/Argentina/Buenos_Aires", "open": "11:00", "close": "17:00",
        "four_hour": ["11:00-15:00", "15:00-17:00"], "label": "BYMA"}
NYSE = {"calendar": "NYSE", "timezone": "America/New_York", "open": "09:30", "close": "16:00",
        "four_hour": ["09:30-13:30", "13:30-16:00"], "label": "NYSE"}


class ArgentinaMathTests(unittest.TestCase):
    def test_ccl_is_local_times_ratio_over_adr(self):
        local = bars(["2026-10-09"], [1000.0])
        adr = bars(["2026-10-09"], [25.0])
        self.assertAlmostEqual(float(ccl_series(local, adr, 10).iloc[-1]), 400.0)
        self.assertAlmostEqual(float(ccl_series(local, adr, 1).iloc[-1]), 40.0)

    def test_ccl_needs_the_same_session_or_timestamp(self):
        local = bars(["2026-10-08", "2026-10-09"], [1000.0, 1010.0])
        adr = bars(["2026-10-09"], [25.0])
        self.assertEqual([str(d) for d in ccl_series(local, adr, 10).index], ["2026-10-09"])

    def test_common_window_follows_real_dst(self):
        summer, summer_end = common_window(pd.Timestamp("2026-10-09 12:00", tz="UTC"), BYMA, NYSE)
        self.assertEqual(summer.strftime("%H:%M"), "14:00")
        self.assertEqual(summer_end.strftime("%H:%M"), "20:00")
        winter, winter_end = common_window(pd.Timestamp("2026-11-10 12:00", tz="UTC"), BYMA, NYSE)
        self.assertEqual(winter.strftime("%H:%M"), "14:30")
        self.assertEqual(winter_end.strftime("%H:%M"), "20:00")

    def test_session_four_hour_splits_byma_and_keeps_the_short_block(self):
        day = "2026-10-09"
        local_times = pd.date_range(f"{day} 14:00", f"{day} 20:00", freq="15min", tz="UTC")
        frame = bars(local_times, range(len(local_times)))
        result = session_four_hour(frame, BYMA, pd.Timestamp("2026-10-10 00:00", tz="UTC"))
        self.assertEqual([value.strftime("%H:%M") for value in result.timestamp], ["14:00", "18:00"])
        self.assertEqual([value.strftime("%H:%M") for value in result.bar_end], ["18:00", "20:00"])
        self.assertEqual(result.iloc[1].volume, 8 * 100.)
        # 11:00–15:00 tiene 16 velas de quince minutos; 15:00–17:00 tiene 8.
        self.assertEqual(result.iloc[0].volume, 16 * 100.)

    def test_dispersion_highlights_only_beyond_the_threshold(self):
        frame = pd.DataFrame({"A": [100.0, 100.0], "B": [100.0, 105.0], "C": [100.0, 99.0]},
                             index=pd.to_datetime(["2026-10-08", "2026-10-09"]))
        rows = {row["company"]: row for row in dispersion(frame, 2.0)}
        self.assertTrue(rows["B"]["highlight"])
        self.assertFalse(rows["C"]["highlight"])
        self.assertFalse(rows["A"]["highlight"])
        self.assertAlmostEqual(rows["B"]["vs_median_pct"], 5.0, places=6)

    def test_median_change_uses_five_sessions(self):
        history = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0, 110.0],
                            index=pd.date_range("2026-10-01", periods=6))
        reading = median_reading(history)
        self.assertAlmostEqual(reading["change_5"], 10.0)
        self.assertTrue(reading["last_session"].startswith("2026-10-06"))


class ArgentinaAppTests(unittest.TestCase):
    def test_six_tabs_argentina_ccl_sessions_and_photo(self):
        monotonic_apptest_wait()
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "argentina.db")
            snapshot_database(DEFAULT_DB_PATH, db)
            count = len(list_photos(db))
            report = {"generated_at": pd.Timestamp.now(tz="UTC").isoformat()}
            with patch("src.data.db_manager.DEFAULT_DB_PATH", db), patch("src.data.DatabaseManager", side_effect=lambda *a, **k: DatabaseManager(db)):
                app = AppTest.from_file(str(ROOT / "app/main.py"), default_timeout=2400).run()
                self.assertFalse(app.exception, [e.value for e in app.exception])
                self.assertEqual(len(app.tabs), 6)
                tab = app.tabs[5]
                labels = [m.label for m in tab.metric]
                for title in ("CCL implícito mediano", "Distancia del CCL a su media", "Acciones locales que suben", "Mayor separación de la media"):
                    self.assertIn(title, labels)
                texts = " ".join([c.value for c in tab.caption] + [i.value for i in tab.info] + [d.value for d in tab.subheader])
                self.assertIn("tendencia", texts)
                self.assertIn("14:00", texts)
                table = [d for d in tab.dataframe if list(d.value.columns)[:1] == ["Empresa"]][0]
                self.assertEqual(len(table.value), 5)
                self.assertIn("YPF", " ".join(table.value["Empresa"]))
                self.assertTrue(any("BYMA" in c.value for c in tab.caption))
                self.assertTrue(any(e.label.startswith("Relaciones entre") for e in tab.expander))
                self.assertFalse(any(s.key == "argentina_pilot_pair" for s in tab.selectbox))
                self.assertFalse(any(s.key == "argentina_pilot_pair_tf" for s in tab.selectbox))
                self.assertTrue(any("no se usa cointegración" in i.value.lower() for i in tab.info) or
                                any("brecha" in c.value.lower() for c in tab.caption))
                report["metrics"] = [{"label": m.label, "value": m.value, "delta": m.delta} for m in tab.metric]
                report["ccl"] = table.value.to_dict("records")
                report["captions"] = [c.value for c in tab.caption]
                report["warnings"] = [w.value for w in tab.warning]
                app.selectbox(key="argentina_pilot_tf").set_value("15m").run()
                self.assertTrue(any("VWAP" in c.value or "sesión" in c.value.lower() for c in app.tabs[5].caption))
                app.selectbox(key="argentina_pilot_tf").set_value("4h").run()
                self.assertTrue(any("4h de sesión" in c.value for c in app.tabs[5].caption))
            self.assertEqual(len(list_photos(db)), count)
            photo = get_photo(take_snapshot(db, trigger="test_argentina"), db)
            self.assertEqual(photo["content"]["schema_version"], SCHEMA_VERSION)
            stored = photo["content"]["sections"]["argentina"]
            kpis = stored["kpis"]
            self.assertEqual(len(kpis["ccl_by_company"]), 5)
            self.assertIn("median", kpis["median"])
            self.assertIn("change_5", kpis["median"])
            self.assertIn("dispersion_reference", kpis)
            self.assertIn("BYMA", " ".join(stored["regular_sessions"]))
            self.assertTrue(all(not spec["include_premarket"] for spec in stored["regular_sessions"].values()))
            self.assertIn("four_hour", stored["regular_sessions"]["BYMA 11:00–17:00 Buenos Aires"])
            self.assertTrue(stored["ccl"]["by_company"])
            self.assertIsNotNone(stored["ccl"]["median"])
            target = os.environ.get("ARGENTINA_READING_OUTPUT")
            if target:
                Path(target).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))
                print("\nArgentina de esta corrida: " + report["generated_at"], flush=True)
                for row in report["ccl"]:
                    print(f"- {row['Empresa']}: {row['CCL implícito']} · {row['% vs mediana']} · {row['Estado']}", flush=True)
                for metric in report["metrics"][:4]:
                    print(f"- {metric['label']}: {metric['value']} · {metric['delta']}", flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)