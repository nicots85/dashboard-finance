"""Valores de esta corrida, mismos modelos y fórmulas que la interfaz."""
import argparse
import json
from pathlib import Path

import pandas as pd

from app.indices import configs, view_model
from src.data.db_manager import DEFAULT_DB_PATH, DatabaseManager
from src.pilot_math import crypto_kpis


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DEFAULT_DB_PATH)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    signature = DatabaseManager(args.db).data_signature()
    now = pd.Timestamp.now(tz="UTC").isoformat()
    report = {"calculated_at": now, "sections": {}}
    for section in ("cripto", "metales", "equity", "smallcaps"):
        cfg = configs(section) if section != "smallcaps" else None
        if cfg is None:
            continue
        model = view_model(args.db, signature, json.dumps(cfg, sort_keys=True), now, section)
        reading = {"rows": model["rows"], "ratios": model["ratios"], "vwaps": model["session_vwaps"],
                   "alignment": model["alignment"], "last_data": max((row["last_data"] for row in model["rows"]), default=None)}
        if section == "cripto":
            reading["kpis"] = crypto_kpis(model["rows"], model["alignment"], model["ratios"], model["session_vwaps"])
        if section == "metales":
            reading["between"] = model["performance_between"].to_dict("records")
        if section == "equity":
            reading["kpis"] = model["equity"]["kpis"]
        prices = []
        for symbol in ("BTC/USDT", "ETH/USDT", "GC=F"):
            frames = model["frames"].get((symbol, "1m"))
            if frames is not None and len(frames):
                closed = frames[frames.closed]
                last = closed.iloc[-1]
                prices.append({"symbol": symbol, "close": float(last.close), "timestamp": last.timestamp.isoformat(), "source": last.source})
        reading["latest_minute_prices"] = prices
        report["sections"][section] = reading
        print(f"\n{section}: {json.dumps(reading, ensure_ascii=False, default=str)}", flush=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
