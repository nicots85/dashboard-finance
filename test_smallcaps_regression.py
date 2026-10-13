"""Small caps no altera ninguna de las otras cuatro pestañas aprobadas."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import pandas as pd

from src.data.backup import ROOT, snapshot_database
from src.data.db_manager import DEFAULT_DB_PATH
from test_regression import compare

BASELINE = "f7aef2e"


def compare_dumps(dumps):
    reports = {}
    for section in ("indices", "metales", "cripto", "equity"):
        a = {k: v for k, v in dumps["before"].items() if k.endswith("/" + section)}
        b = {k: v for k, v in dumps["after"].items() if k.endswith("/" + section)}
        if len(a) != 17 or set(a) != set(b):
            raise AssertionError("Perfil incompleto: " + section)
        reports[section] = compare(a, b)
        print(f"{section}: {reports[section]['elements_compared']} elementos; {reports[section]['differences']} diferencias", flush=True)
    return reports


def assert_unchanged(reports):
    for section, report in reports.items():
        if report["differences"]:
            raise AssertionError("Cambió " + section)


class SmallcapsRegression(unittest.TestCase):
    def test_four_previous_tabs_are_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            db = folder / "same.db"
            snapshot_database(DEFAULT_DB_PATH, str(db))
            old = folder / "before_smallcaps"
            subprocess.run(["git", "worktree", "add", "--detach", str(old), BASELINE], cwd=ROOT, check=True, capture_output=True)
            try:
                asof = pd.Timestamp.now(tz="UTC").isoformat()
                env = dict(os.environ, FINANCE_DB_PATH=str(db), FINANCE_REGRESSION_ASOF=asof, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1")
                print("Corte compartido de regresión: " + asof, flush=True)
                dumps = {}
                for label, repo in (("before", old), ("after", ROOT)):
                    output = folder / (label + ".json")
                    # El script se ejecuta en la raíz de cada versión para aislar
                    # todos los módulos; la misma base íntegra se comparte.
                    result = subprocess.run([sys.executable, "-B", str(ROOT / "_four_tabs_dump.py"), str(repo), str(output)], cwd=repo, env=env,
                                            capture_output=True, text=True, timeout=14000)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr[-12000:])
                    dumps[label] = json.loads(output.read_text())
                    target = os.environ.get("SMALLCAPS_REGRESSION_OUTPUT_DIR")
                    if target:
                        directory = Path(target)
                        directory.mkdir(parents=True, exist_ok=True)
                        (directory / (label + ".json")).write_text(json.dumps(dumps[label], ensure_ascii=False, indent=2))
                        (directory / "asof.txt").write_text(asof)
                reports = compare_dumps(dumps)
                target = os.environ.get("SMALLCAPS_REGRESSION_OUTPUT_DIR")
                if target:
                    directory = Path(target)
                    directory.mkdir(parents=True, exist_ok=True)
                    for label, value in dumps.items():
                        (directory / (label + ".json")).write_text(json.dumps(value, ensure_ascii=False, indent=2))
                    (directory / "report.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2))
                assert_unchanged(reports)
            finally:
                subprocess.run(["git", "worktree", "remove", "--force", str(old)], cwd=ROOT, check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
