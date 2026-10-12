"""Agregar Equity conserva todas las lecturas de Índices, Metales y Cripto."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.data.backup import ROOT, snapshot_database
from src.data.db_manager import DEFAULT_DB_PATH
from test_regression import compare
from historical_regression_fixture import historical_snapshot

BASELINE = "6769e9e"


class EquityRegression(unittest.TestCase):
    def test_three_previous_tabs_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            db = tmp / "same.db"
            historical_snapshot(DEFAULT_DB_PATH, str(db))
            old = tmp / "before_equity"
            subprocess.run(["git", "worktree", "add", "--detach", str(old), BASELINE], cwd=ROOT, check=True, capture_output=True)
            approved = tmp / "approved_equity"
            subprocess.run(["git", "worktree", "add", "--detach", str(approved), "946413f"], cwd=ROOT, check=True, capture_output=True)
            try:
                env = dict(os.environ, FINANCE_DB_PATH=str(db), OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1")
                dumps = {}
                for name, repo in (("before", old), ("approved", approved)):
                    output = tmp / f"{name}.json"
                    result = subprocess.run([sys.executable, "-B", str(ROOT / "_group4_dump.py"), str(repo), str(output)], cwd=repo,
                                            env=env, capture_output=True, text=True, timeout=5400)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr[-9000:])
                    dumps[name] = json.loads(output.read_text(encoding="utf-8"))["readings"]
                reports = {}
                for section in ("indices", "metales", "cripto"):
                    before = {k: v for k, v in dumps["before"].items() if k.endswith("/" + section)}
                    after = {k: v for k, v in dumps["approved"].items() if k.endswith("/" + section)}
                    reports[section] = compare(before, after)
                    print(f"\n{section}: {reports[section]['elements_compared']} elementos comparados; {reports[section]['differences']} diferencias")
                target = os.environ.get("EQUITY_REGRESSION_OUTPUT_DIR")
                if target:
                    folder = Path(target)
                    folder.mkdir(parents=True, exist_ok=True)
                    for name, dump in dumps.items():
                        (folder / f"{name}.json").write_text(json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8")
                    (folder / "report.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
                for section, report in reports.items():
                    self.assertEqual(report["differences"], 0, "Cambió " + section)
            finally:
                subprocess.run(["git", "worktree", "remove", "--force", str(old)], cwd=ROOT, check=True, capture_output=True)
                subprocess.run(["git", "worktree", "remove", "--force", str(approved)], cwd=ROOT, check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
