"""Reglas de Metales: ratio real, Platino diario, benchmark USD y AppTest."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from src.data.backup import ROOT, snapshot_database
from src.data.db_manager import DEFAULT_DB_PATH, DatabaseManager
from src.data.snapshots import list_photos
from src.indices_math import ratio_analysis


class MetalesTests(unittest.TestCase):
    def test_ratio_uses_common_positive_closes_and_sample_deviation(self):
        y = pd.Series([10., 20., 30., 999., 40.], index=["a", "b", "c", "unmatched", "zero"])
        x = pd.Series([10., 10., 10., 0.], index=["a", "b", "c", "zero"])
        result = ratio_analysis(y, x, window=3)
        self.assertEqual(list(result.index), ["a", "b", "c"])
        self.assertEqual(result.ratio.tolist(), [1., 2., 3.])
        self.assertAlmostEqual(result["mean"].iloc[-1], 2.)
        self.assertAlmostEqual(result.distance_pct.iloc[-1], 50.)
        self.assertAlmostEqual(result.distance_std.iloc[-1], 1.)
        self.assertTrue(result["mean"].iloc[:2].isna().all())

    def test_constant_ratio_does_not_invent_dispersion(self):
        dates = pd.date_range("2026-01-01", periods=60)
        result = ratio_analysis(pd.Series(20., index=dates), pd.Series(10., index=dates))
        self.assertEqual(result.distance_pct.iloc[-1], 0.)
        self.assertTrue(np.isnan(result.distance_std.iloc[-1]))

    def test_six_tabs_metales_vwap_platinum_and_cointegration(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = str(Path(temporary) / "app.db")
            snapshot_database(DEFAULT_DB_PATH, path)
            before = len(list_photos(path))
            with patch("src.data.db_manager.DEFAULT_DB_PATH", path), patch(
                "src.data.DatabaseManager", side_effect=lambda *a, **k: DatabaseManager(path)
            ):
                app = AppTest.from_file(str(ROOT / "app/main.py"), default_timeout=1200).run()

                def check():
                    self.assertFalse(app.exception, [e.value for e in app.exception])
                    self.assertEqual(len(app.tabs), 6)

                check()
                metals = app.tabs[1]
                labels = [metric.label for metric in metals.metric]
                for term in ["DGS10", "DFII10", "DTWEXBGS"]:
                    self.assertTrue(any(term in label for label in labels))
                self.assertTrue(any("Fuerza relativa frente al dólar" in h.value for h in metals.subheader))
                self.assertIn("Ratio Oro / Plata", labels)
                self.assertIn("Distancia a la media del ratio", labels)
                # Opciones de AppTest están formateadas para el lector.
                self.assertEqual(list(app.selectbox(key="metales_pilot_pair_tf").options), ["Diario (1D)"])
                app.selectbox(key="metales_pilot_asset").set_value("PL=F").run()
                check()
                self.assertEqual(list(app.selectbox(key="metales_pilot_tf").options), ["Diario (1D)"])
                self.assertTrue(any("volumen intradía es incompleta" in e.value for e in app.tabs[1].info))
                platinum = next(e for e in app.tabs[1].get("plotly_chart") if e.key == "metales_pilot_price_chart")
                traces = json.loads(platinum.proto.spec)["data"]
                self.assertFalse(any("VWAP" in trace.get("name", "") for trace in traces))
                app.selectbox(key="metales_pilot_asset").set_value("GC=F").run()
                app.selectbox(key="metales_pilot_tf").set_value("1h").run()
                check()
                self.assertEqual(list(app.selectbox(key="metales_pilot_vwap_session_GC=F").options),
                                 ["Completa: reinicio 18:00 Nueva York"])
                gold = next(e for e in app.tabs[1].get("plotly_chart") if e.key == "metales_pilot_price_chart")
                self.assertTrue(any("VWAP" in trace.get("name", "") for trace in json.loads(gold.proto.spec)["data"]))
                for pair in [0, 1]:
                    app.selectbox(key="metales_pilot_pair").set_value(pair)
                    app.button(key="metales_pilot_load_pair").click().run()
                    check()
                    self.assertTrue(any("**Estado:" in e.value for e in app.tabs[1].markdown))
                app.selectbox(key="metales_pilot_tf").set_value("4h").run()
                check()
            self.assertEqual(len(list_photos(path)), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
