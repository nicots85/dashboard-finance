"""Cambios intencionales de Cripto; Índices/Metales y resto de Cripto intactos."""
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


class CryptoAdjustmentRegression(unittest.TestCase):
    def test_requested_crypto_adjustments_are_scoped(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            db = tmp / "same.db"
            snapshot_database(DEFAULT_DB_PATH, str(db))
            old = tmp / "approved_crypto"
            subprocess.run(["git", "worktree", "add", "--detach", str(old), "5ea8fa6"], cwd=ROOT,
                           check=True, capture_output=True)
            try:
                env = dict(os.environ, FINANCE_DB_PATH=str(db), OPENBLAS_NUM_THREADS="1",
                           OMP_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1")
                dumps = {}
                for name, repo in (("before", old), ("after", ROOT)):
                    output = tmp / f"{name}.json"
                    result = subprocess.run([sys.executable, "-B", str(ROOT / "_group4_dump.py"), str(repo), str(output)],
                                            cwd=repo, env=env, capture_output=True, text=True, timeout=3600)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr[-9000:])
                    dumps[name] = json.loads(output.read_text(encoding="utf-8"))
                reports = {}
                for section in ("indices", "metales", "cripto"):
                    a = {k: v for k, v in dumps["before"]["readings"].items() if k.endswith("/" + section)}
                    b = {k: v for k, v in dumps["after"]["readings"].items() if k.endswith("/" + section)}
                    reports[section] = compare(a, b)
                reports["cripto_fuera_de_ajustes"] = compare(dumps["before"]["unaffected_crypto"], dumps["after"]["unaffected_crypto"])
                for name, report in reports.items():
                    print(f"\n{name}: {report['elements_compared']} elementos comparados; {report['differences']} diferencias")
                target = os.environ.get("CRYPTO_ADJUSTMENTS_OUTPUT_DIR")
                if target:
                    folder = Path(target)
                    folder.mkdir(parents=True, exist_ok=True)
                    for name, dump in dumps.items():
                        (folder / f"{name}.json").write_text(json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8")
                    (folder / "report.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
                for name in ("indices", "metales", "cripto_fuera_de_ajustes"):
                    self.assertEqual(reports[name]["differences"], 0, f"Cambió {name} fuera de los ajustes pedidos")
                self.assertGreater(reports["cripto"]["differences"], 0)
            finally:
                subprocess.run(["git", "worktree", "remove", "--force", str(old)], cwd=ROOT,
                               check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
