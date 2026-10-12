"""La nueva regla cambia cointegración, no precios, KPIs, ratios ni gráficos de precio."""
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


class RuleRegression(unittest.TestCase):
    def test_rule_change_is_scoped_in_four_tabs(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            db = folder / "same.db"
            snapshot_database(DEFAULT_DB_PATH, str(db))
            env = dict(os.environ, FINANCE_DB_PATH=str(db), OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1")
            dumps = {}
            for label, flag in (("before", ["--old-rule"]), ("after", [])):
                output = folder / (label + ".json")
                result = subprocess.run([sys.executable, "-B", str(ROOT / "_rule_dump.py"), str(output), *flag], env=env, cwd=ROOT,
                                        capture_output=True, text=True, timeout=8500)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr[-12000:])
                dumps[label] = json.loads(output.read_text())
            reports = {}
            for section in ("indices", "metales", "cripto", "equity"):
                reports[section] = {}
                for group in ("all", "non_cointegration"):
                    a = {k: v for k, v in dumps["before"][group].items() if k.endswith("/" + section)}
                    b = {k: v for k, v in dumps["after"][group].items() if k.endswith("/" + section)}
                    reports[section][group] = compare(a, b)
                full, untouched = reports[section]["all"], reports[section]["non_cointegration"]
                print(f"\n{section}: {full['elements_compared']} elementos; {full['differences']} diferencias de regla; fuera de cointegración {untouched['differences']}")
                self.assertEqual(untouched["differences"], 0)
            target = os.environ.get("RULE_REGRESSION_OUTPUT_DIR")
            if target:
                destination = Path(target)
                destination.mkdir(parents=True, exist_ok=True)
                for label, value in dumps.items():
                    (destination / (label + ".json")).write_text(json.dumps(value, ensure_ascii=False, indent=2))
                (destination / "report.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
