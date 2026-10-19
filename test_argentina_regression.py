"""Argentina no altera ninguna de las otras cinco pestanas aprobadas."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.data.backup import ROOT
from testing_frozen import frozen_state
from test_regression import compare

BASELINE = "676a14a"
NOTA = "Al evaluar muchos pares, algunos aparecerán como «intermitentes» por azar. Tomalo como una pista débil, no como una señal."


def _texto(node):
    """Texto visible de un nodo, sea markdown, write o caption."""
    if not isinstance(node, dict):
        return None
    content = node.get("content")
    if isinstance(content, dict):
        for clave in ("value", "body", "label"):
            if isinstance(content.get(clave), str):
                return content[clave]
    return None


def es_nota_esperada(nuevos, viejos):
    """La única diferencia admitida es la nota agregada a «Cómo leer esto»."""
    if len(nuevos) != 1 or len(viejos) != 1:
        return False
    antes, despues = _texto(viejos[0]), _texto(nuevos[0])
    if antes is None or despues is None:
        return False
    return despues == antes + " " + NOTA


def compare_dumps(dumps):
    reports = {}
    for section in ("indices", "metales", "cripto", "equity", "smallcaps"):
        a = {k: v for k, v in dumps["before"].items() if k.endswith("/" + section)}
        b = {k: v for k, v in dumps["after"].items() if k.endswith("/" + section)}
        if len(a) != 17 or set(a) != set(b):
            raise AssertionError("Perfil incompleto: " + section)
        reports[section] = compare(a, b)
        print(f"{section}: {reports[section]['elements_compared']} elementos; {reports[section]['differences']} diferencias", flush=True)
    return reports


def assert_unchanged(reports):
    """Ninguna diferencia salvo la nota de «Cómo leer esto» de cada escenario."""
    for section, report in reports.items():
        for detail in report.get("details", []):
            if detail["operation"] != "replace" or not es_nota_esperada(detail["new"], detail["old"]):
                raise AssertionError(f"{section}: cambio no explicado en {detail['state']}")
        inesperadas = sum(1 for detail in report.get("details", [])
                          if detail["operation"] != "replace" or not es_nota_esperada(detail["new"], detail["old"]))
        if inesperadas or len(report.get("details", [])) != len(report.get("state_counts", {})):
            raise AssertionError(f"{section}: {inesperadas or len(report.get('details', []))} diferencias inesperadas")
        print(f"{section}: {len(report.get('details', []))} notas esperadas; 0 cambios de cálculo", flush=True)


class SmallcapsRegression(unittest.TestCase):
    def test_five_previous_tabs_are_identical(self):
        db, asof = frozen_state()
        if db is None:
            raise unittest.SkipTest("FINANCE_TEST_FAST_DB sin definir: la regresión rápida se saltea y nunca usa la base grande por accidente")
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            old = folder / "before_argentina"
            subprocess.run(["git", "worktree", "add", "--detach", str(old), BASELINE], cwd=ROOT, check=True, capture_output=True)
            try:
                env = dict(os.environ, FINANCE_DB_PATH=str(db), FINANCE_REGRESSION_ASOF=asof, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1")
                print("Regresión rápida contra `" + str(db) + "` con corte " + asof, flush=True)
                dumps = {}
                for label, repo in (("before", old), ("after", ROOT)):
                    output = folder / (label + ".json")
                    # El script se ejecuta en la raíz de cada versión para aislar
                    # todos los módulos; la misma base íntegra se comparte.
                    result = subprocess.run([sys.executable, "-B", str(ROOT / "_five_tabs_dump.py"), str(repo), str(output)], cwd=repo, env=env,
                                            capture_output=True, text=True, timeout=14000)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr[-12000:])
                    dumps[label] = json.loads(output.read_text())
                    target = os.environ.get("ARGENTINA_REGRESSION_OUTPUT_DIR")
                    if target:
                        directory = Path(target)
                        directory.mkdir(parents=True, exist_ok=True)
                        (directory / (label + ".json")).write_text(json.dumps(dumps[label], ensure_ascii=False, indent=2))
                        (directory / "asof.txt").write_text(asof)
                reports = compare_dumps(dumps)
                target = os.environ.get("ARGENTINA_REGRESSION_OUTPUT_DIR")
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
