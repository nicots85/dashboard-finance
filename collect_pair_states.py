"""Lectura reproducible de todos los estados de los pilotos sobre una misma BD."""
import argparse
import json
from pathlib import Path

import pandas as pd

from app.indices import configs, cointegration_model
from src.data.db_manager import DEFAULT_DB_PATH, DatabaseManager


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DEFAULT_DB_PATH)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    signature = DatabaseManager(args.db).data_signature()
    now = pd.Timestamp.now(tz="UTC").isoformat()
    readings = []
    for section in ("indices", "metales", "cripto", "equity"):
        configuration = configs(section)
        pilot, pairs = configuration[2], configuration[4][section]
        settings = json.dumps(configuration, sort_keys=True)
        scales = pilot["cointegration_scales"] if section == "cripto" else ["1D"]
        for pair in pairs:
            for tf in scales:
                result = cointegration_model(args.db, signature, settings, now, pair["y"], pair["x"], tf)
                row = {"section": section, "y": pair["y"], "x": pair["x"], "tf": tf,
                       **{key: value for key, value in result.items() if key not in ("spread", "rolling")}}
                readings.append(row)
                print(f"{section} {pair['y']}/{pair['x']} {tf}: {result['state']} · {result.get('bars')} cierres", flush=True)
    Path(args.output).write_text(json.dumps({"calculated_at": now, "pairs": readings}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
