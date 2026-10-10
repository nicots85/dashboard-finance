"""Indicadores compartidos pantalla/foto y compatibilidad histórica."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.data.backup import ROOT, snapshot_database
from src.data.db_manager import DEFAULT_DB_PATH
from src.data.snapshots import take_snapshot, get_photo, SCHEMA_VERSION
from src.pilot_math import common_performance


class PilotPhotoTests(unittest.TestCase):
    def test_ranking_uses_one_common_period_for_all_assets(self):
        dates = pd.date_range("2026-01-01", periods=23).strftime("%Y-%m-%d")
        series = {"gold": pd.Series(range(100, 123), index=dates),
                  "silver": pd.Series(range(100, 122), index=dates[:22])}
        result = common_performance(series, sessions=20)
        self.assertEqual(result.start_session.nunique(), 1)
        self.assertEqual(result.last_session.nunique(), 1)
        self.assertEqual(result.last_session.iloc[0], dates[21])
        self.assertAlmostEqual(result.return_pct.iloc[0], (121 / 101 - 1) * 100)
        self.assertAlmostEqual(result.return_pct.iloc[1], (121 / 101 - 1) * 100)

    def test_metal_photo_stores_ratios_return_ranking_and_keeps_old_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "photo.db")
            snapshot_database(DEFAULT_DB_PATH, db)
            new_id = take_snapshot(db, trigger="test_pilot_fields")
            photo = get_photo(new_id, db)
            self.assertEqual(photo["content"]["schema_version"], SCHEMA_VERSION)
            metals = photo["content"]["sections"]["metales"]
            ratio = metals["ratios"][0]
            for field in ("ratio", "mean", "distance_pct", "distance_std", "window", "last_session"):
                self.assertIn(field, ratio)
                self.assertIsNotNone(ratio[field])
            self.assertEqual(len(metals["relative_strength"]["between_assets"]), 4)
            self.assertEqual(len(metals["relative_strength"]["against_benchmark"]), 4)
            with sqlite3.connect(db) as conn:
                content = photo["content"]
                content["schema_version"] = 5
                for section in ("metales", "cripto"):
                    for key in ("ratios", "relative_strength", "kpis", "pilot_indicators_calculated_at"):
                        content["sections"][section].pop(key, None)
                original = json.dumps(content, ensure_ascii=False)
                conn.execute("UPDATE snapshot_photos SET sections_json=? WHERE id=?", (original, new_id))
            old = get_photo(new_id, db)
            self.assertNotIn("ratios", old["content"]["sections"]["metales"])
            with sqlite3.connect(db) as conn:
                self.assertEqual(conn.execute("SELECT sections_json FROM snapshot_photos WHERE id=?", (new_id,)).fetchone()[0], original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
