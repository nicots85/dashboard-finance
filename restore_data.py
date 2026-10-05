#!/usr/bin/env python3
"""Restaurar un ZIP verificado. El destino es obligatorio para evitar tocar la base real por accidente."""
import argparse
import yaml
from src.data.backup import ROOT, NAME
from src.data.backup import restore_backup


def main():
    parser = argparse.ArgumentParser(description="Restaurar y comprobar una copia de dashboard-finance.")
    parser.add_argument("archivo", nargs="?", help="Archivo finance_*.zip")
    parser.add_argument("--ultimo", action="store_true", help="Elegir la última copia diaria")
    parser.add_argument("--destino", required=True, help="Ejemplo de prueba: data/restauracion_prueba.db")
    parser.add_argument("--reemplazar", action="store_true", help="Reemplazar un destino existente, con copia previa")
    args = parser.parse_args()
    if bool(args.archivo) == bool(args.ultimo):
        parser.error("Indicá un archivo o --ultimo (solo uno).")
    try:
        archive = args.archivo
        if args.ultimo:
            config = yaml.safe_load((ROOT / "config/operations.yaml").read_text(encoding="utf-8"))["backups"]
            archives = [p for p in (ROOT / config["directory"] / "daily").glob("finance_*.zip") if NAME.match(p.name)]
            if not archives:
                raise FileNotFoundError("Todavía no hay una copia diaria. Primero ejecutá backup_data.py.")
            archive = max(archives, key=lambda p: p.name)
        result = restore_backup(archive, args.destino, args.reemplazar)
    except Exception as exc:
        print(f"❌ No se restauró la base: {exc}")
        return 1
    print(f"✅ Restauración comprobada: {result['destination']}")
    print(f"   Velas: {result['candles']:,} · Último dato (UTC): {result['last_candle']}")
    print("   Integridad, comprobación del archivo y cantidades: correctas.")
    if result["safety_backup"]:
        print(f"   Copia de la base anterior: {result['safety_backup']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
