"""Copia congelada de pruebas: resolución de rutas y reglas de uso.

La regresión rápida de las pestañas corre contra una base chica que no se
actualiza nunca, con un reloj congelado. Esta pieza resuelve la copia y su
fecha, y marca los tres casos que el diseño aprobado exige:

1. ``FINANCE_TEST_FAST_DB`` sin definir: la regresión se saltea; nunca usa
   la base grande por accidente.
2. ``FINANCE_TEST_FAST_DB`` apuntando a ``data/finance.db``: se rechaza.
3. Copia sin la marca de validación de paridad (``fixture.json`` con
   ``validado``): se rechaza; hay que regenerarla o correr la paridad.
"""
import json
import os
from pathlib import Path

from src.data.db_manager import DEFAULT_DB_PATH


class FrozenDBError(Exception):
    """La variable de la copia congelada está definida pero no es usable."""


def frozen_state():
    """Devuelve (ruta_absoluta, asof) o (None, None) si no está pedida.

    Lanza FrozenDBError si la variable apunta a la base real, a un archivo
    que no existe, o a una copia sin la marca de validación de paridad.
    """
    fast = os.environ.get("FINANCE_TEST_FAST_DB")
    if not fast:
        return None, None
    ruta = Path(fast).expanduser().resolve()
    real = Path(DEFAULT_DB_PATH).resolve()
    if ruta == real:
        raise FrozenDBError(f"FINANCE_TEST_FAST_DB no puede apuntar a la base real: {ruta}")
    if ruta.parent == real.parent:
        raise FrozenDBError(f"La copia congelada no debe vivir en la carpeta data/: {ruta.parent}")
    if not ruta.exists():
        raise FrozenDBError(f"La copia congelada no existe: {ruta} (generala con make_fast_fixture.py)")
    detalle = ruta.parent / "fixture.json"
    if not detalle.exists():
        raise FrozenDBError(f"Falta fixture.json junto a la copia: {detalle}")
    informacion = json.loads(detalle.read_text())
    if not informacion.get("validado") or informacion["validado"].get("differences") != 0:
        raise FrozenDBError(
            f"La copia no tiene la marca de paridad ({detalle}); corré test_fast_fixture antes de usarla")
    asof = os.environ.get("FINANCE_TEST_ASOF") or informacion.get("asof")
    if not asof:
        raise FrozenDBError(f"fixture.json no guarda asof y tampoco hay FINANCE_TEST_ASOF")
    return ruta, asof
