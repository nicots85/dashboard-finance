#!/usr/bin/env python3
"""C2: descargar solo las referencias nuevas del piloto; no crea fotos de historial."""
import argparse
import json
from pathlib import Path
import yaml
from src.data import DatabaseManager, YahooAdapter
from src.data.db_manager import DEFAULT_DB_PATH
from src.data.backup import ROOT, ensure_daily_backup
from update_data import update_market_asset


def update_references(db_path=DEFAULT_DB_PATH, timeframes=None, progress=None):
    tfs = timeframes or ["1m", "5m", "15m", "1h", "4h", "1D"]
    cfg = yaml.safe_load((ROOT / "config/indices_pilot.yaml").read_text(encoding="utf-8"))
    # IWM ya pertenece a Small caps: no se redescarga desde el piloto.
    symbols = list(cfg["names"])
    ops = yaml.safe_load((ROOT / "config/operations.yaml").read_text(encoding="utf-8"))["backups"]
    if Path(db_path).exists():
        ensure_daily_backup(db_path, ROOT / ops["directory"],
            retention={k: ops[k] for k in ("daily", "weekly", "monthly")}, compression_level=ops["compression_level"])
    db, adapter = DatabaseManager(db_path), YahooAdapter()
    rows = []
    total = len(symbols) * len(tfs)
    for symbol in symbols:
        for tf in tfs:
            result = update_market_asset(adapter, db, symbol, [tf])
            rows.extend(result)
            if progress:
                progress(len(rows) / total, f"Referencia {symbol}, {tf}")
    return rows


def main():
    parser = argparse.ArgumentParser(description="Descargar referencias del piloto de Índices, con protección C0.")
    parser.add_argument("--db", default=DEFAULT_DB_PATH)
    parser.add_argument("--tf", default="1m,5m,15m,1h,4h,1D")
    args = parser.parse_args()
    rows = update_references(args.db, args.tf.split(","))
    for row in rows:
        print(f"{row['symbol']} {row['tf']}: {row['count']} velas · {row['min_date']} → {row['max_date']} · {row['status']}")
    return 1 if any(r["status"].startswith(("ERROR", "PARCIAL")) for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
