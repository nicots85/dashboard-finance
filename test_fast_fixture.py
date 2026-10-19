"""Paridad de la copia congelada: debe renderizar idéntico a la base grande.

Se corre al crear o regenerar la copia, no después de cada cambio. Voltea
las mismas pantallas (las cinco pestañas no argentinas, con sus escenarios)
dos veces con el reloj congelado: una contra la copia congelada y otra
contra la base grande real. Si no hay ninguna diferencia, la copia queda
validada y las regresiones rápidas la aceptan; si algo difiere, marca las
diferencias y no escribe la marca.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.data.backup import ROOT, snapshot_database
from src.data.db_manager import DEFAULT_DB_PATH
from test_regression import compare

ARREGLO = Path(__file__).resolve().parent
COPIA = ARREGLO / "test_fixtures" / "db_fast.db"
INFO = ARREGLO / "test_fixtures" / "fixture.json"
SECCIONES = ("indices", "metales", "cripto", "equity", "smallcaps")


def sha_corto():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ARREGLO,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "fuera-de-repositorio"


class FrozenParity(unittest.TestCase):
    def test_frozen_copy_matches_the_big_base(self):
        if not COPIA.exists():
            raise unittest.SkipTest("No hay copia congelada: generála con make_fast_fixture.py")
        info = json.loads(INFO.read_text())
        asof = os.environ.get("FINANCE_TEST_ASOF") or info.get("asof")
        if not asof:
            raise unittest.SkipTest("fixture.json no guarda asof; regenerá la copia")
        destino = os.environ.get("PARITY_OUTPUT_DIR")
        folder = Path(destino).resolve() if destino else None
        if folder:
            folder.mkdir(parents=True, exist_ok=True)
        else:
            tmp_context = tempfile.TemporaryDirectory()
            folder = Path(tmp_context.name)
        try:
            self._paridad(folder, asof, info)
        finally:
            if not destino:
                tmp_context.cleanup()

    def _paridad(self, folder, asof, info):
        grande = folder / "grande.db"
        snapshot_database(DEFAULT_DB_PATH, str(grande))
        dumps = {}
        for label, db in (("frozen", COPIA), ("big", grande)):
            salida = folder / f"{label}.json"
            env = dict(os.environ, FINANCE_DB_PATH=str(db), FINANCE_REGRESSION_ASOF=asof,
                       OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1")
            print(f"Volcado {label}: {db}", flush=True)
            result = subprocess.run([sys.executable, "-B", str(ROOT / "_five_tabs_dump.py"), str(ROOT), str(salida)],
                                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=14000)
            self.assertEqual(result.returncode, 0, result.stdout[-4000:] + result.stderr[-12000:])
            dumps[label] = json.loads(salida.read_text())
        self.assertEqual(set(dumps["frozen"]), set(dumps["big"]), "escenarios distintos entre bases")
        reports = {}
        for section in SECCIONES:
            a = {k: v for k, v in dumps["frozen"].items() if k.endswith("/" + section)}
            b = {k: v for k, v in dumps["big"].items() if k.endswith("/" + section)}
            reports[section] = compare(a, b)
            print(f"  {section}: {reports[section]['elements_compared']} elementos; "
                  f"{reports[section]['differences']} diferencias", flush=True)
        diferencias = sum(r["differences"] for r in reports.values())
        (folder / "report.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2))
        if diferencias:
            detalle = json.dumps({s: r.get("details") for s, r in reports.items() if r["differences"]},
                                 ensure_ascii=False, indent=2)
            subset_path = folder / "detalles_diferencias.json"
            subset_path.write_text(detalle)
            self.fail(f"El recorte cambia el contenido ({diferencias} filas sumadas; "
                      f"ampliá los márgenes de make_fast_fixture.py). Detalle guardado en {subset_path}")
        info["validado"] = {"differences": 0, "commit": sha_corto(),
                            "validado_en": pd.Timestamp.now(tz="UTC").isoformat()}
        INFO.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n")
        print("Copia validada: la regresión rápida puede usarla.", flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
