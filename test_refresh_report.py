"""No confundir claves nuevas, correcciones y reconstrucciones."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.data.db_manager import DatabaseManager
from src.data.backup import snapshot_database
from refresh_and_report import changes


class RefreshReportTests(unittest.TestCase):
    def test_new_keys_and_price_corrections_are_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            before, after = Path(tmp) / "before.db", Path(tmp) / "after.db"
            DatabaseManager(str(before))
            with sqlite3.connect(before) as conn:
                conn.execute("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?)", ("BTC/USDT", "1m", "2026-01-01T00:00:00Z", 10, 10, 10, 10, 1, "binance", "2026-01-01"))
                conn.execute("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?)", ("IWM", "4h", "2026-01-01T00:00:00Z", 10, 10, 10, 10, 1, "old", "2026-01-01"))
            snapshot_database(before, after)
            with sqlite3.connect(after) as conn:
                conn.execute("UPDATE candles SET close=11 WHERE symbol='BTC/USDT'")
                conn.execute("DELETE FROM candles WHERE symbol='IWM'")
                conn.execute("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?)", ("BTC/USDT", "1m", "2026-01-01T00:01:00Z", 12, 12, 12, 12, 1, "binance", "2026-01-01"))
            result = changes(before, after)
            self.assertEqual(sum(r["count"] for r in result["added"]), 1)
            self.assertEqual(sum(r["count"] for r in result["corrected"]), 1)
            self.assertEqual(sum(r["count"] for r in result["removed"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
