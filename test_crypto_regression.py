"""Regresión real: agregar Cripto no cambia Índices ni Metales.

La base antes de Cripto es 9014ede: incluye las aclaraciones solicitadas de
Metales (ranking entre los cuatro y campos de fotos). Ambas versiones leen
la misma copia SQLite; se compara TODO el contenido de ambas pestañas.
"""
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

BASELINE = "9014ede"


class CryptoRegression(unittest.TestCase):
    def test_indices_and_metales_unchanged_by_crypto(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            db = folder / "same.db"
            snapshot_database(DEFAULT_DB_PATH, str(db))
            old = folder / "before_crypto"
            subprocess.run(["git", "worktree", "add", "--detach", str(old), BASELINE], cwd=ROOT,
                           check=True, capture_output=True)
            try:
                env = dict(os.environ, FINANCE_DB_PATH=str(db), OPENBLAS_NUM_THREADS="1",
                           OMP_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1")
                dumps = {}
                for name, repo in [("before", old), ("after", ROOT)]:
                    output = folder / f"{name}.json"
                    result = subprocess.run([sys.executable, "-B", str(ROOT / "_step3_dump.py"), str(repo), str(output)],
                                            cwd=repo, env=env, capture_output=True, text=True, timeout=2700)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr[-10000:])
                    dumps[name] = json.loads(output.read_text(encoding="utf-8"))
                reports = {}
                for section in ("indices", "metales"):
                    before = {key: value for key, value in dumps["before"].items() if key.endswith("/" + section)}
                    after = {key: value for key, value in dumps["after"].items() if key.endswith("/" + section)}
                    reports[section] = compare(before, after)
                    report = reports[section]
                    print(f"\n{section}: {report['elements_compared']} elementos comparados; {report['differences']} diferencias")
                destination = os.environ.get("CRYPTO_REGRESSION_OUTPUT_DIR")
                if destination:
                    target = Path(destination)
                    target.mkdir(parents=True, exist_ok=True)
                    for name, dump in dumps.items():
                        (target / f"{name}.json").write_text(json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8")
                    (target / "report.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
                for section, report in reports.items():
                    self.assertEqual(report["differences"], 0, f"Cambió {section}; consultar el volcado de regresión")
            finally:
                subprocess.run(["git", "worktree", "remove", "--force", str(old)], cwd=ROOT,
                               check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
