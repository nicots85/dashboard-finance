#!/usr/bin/env python3
"""Copia SQLite diaria/manual comprimida: python backup_data.py."""
import argparse
import yaml
from src.data.backup import ROOT, create_backup
from src.data.db_manager import DEFAULT_DB_PATH


def main():
    parser = argparse.ArgumentParser(description="Guardar copia comprimida y comprobada de la base.")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="Base a respaldar")
    parser.add_argument("--destino", help="Carpeta de copias, fuera de Git")
    args = parser.parse_args()
    config = yaml.safe_load((ROOT / "config/operations.yaml").read_text(encoding="utf-8"))["backups"]
    try:
        result = create_backup(args.db, args.destino or ROOT / config["directory"],
                               retention={k: config[k] for k in ("daily", "weekly", "monthly")},
                               compression_level=config["compression_level"])
    except Exception as exc:
        print(f"❌ No se pudo guardar el respaldo: {exc}")
        return 1
    print(f"✅ Respaldo verificado: {result['archive']}")
    print(f"   Tamaño comprimido: {result['compressed_bytes'] / 1_000_000:.2f} MB")
    print(f"   Velas: {result['candles']:,} · Último dato (UTC): {result['last_candle']}")
    print("   Retención por períodos: 7 días, 4 semanas, 3 meses (según configuración).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
