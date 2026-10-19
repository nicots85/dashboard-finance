"""Genera la copia congelada de pruebas (test_fixtures/db_fast.db).

Recorta la base real hasta lo que las pantallas piden realmente, con
márgenes generosos; la paridad (test_fast_fixture) es la que confirma que
el recorte alcanza. La fecha congelada sale de la última rueda diaria
registrada: siempre 05:00 UTC del día siguiente.

Uso:
    OPENBLAS_NUM_THREADS=1 .venv/bin/python make_fast_fixture.py
    OPENBLAS_NUM_THREADS=1 .venv/bin/python make_fast_fixture.py --forzar
"""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

from src.data.db_manager import DEFAULT_DB_PATH

DESCAPE = Path(__file__).resolve().parent
DESTINO = DESCAPE / "test_fixtures" / "db_fast.db"
INFORMACION = DESCAPE / "test_fixtures" / "fixture.json"

# Días que se conservan por temporalidad, contando hacia atrás desde la
# fecha congelada. Son márgenes generosos: las ventanas de pantalla piden
# menos. La paridad valida el recorte.
DIAS_POR_TEMPORALIDAD = {"1m": 10, "5m": 40, "15m": 120, "1h": 900}
SESIONES_1D = 1100  # 500 de ventana + 500 de pares + margen


def sha_corto():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=DESCAPE,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "fuera-de-repositorio"


def formato_sqlite(instante):
    """Fecha en el formato textual que usa la base, para comparar por texto."""
    return instante.tz_convert("UTC").strftime("%Y-%m-%d %H:%M:%S+0000")


def asof_congelada(conn):
    ultima = conn.execute("SELECT MAX(timestamp) FROM candles WHERE timeframe='1D'").fetchone()[0]
    if not ultima:
        raise SystemExit("La base no tiene velas diarias")
    dia = pd.Timestamp(ultima, tz="UTC")
    base = (dia + pd.Timedelta(days=1)).floor("D") + pd.Timedelta(hours=5)
    return base.isoformat().replace("+00:00", "Z")


def recortar(db, asof):
    """Borra velas fuera de las ventanas y deja la cola de cálculos."""
    zona = pd.Timestamp(asof).tz_convert("UTC")
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=OFF")
    corte = {}
    for tf, dias in DIAS_POR_TEMPORALIDAD.items():
        limite = formato_sqlite(zona - pd.Timedelta(days=dias))
        eliminadas = conn.execute("DELETE FROM candles WHERE timeframe=? AND timestamp<?", (tf, limite)).rowcount
        corte[tf] = dias
        print(f"  {tf:5s}: −{eliminadas} velas (conserva {dias} días)", flush=True)
    # Diaria: cola por símbolo (no por fecha global; la 1D más vieja arranca en 1927).
    conn.execute("CREATE TEMP TABLE cola (symbol TEXT UNIQUE, corte TEXT)")
    for (simbolo,) in conn.execute("SELECT DISTINCT symbol FROM candles WHERE timeframe='1D'").fetchall():
        primera = conn.execute(
            "SELECT timestamp FROM candles WHERE symbol=? AND timeframe='1D' ORDER BY timestamp DESC LIMIT 1 OFFSET ?",
            (simbolo, SESIONES_1D - 1)).fetchone()
        if primera:
            conn.execute("INSERT OR IGNORE INTO cola VALUES (?, ?)", (simbolo, primera[0]))
    eliminadas = conn.execute(
        "DELETE FROM candles WHERE timeframe='1D' AND timestamp<(SELECT corte FROM cola WHERE cola.symbol=candles.symbol)").rowcount
    print(f"  1D   : −{eliminadas} filas (conserva {SESIONES_1D} ruedas por símbolo)", flush=True)
    conn.execute("DROP TABLE cola")
    conn.execute("DELETE FROM data_notices WHERE last_seen<?", (formato_sqlite(zona - pd.Timedelta(days=300)),))
    # Fotos: quedan las tres últimas (si no hay ninguna, la condición no borra nada).
    conn.execute(
        "DELETE FROM snapshot_photos WHERE created_at < COALESCE("
        "(SELECT MIN(created_at) FROM (SELECT created_at FROM snapshot_photos ORDER BY created_at DESC, id DESC LIMIT 3)), "
        "(SELECT MAX(created_at) FROM snapshot_photos))")
    conn.commit()
    try:
        conn.execute("VACUUM")
    finally:
        conn.close()
    return corte


def recuento(db):
    conn = sqlite3.connect(db)
    tablas = {}
    for (tabla,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        tablas[tabla] = conn.execute(f"SELECT COUNT(*) FROM '{tabla}'").fetchone()[0]
    conn.close()
    return tablas


def resumen(db):
    total = sum(recuento(db).values())
    return total


def main():
    forzar = "--forzar" in sys.argv
    if (INFORMACION.exists() or DESTINO.exists()) and not forzar:
        raise SystemExit("Ya existe la copia congelada; pasá --forzar para reemplazarla")
    real = Path(DEFAULT_DB_PATH).resolve()
    if DESTINO.resolve() == real:
        raise SystemExit("El destino no puede ser la base real")
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    print(f"Copiando {real} → {DESTINO} …", flush=True)
    with tempfile.NamedTemporaryFile(suffix=".db", dir=DESTINO.parent, delete=False) as provisional:
        parcial = Path(provisional.name)
    try:
        shutil.copyfile(real, parcial)
        conn = sqlite3.connect(parcial)
        try:
            asof = asof_congelada(conn)
        finally:
            conn.close()
        print(f"Fecha congelada: {asof}")
        print(f"Recortando {parcial} …", flush=True)
        corte = recortar(parcial, asof)
        os.replace(parcial, DESTINO)
    except Exception:
        if parcial.exists():
            parcial.unlink(missing_ok=True)
        raise
    digito = hashlib.sha256(DESTINO.read_bytes()).hexdigest()
    tablas = recuento(DESTINO)
    marca_validada = None
    if forzar and INFORMACION.exists():
        try:
            marca_validada = json.loads(INFORMACION.read_text()).get("validado")
        except Exception:
            marca_validada = None
    documento = {"asof": asof, "generado_en": pd.Timestamp.now(tz="UTC").isoformat(),
                 "commit": sha_corto(), "origen": str(real), "peso_bytes": DESTINO.stat().st_size,
                 "sha256": digito, "recorte_dias": corte,
                 "sesiones_1d_por_simbolo": SESIONES_1D,
                 "validado": marca_validada, "filas": tablas,
                 "filas_totales": sum(tablas.values())}
    INFORMACION.write_text(json.dumps(documento, ensure_ascii=False, indent=2) + "\n")
    print(f"Listo: {DESTINO} ({documento['peso_bytes']/1e6:.1f} MB, {documento['filas_totales']} filas)")
    print("Paridad pendiente: corré  test_fast_fixture  para validar el recorte.")


if __name__ == "__main__":
    main()
