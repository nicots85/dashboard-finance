"""Regresión OLD vs NEW de la pestaña Índices (sin cambios visibles del refactor).

Compara dos volcados sobre la MISMA base de datos:
  - OLD = código del commit 63c8401 (git worktree, data enlazada = misma DB)
  - NEW = código actual del árbol de trabajo (incluye cambios sin commitear)

Cada volcado tiene:
  - "apptest": vista por defecto de la pestaña Índices vía AppTest, normalizada
               (solo se enmascaran la hora de cálculo y la antigüedad de datos).
  - "model":   datos exactos de view_model + cointegración con RELOJ FIJO.

El test falla si hay diferencias fuera de lo permitido. Los cuerpos de
expanders colapsados se capturan de forma no determinista en modo headless,
por eso la comparación estricta de "apptest" usa solo el nivel superior; el
contenido de expanders se verifica aparte (NEW no debe traer nada que OLD no
tenga) y la data completa se prueba con el "model" de reloj fijo.

Uso:  python -B test_regression.py
Salta automáticamente si no existe data/finance.db.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent
DB = REPO / "data" / "finance.db"
OLD_COMMIT = "63c8401"
DUMPER = str(REPO / "_regdump.py")


def diffs(a, b, path=""):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append(f"{path}.{k}: solo en NEW")
            elif k not in b:
                out.append(f"{path}.{k}: solo en OLD")
            else:
                out += diffs(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: largo {len(a)} (OLD) vs {len(b)} (NEW)")
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                out += diffs(x, y, f"{path}[{i}]")
    elif a != b:
        out.append(f"{path}: {a!r} != {b!r}")
    return out


def signatures(elements):
    s = set()
    for e in elements:
        v = e.get("value")
        if isinstance(v, dict):
            for k, val in v.items():
                s.add((e["type"], k, json.dumps(val, ensure_ascii=False, sort_keys=True)[:120]))
    return s


def run_dumper(app_main_py, out_json):
    result = subprocess.run([sys.executable, "-B", DUMPER, str(app_main_py), str(out_json)],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        tail = "\n".join((result.stderr or "").splitlines()[-25:])
        raise AssertionError(f"_regdump falló para {app_main_py}\n{tail}")


class PilotRegression(unittest.TestCase):
    def test_pilot_indices_igual_old_vs_new(self):
        with tempfile.TemporaryDirectory() as tmp:
            wt = Path(tmp) / "old"
            add = subprocess.run(["git", "-C", str(REPO), "worktree", "add", "--detach", str(wt), OLD_COMMIT],
                                 capture_output=True, text=True, check=False)
            if add.returncode:
                self.skipTest(f"No se pudo crear el worktree de {OLD_COMMIT} (¿historial recortada?): {add.stderr[-200:]}")
            try:
                # El worktree trae data/.gitkeep del checkout; reemplazarlo por un
                # enlace a la MISMA base de datos real (solo lectura en estas rutas).
                data_dir = wt / "data"
                if data_dir.exists():
                    subprocess.run(["rm", "-rf", str(data_dir)], check=True)
                data_dir.symlink_to(DB.parent)

                old_json, new_json = Path(tmp) / "old.json", Path(tmp) / "new.json"
                run_dumper(wt / "app" / "main.py", old_json)
                run_dumper(REPO / "app" / "main.py", new_json)
                old = json.loads(old_json.read_text())
                new = json.loads(new_json.read_text())
            finally:
                subprocess.run(["git", "-C", str(REPO), "worktree", "remove", "--force", str(wt)],
                               capture_output=True, text=True, check=False)
                subprocess.run(["git", "-C", str(REPO), "worktree", "prune"], check=False)

        # (A) Vista por defecto, nivel superior (determinista)
        ui_old = [e for e in old["apptest"] if not e["in_expander"]]
        ui_new = [e for e in new["apptest"] if not e["in_expander"]]
        dui = diffs(ui_old, ui_new, "UI")
        # (B) Data exacta con reloj fijo (alineación, calidad, rendimiento, cointegración)
        dmodel = diffs(old["model"], new["model"], "MODEL")
        # (C) Dentro de expanders: NEW no debe traer bloques ausentes en OLD
        exp_only_new = signatures([e for e in new["apptest"] if e["in_expander"]]) - \
            signatures([e for e in old["apptest"] if e["in_expander"]])

        print("\n=== Regresión pestaña Índices (esta corrida) ===")
        print(f"AppTest nivel superior comparados: {len(ui_old)} (OLD) vs {len(ui_new)} (NEW); diferencias: {len(dui)}")
        print(f"Model (reloj fijo) activos: {len(old['model']['rows'])} filas, "
              f"{len(old['model']['quality']['rows'])} calidad, {len(old['model']['cointegration'])} pares; diferencias: {len(dmodel)}")
        print(f"AppTest dentro-de-expanders: {len([e for e in new['apptest'] if e['in_expander']])} (NEW) — "
              f"bloques solo en NEW: {len(exp_only_new)}")
        for label, dd in [("UI", dui), ("MODEL", dmodel)]:
            for x in dd[:40]:
                print(f"   {label} {x}")
        for x in sorted(exp_only_new)[:20]:
            print(f"   EXP-NEW {x}")

        self.assertEqual(dui, [], f"{len(dui)} diferencias en la vista por defecto")
        self.assertEqual(dmodel, [], f"{len(dmodel)} diferencias en los datos (reloj fijo)")
        self.assertEqual(exp_only_new, set(), "NEW introdujo contenido de expander ausente en OLD")


if __name__ == "__main__":
    unittest.main(verbosity=2)
