"""Regresión AppTest real: 63c8401 vs 26e1a77, y 63c8401 vs código actual.

Todas las versiones usan la MISMA copia consistente de finance.db. Los dos
commits históricos se ejecutan en git worktrees aislados. Se comparan tablas,
valores formateados, indicadores, ayudas, textos, desplegables y todas las trazas
de cada gráfico (incluyendo cointegración y detalle 1h/4h). No hay opt-in ni
saltos de pruebas: un timeout o una excepción es un fallo.
REGRESSION_OUTPUT_DIR permite conservar los volcados y el informe de la corrida.
"""
import difflib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from src.data.backup import snapshot_database
from src.data.db_manager import DEFAULT_DB_PATH

ROOT = Path(__file__).resolve().parent


def compare(old, new):
    differences = []
    compared = 0
    for state in sorted(set(old) | set(new)):
        a, b = old.get(state, []), new.get(state, [])
        compared += max(len(a), len(b))
        # Alinear inserciones/borrados sin contar como distintos los nodos corridos.
        encode = lambda values: [json.dumps(v, sort_keys=True, ensure_ascii=False) for v in values]
        matcher = difflib.SequenceMatcher(a=encode(a), b=encode(b), autojunk=False)
        for kind, i, end_i, j, end_j in matcher.get_opcodes():
            if kind != "equal":
                differences.append({"state": state, "operation": kind,
                                    "old": a[i:end_i], "new": b[j:end_j]})
    return {"elements_compared": compared,
            "differences": sum(max(len(d["old"]), len(d["new"])) for d in differences),
            "details": differences}


class PilotRegression(unittest.TestCase):
    def test_complete_apptest_regression(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            db = tmp / "finance.db"
            snapshot_database(DEFAULT_DB_PATH, str(db))
            worktrees = []
            try:
                repos = {"current": ROOT}
                for name, commit in [("old", "63c8401"), ("refactor", "26e1a77")]:
                    repo = tmp / name
                    subprocess.run(["git", "worktree", "add", "--detach", str(repo), commit],
                                   cwd=ROOT, check=True, capture_output=True, text=True)
                    worktrees.append(repo)
                    repos[name] = repo
                env = dict(os.environ, FINANCE_DB_PATH=str(db), OPENBLAS_NUM_THREADS="1",
                           OMP_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1")

                def dump(name):
                    output = tmp / f"{name}.json"
                    cmd = [sys.executable, "-B", str(ROOT / "_regdump.py"), str(repos[name]), str(output)]
                    if name == "refactor":
                        cmd.append("--original")
                    result = subprocess.run(cmd, cwd=repos[name], env=env, capture_output=True,
                                            text=True, timeout=1800)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr[-6000:])
                    return json.loads(output.read_text(encoding="utf-8"))

                # Procesos independientes, secuenciales: tres apps simultáneas
                # con esta base real causan presión de memoria y timeouts.
                dumps = {name: dump(name) for name in repos}
                original_old = {key: dumps["old"][key] for key in dumps["refactor"]}
                report = {"63c8401_vs_26e1a77": compare(original_old, dumps["refactor"]),
                          "63c8401_vs_current": compare(dumps["old"], dumps["current"])}
                self.assertGreater(report["63c8401_vs_26e1a77"]["differences"], 0,
                                   "La prueba debe detectar las regresiones reales del primer refactor")
                for name, result in report.items():
                    print(f"\n{name}: {result['elements_compared']} elementos comparados; {result['differences']} diferencias")
                    for detail in result["details"]:
                        print(f"- {detail['state']}: {detail['operation']} · {len(detail['old'])} anteriores / {len(detail['new'])} actuales")
                destination = os.environ.get("REGRESSION_OUTPUT_DIR")
                if destination:
                    folder = Path(destination)
                    folder.mkdir(parents=True, exist_ok=True)
                    for name in dumps:
                        shutil.copyfile(tmp / f"{name}.json", folder / f"{name}.json")
                    (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                self.assertEqual(report["63c8401_vs_current"]["differences"], 0,
                                 "Hay diferencias reales de Índices: consultar report.json")
            finally:
                for repo in worktrees:
                    subprocess.run(["git", "worktree", "remove", "--force", str(repo)],
                                   cwd=ROOT, check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
