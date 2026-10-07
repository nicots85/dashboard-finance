"""Prueba de integración 4h e historial sobre una copia SQLite de los datos reales."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from src.data.backup import ROOT, snapshot_database
from src.data.db_manager import DEFAULT_DB_PATH, DatabaseManager
from src.data.snapshots import get_photo, list_photos, take_snapshot


class FourHourAppTests(unittest.TestCase):
    def test_four_hour_views_and_versioned_history_do_not_create_photos(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "app_test.db")
            snapshot_database(DEFAULT_DB_PATH, path)
            photo_id = take_snapshot(path, trigger="integration_test")
            original = get_photo(photo_id, path)["content"]
            count = len(list_photos(path))
            with patch("src.data.db_manager.DEFAULT_DB_PATH", path), patch(
                "src.data.DatabaseManager", side_effect=lambda *a, **k: DatabaseManager(path)
            ):
                app = AppTest.from_file(str(ROOT / "app/main.py"), default_timeout=600)
                for key, value in {
                    "pilot_tf": "4h", "pilot_reference_^NDX": "NQ=F",
                    "tf_indices": "4h", "tf_metales": "4h", "tf_cripto": "4h",
                    "tf_equity": "4h", "sym_equity": "AAPL",
                    "tf_smallcaps": "4h", "sym_smallcaps": "IWM",
                    "tf_argentina": "4h", "sym_argentina": "GGAL",
                    "hist_view": "Elegir foto", "hist_photo": photo_id,
                }.items():
                    app.session_state[key] = value
                app.run()
                self.assertFalse(app.exception, [e.value for e in app.exception])
                self.assertEqual(len(app.tabs), 6)
                captions = "\n".join(e.value for e in app.caption)
                self.assertIn("Nasdaq 100 (vía NQ=F)", captions)
                self.assertIn("4h de sesión: 09:30–13:30 y 13:30–16:00 NY", captions)
                self.assertIn("Serie usada en esa foto: 4h versionada", captions)
                self.assertTrue(any(e.label == "Versiones 4h de esa foto" for e in app.expander))
                self.assertTrue(any("4h-v2-future_utc" in e.value for e in app.markdown))
                app.selectbox(key="pilot_reference_^NDX").set_value("QQQ").run()
                self.assertFalse(app.exception, [e.value for e in app.exception])
                self.assertTrue(any("4h de sesión" in e.value for e in app.caption))
            self.assertEqual(len(list_photos(path)), count)
            self.assertEqual(get_photo(photo_id, path)["content"], original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
