"""Small caps: ratios completos, sesión NY, fotos y lectura real."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from src.data.backup import ROOT, snapshot_database
from src.data.db_manager import DEFAULT_DB_PATH, DatabaseManager
from src.data.snapshots import list_photos, take_snapshot, get_photo, SCHEMA_VERSION
from src.pilot_math import ratio_reading, smallcaps_indicators
from src.presentation import asset_label
from test_crypto import live_tab, pair_state
from testing_clock import monotonic_apptest_wait


class SmallcapsTests(unittest.TestCase):
    def test_ratio_trend_is_sma_slope_without_synthetic_atr(self):
        days = pd.date_range("2026-01-01", periods=80).strftime("%Y-%m-%d")
        daily = {"IWM": pd.DataFrame({"session": days, "close": np.linspace(100, 140, 80), "source": "yahoo"}),
                 "^GSPC": pd.DataFrame({"session": days, "close": 100., "source": "yahoo"})}
        reading, _ = ratio_reading(daily, {"y": "IWM", "x": "^GSPC", "label": "IWM/S&P 500", "window": 50,
                                          "percentile_window": 250, "trend_period": 5})
        self.assertEqual(reading["trend"], "creciente")
        self.assertGreater(reading["distance_pct"], 0)
        self.assertEqual(reading["y_source"], "yahoo")
        self.assertNotIn("y_exchange", reading)
        self.assertTrue(0 <= reading["percentile"] <= 100)

    def test_four_etfs_are_counted_without_the_external_benchmark(self):
        days = pd.date_range("2026-01-01", periods=80).strftime("%Y-%m-%d")
        daily = {s: pd.DataFrame({"session": days, "close": np.linspace(100, 120, 80), "source": "yahoo"}) for s in ("IWM", "IJR", "IWO", "IWN", "^GSPC")}
        rows = [{"symbol": s, "direction": "alcista" if s != "IWN" else "bajista", "distance_std": 1., "distance_pct": 2.} for s in ("IWM", "IJR", "IWO", "IWN")]
        specs = [{"y": "IWM", "x": "^GSPC", "label": "IWM/S&P 500", "window": 50, "trend_period": 5},
                 {"y": "IWO", "x": "IWN", "label": "IWO/IWN", "window": 50, "trend_period": 5}]
        k = smallcaps_indicators(rows, daily, {"ratios": specs})
        self.assertEqual((k["total"], k["up"], k["down"]), (4, 3, 1))
        self.assertEqual(k["growth_value"]["ratio"], 1.)

    def test_six_tabs_smallcaps_rth_pairs_photos_and_live_values(self):
        monotonic_apptest_wait()
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "small.db")
            snapshot_database(DEFAULT_DB_PATH, db)
            count = len(list_photos(db))
            report = {"calculated_at": pd.Timestamp.now(tz="UTC").isoformat()}
            with patch("src.data.db_manager.DEFAULT_DB_PATH", db), patch("src.data.DatabaseManager", side_effect=lambda *a, **k: DatabaseManager(db)):
                app = AppTest.from_file(str(ROOT / "app/main.py"), default_timeout=2400).run()

                def check():
                    self.assertFalse(app.exception, [e.value for e in app.exception])
                    self.assertEqual(len(app.tabs), 6)

                check()
                tab = app.tabs[3]
                labels = [m.label for m in tab.metric]
                relative_label = asset_label("IWM") + " / " + asset_label("^GSPC")
                growth_label = asset_label("IWO") + " / " + asset_label("IWN")
                for title in ("ETF que suben", "Fuerza relativa " + relative_label, "Crecimiento frente a valor " + growth_label, "Mayor separación de la media", "Percentil de " + relative_label, "Percentil de " + growth_label):
                    self.assertIn(title, labels)
                self.assertEqual(tab.dataframe[0].value.shape, (4, 5))
                self.assertTrue(any("Tendencia del ratio:" in c.value for c in tab.caption))
                report["default"] = live_tab(tab)
                report["pairs"] = {}
                for pair in (0, 1):
                    app.selectbox(key="smallcaps_pilot_pair").set_value(pair)
                    app.button(key="smallcaps_pilot_load_pair").click().run()
                    check()
                    report["pairs"][str(pair)] = pair_state(app.tabs[3])
                    self.assertTrue(any("Evidencia binomial" in c.value for c in app.tabs[3].caption))
                app.selectbox(key="smallcaps_pilot_pair_tf").set_value("1h").run()
                self.assertTrue(any("Historia insuficiente" in e.value for e in app.tabs[3].info))
                for tf in ("15m", "4h"):
                    app.selectbox(key="smallcaps_pilot_tf").set_value(tf).run()
                    check()
                    self.assertTrue(any("sesión regular" in c.value.lower() for c in app.tabs[3].caption))
                    self.assertTrue(any("VWAP de IWM" in c.value for c in app.tabs[3].caption))
                    if tf == "4h":
                        self.assertTrue(any("4h de sesión" in c.value for c in app.tabs[3].caption))
            self.assertEqual(len(list_photos(db)), count)
            photo = get_photo(take_snapshot(db, trigger="test_smallcaps"), db)
            self.assertEqual(photo["content"]["schema_version"], SCHEMA_VERSION)
            stored = photo["content"]["sections"]["smallcaps"]
            self.assertEqual(stored["kpis"]["total"], 4)
            self.assertEqual(len(stored["ratios"]), 2)
            self.assertIn("trend", stored["ratios"][0])
            self.assertEqual(len(stored["pilot_cointegration"]), 2)
            self.assertFalse(stored["regular_session"]["include_premarket"])
            target = os.environ.get("SMALLCAPS_READING_OUTPUT")
            if target:
                Path(target).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))
                print("\nSmall caps de esta corrida: " + report["calculated_at"], flush=True)
                for m in report["default"]["metrics"][:12]:
                    print(f"- {m['label']}: {m['value']} · {m['delta']}", flush=True)
                for c in report["default"]["captions"]:
                    if c.startswith(("Datos al:", "Tendencia del ratio:", "Última sesión común:", "Fecha del dato:")):
                        print("- " + c, flush=True)
                for p, value in report["pairs"].items():
                    print(f"- Par {p}: {value['state']}", flush=True)
                    for c in value["captions"]:
                        if c.startswith(("Evidencia binomial", "Confirmó", "Tramo reciente")):
                            print("- " + c, flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
