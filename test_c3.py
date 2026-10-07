"""C3: fotos del historial — no se crean al abrir la app, legibles entre versiones, import/export sin duplicar."""
import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from src.data.db_manager import DEFAULT_DB_PATH
from src.data.snapshots import take_snapshot, list_photos, get_photo, export_photos, import_photos, changes_between, ensure_table, SCHEMA_VERSION


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "t.db")
        from src.data.backup import snapshot_database
        snapshot_database(DEFAULT_DB_PATH, self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_take_and_read_back(self):
        pid = take_snapshot(self.db, trigger="manual_full", status="ok")
        photos = list_photos(self.db)
        self.assertEqual(len(photos), 1)
        p = get_photo(pid, self.db)
        self.assertIn("sections", p["content"])
        self.assertEqual(p["content"]["schema_version"], SCHEMA_VERSION)

    def test_old_schema_version_remains_readable(self):
        conn = sqlite3.connect(self.db)
        ensure_table(conn)
        conn.execute("INSERT INTO snapshot_photos VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            "vieja-1", "2026-10-01T00:00:00+00:00", "m", "daily", "ok", 0, "v0", "h0", '["1D"]', "[]",
            json.dumps({"schema_version": 0, "sections": {"indices": {"assets": [], "pairs": [], "macro": []}}})))
        conn.commit()
        p = get_photo("vieja-1", self.db)
        self.assertEqual(p["content"]["schema_version"], 0)
        self.assertIn("indices", p["content"]["sections"])
        conn.close()

    def test_export_import_does_not_duplicate_exact(self):
        take_snapshot(self.db, trigger="manual_full")
        data = export_photos(self.db)
        result = import_photos(data, self.db)
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["skipped_duplicates"], 1)
        self.assertEqual(len(list_photos(self.db)), 1)

    def test_import_distinct_content_kept_with_new_id(self):
        pid = take_snapshot(self.db, trigger="manual_full")
        data = export_photos(self.db)
        buf = io.BytesIO(data)
        with zipfile.ZipFile(buf) as zf:
            name = zf.namelist()[0]
            payload = json.loads(zf.read(name))
        payload["content"]["sections"]["indices"]["kpis"] = {"top_relative_20d": "^DJI"}
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as zf:
            zf.writestr(name, json.dumps(payload, ensure_ascii=False))
        result = import_photos(out.getvalue(), self.db)
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["kept_distinct"], 1)
        self.assertEqual(len(list_photos(self.db)), 2)

    def test_opening_app_does_not_create_photo(self):
        before = len(list_photos(DEFAULT_DB_PATH))
        from streamlit.testing.v1 import AppTest
        a = AppTest.from_file(str(Path(__file__).parent / "app/main.py"), default_timeout=600).run()
        self.assertFalse(a.exception, [e.value for e in a.exception])
        self.assertEqual(len(list_photos(DEFAULT_DB_PATH)), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
