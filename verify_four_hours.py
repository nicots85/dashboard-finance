#!/usr/bin/env python3
"""Comprueba conservación y concordancia de cálculos 4h sin escribir en las bases."""
import argparse
from contextlib import closing
import math
import sqlite3
from pathlib import Path

import pandas as pd
import yaml

from src.data.backup import ROOT
from src.data.db_manager import DEFAULT_DB_PATH
from src.data.four_hour import market_results, policy, prepare_stored, version_for


def read_only(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def candles(conn, symbol, timeframe):
    return conn.execute("""SELECT timestamp,open,high,low,close,volume,source,updated_at
        FROM candles WHERE symbol=? AND timeframe=? ORDER BY timestamp""", (symbol, timeframe)).fetchall()


def matches(actual, expected):
    if expected is None or pd.isna(expected):
        return actual is None
    if isinstance(expected, (float, int)):
        return actual is not None and math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)
    return actual == expected


def verify(before_path, current_path):
    failures = []
    counts = {"series_legacy_conservadas": 0, "series_4h_sin_cambios": 0,
              "activos_con_calculos_concordantes": 0, "fotos_previas_conservadas": 0}
    cfg = yaml.safe_load((ROOT / "config/calc.yaml").read_text(encoding="utf-8"))
    assets = yaml.safe_load((ROOT / "config/assets.yaml").read_text(encoding="utf-8"))
    with closing(read_only(before_path)) as before, closing(read_only(current_path)) as current:
        for name, conn in [("anterior", before), ("activa", current)]:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            print(f"Integridad {name}: {integrity}", flush=True)
            if integrity != "ok":
                failures.append(f"Integridad {name}: {integrity}")
        symbols = [r[0] for r in before.execute("SELECT DISTINCT symbol FROM candles WHERE timeframe='4h'")]
        for symbol in symbols:
            spec = policy(symbol)
            target = "4h_legacy" if spec else "4h"
            if candles(before, symbol, "4h") != candles(current, symbol, target):
                failures.append(f"{symbol}: la serie anterior no coincide con {target}")
            else:
                counts["series_legacy_conservadas" if spec else "series_4h_sin_cambios"] += 1
            if spec:
                row = current.execute("SELECT version FROM four_hour_series WHERE asset=?", (symbol,)).fetchone()
                if not row or row[0] != version_for(spec):
                    failures.append(f"{symbol}: versión activa distinta del método configurado")
        for section, data in assets.items():
            if section == "referencias":
                continue
            print(f"Comprobando cálculos 4h: {section}", flush=True)
            for symbol in data["activos"]:
                frame = pd.read_sql_query("SELECT * FROM candles WHERE symbol=? AND timeframe='4h' ORDER BY timestamp",
                                          current, params=(symbol,))
                frame = prepare_stored(frame, symbol)
                frame = frame[frame.closed]
                reg, z = market_results(frame, cfg)
                initial = len(failures)
                for table, expected, fields in [
                    ("calc_regimes", reg, {"direction": "direction", "regime": "regime", "adx": "adx", "atr_percentile": "atr_percentile"}),
                    ("calc_zscores", z, {"z_atr": "z_atr", "z_std": "z_std", "percentile": "z_percentile"}),
                ]:
                    columns = ",".join(fields)
                    row = current.execute(f"SELECT timestamp,series_version,{columns} FROM {table} WHERE symbol=? AND timeframe='4h' ORDER BY timestamp DESC LIMIT 1", (symbol,)).fetchone()
                    if not row:
                        failures.append(f"{symbol}: falta {table} 4h")
                        continue
                    if pd.to_datetime(row[0], utc=True) != pd.to_datetime(expected["timestamp"], utc=True):
                        failures.append(f"{symbol}: último dato no coincide en {table}")
                    spec = policy(symbol)
                    version = version_for(spec) if spec else "4h-proveedor-sin-cambio"
                    if row[1] != version:
                        failures.append(f"{symbol}: versión del cálculo no coincide en {table}")
                    for actual, field in zip(row[2:], fields.values()):
                        if not matches(actual, expected[field]):
                            failures.append(f"{symbol}: {table}.{field} guardado={actual}, calculado={expected[field]}")
                if len(failures) == initial:
                    counts["activos_con_calculos_concordantes"] += 1
        if before.execute("SELECT 1 FROM sqlite_master WHERE name='snapshot_photos'").fetchone():
            for row in before.execute("SELECT * FROM snapshot_photos"):
                actual = current.execute("SELECT * FROM snapshot_photos WHERE id=?", (row[0],)).fetchone()
                if row != actual:
                    failures.append(f"Foto anterior modificada o ausente: {row[0]}")
                else:
                    counts["fotos_previas_conservadas"] += 1
    return counts, failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, help="Base anterior restaurada del respaldo")
    parser.add_argument("--db", default=DEFAULT_DB_PATH)
    args = parser.parse_args()
    counts, failures = verify(args.before, args.db)
    for key, value in counts.items():
        print(f"{key}: {value}")
    for failure in failures:
        print(f"ERROR: {failure}")
    print("Verificación correcta." if not failures else f"{len(failures)} discrepancias requieren atención.")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
