#!/usr/bin/env python3
"""Solo lectura: velas coincidentes y bloques completos por par/temporalidad."""
import argparse
import sqlite3
from pathlib import Path
import pandas as pd
import yaml
from src.data.audit import candle_end, clock
from src.data.backup import ROOT
from src.data.db_manager import DEFAULT_DB_PATH


def available_blocks(db_path):
    pairs = yaml.safe_load((ROOT / "config/pairs.yaml").read_text(encoding="utf-8"))
    ops = yaml.safe_load((ROOT / "config/operations.yaml").read_text(encoding="utf-8"))["cointegration_stability"]
    now = clock()
    rows = []
    conn = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        for section, section_pairs in pairs.items():
            if section == "argentina":
                continue  # Local/ADR usa CCL, no cointegración.
            for pair in section_pairs:
                for tf, window in ops["block_bars"].items():
                    df = pd.read_sql_query("""SELECT y.timestamp,y.source sy,x.source sx FROM candles y JOIN candles x
                      ON y.timestamp=x.timestamp AND y.timeframe=x.timeframe AND x.symbol=?
                      WHERE y.symbol=? AND y.timeframe=? AND y.close>0 AND x.close>0 ORDER BY y.timestamp""",
                      conn, params=(pair["x"], pair["y"], tf))
                    # Las series están ordenadas. Retirar las velas finales que aún están abiertas.
                    while len(df) and (candle_end(df.iloc[-1].timestamp, pair["y"], tf, df.iloc[-1].sy) > now or
                                       candle_end(df.iloc[-1].timestamp, pair["x"], tf, df.iloc[-1].sx) > now):
                        df = df.iloc[:-1]
                    n = len(df)
                    enough = n // window >= ops["required_blocks"]
                    enabled = section in ops["eligible_sections"].get(tf, [])
                    status = "Historia insuficiente para evaluar estabilidad" if not enough else "Suficiente" if enabled else "Suficiente, intradía no habilitado por el alcance acordado"
                    rows.append({"section": section, "pair": pair["nombre"], "tf": tf, "bars": n,
                                 "block_bars": window, "blocks": n // window, "enough": enough,
                                 "enabled": enabled, "status": status})
    finally:
        conn.close()
    return rows


def main():
    parser = argparse.ArgumentParser(description="Comprobar historia para cinco bloques sin solape, sin guardar cálculos.")
    parser.add_argument("--db", default=DEFAULT_DB_PATH)
    args = parser.parse_args()
    for row in available_blocks(args.db):
        print(f"{row['pair']} | {row['tf']} | {row['bars']} velas | {row['blocks']} bloques de {row['block_bars']} | {row['status']}")


if __name__ == "__main__":
    main()
