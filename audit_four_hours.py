#!/usr/bin/env python3
"""Solo lectura: auditoría de los minutos reales de apertura, incluidos todos los activos."""
import argparse
import sqlite3
from collections import Counter
from pathlib import Path
import pandas as pd
import yaml
from src.data.backup import ROOT
from src.data.db_manager import DEFAULT_DB_PATH


def hourly_audit(db_path):
    assets = yaml.safe_load((ROOT / "config/assets.yaml").read_text(encoding="utf-8"))
    conn = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    rows = []
    try:
        for section, config in assets.items():
            for symbol in config["activos"]:
                records = conn.execute("SELECT timestamp,source FROM candles WHERE symbol=? AND timeframe='1h' ORDER BY timestamp", (symbol,)).fetchall()
                times = pd.to_datetime([r[0] for r in records], utc=True, format="mixed")
                minutes = dict(sorted(Counter(times.minute).items()))
                # Dato comprobable: qué aperturas de una hora nominal cruzan
                # un límite UTC. Los cierres parciales se documentan por separado.
                crossing = int(((times + pd.Timedelta(hours=1)) > (times.floor("4h") + pd.Timedelta(hours=4))).sum())
                exceptions = [str(ts) for ts in times[times.minute != 0]]
                rows.append({"section": section, "symbol": symbol, "hourly_bars": len(records), "minutes": minutes,
                    "crosses_utc_4h_boundary": crossing, "offset_dates": sorted(set(t[:10] for t in exceptions)),
                    "no_hourly_source": config["fuente"] == "fred"})
    finally:
        conn.close()
    return rows


def main():
    parser = argparse.ArgumentParser(description="Verificar datos reales de apertura 1h sin descargar ni modificar.")
    parser.add_argument("--db", default=DEFAULT_DB_PATH)
    args = parser.parse_args()
    for r in hourly_audit(args.db):
        print(f"{r['section']} · {r['symbol']} · 1h={r['hourly_bars']} · minutos={r['minutes']} · horas que cruzan bloque UTC 4h={r['crosses_utc_4h_boundary']} · días excepcionales={r['offset_dates']}")


if __name__ == "__main__":
    main()
