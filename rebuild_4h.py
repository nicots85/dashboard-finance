#!/usr/bin/env python3
"""Auditar/reconstruir 4h sin borrar legacy; primero prepara, luego aplica con respaldo SQLite."""
import argparse
from src.data.backup import ROOT, create_backup
from src.data.db_manager import DatabaseManager, DEFAULT_DB_PATH
from src.data.four_hour import configuration, policy, rebuild_one


def main():
    parser = argparse.ArgumentParser(description="Reconstrucción 4h desde 1h con conservación de las series antiguas.")
    parser.add_argument("--db", default=DEFAULT_DB_PATH)
    parser.add_argument("--apply", action="store_true", help="Aplicar después de guardar un respaldo")
    parser.add_argument("--symbol", action="append", help="Limitar a un activo; se puede repetir")
    args = parser.parse_args()
    cfg, assets, ops = configuration()
    symbols = args.symbol or list(dict.fromkeys([s for sec in assets.values() for s in sec.get("activos", [])] + cfg["session_symbols"]))
    db = DatabaseManager(args.db)
    if args.apply:
        backup = create_backup(args.db, ROOT / ops["backups"]["directory"])
        print(f"Respaldo previo: {backup['archive']} · {backup['compressed_bytes']/1e6:.2f} MB · {backup['created_at']}")
    failures = []
    for symbol in symbols:
        spec = policy(symbol)
        if not spec:
            continue
        if not args.apply:
            print(f"{symbol}: {spec['method']} · referencia {spec['reference']} · {spec['timezone']}")
            continue
        try:
            result = rebuild_one(db, symbol)
            if result.get("omitted"):
                db.record_data_notice(symbol, "4h", "four_hour_incomplete",
                    f"{result['omitted']} bloques omitidos por horas faltantes, todavía abiertas o incompatibles con el límite; no se fabricaron precios.")
            print(result)
        except Exception as exc:
            failures.append(symbol)
            db.record_data_notice(symbol, "4h", "four_hour_error", str(exc))
            print(f"No se reemplazó {symbol}: {exc}")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
