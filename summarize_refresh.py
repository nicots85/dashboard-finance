"""Resumen de la actualización real y separación de pausas de avisos de huecos."""
import argparse
from collections import Counter
from contextlib import closing
import json
from pathlib import Path

import pandas as pd
import yaml

from src.data.backup import ROOT, connect_readonly
from src.indices_math import market_minutes_between


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    args = parser.parse_args()
    folder = Path(args.directory)
    report = json.loads((folder / "report.json").read_text())
    config = yaml.safe_load((ROOT / "config/sections.yaml").read_text())
    calendars = {symbol: cal for section in config.values() for symbol, cal in section.get("calendars", {}).items()}
    summary = {"sections": {k: {key: v for key, v in data.items() if key != "series"} for k, data in report["sections"].items()},
               "added": sum(r["count"] for r in report["changes"]["added"]),
               "corrected": sum(r["count"] for r in report["changes"]["corrected"]),
               "removed": sum(r["count"] for r in report["changes"]["removed"]),
               "fred_added": sum(r["count"] for r in report["changes"]["fred_added"]),
               "notice_counts": dict(Counter(r["kind"] for r in report["notices"]))}
    with closing(connect_readonly(folder / "after.db")) as conn:
        summary["macro"] = conn.execute("SELECT series_id,MAX(timestamp) FROM fred_series GROUP BY series_id ORDER BY series_id").fetchall()
    classified = []
    import re
    for notice in report["notices"]:
        if notice["kind"] != "gap":
            continue
        match = re.search(r"entre (\S+) y (\S+)\. Compará", notice["message"])
        if not match:
            continue
        symbol, tf = notice["asset"], notice["timeframe"]
        a, b = pd.to_datetime(match.group(1), utc=True), pd.to_datetime(match.group(2), utc=True)
        # El mensaje se refiere a aperturas; contar mercado después de la
        # duración de la primera vela, no una pausa de cierre/lunch break.
        duration = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240}.get(tf)
        if duration is None:
            continue
        cal = calendars.get(symbol) or ("CME_Equity" if symbol.endswith("=F") else "XBUE" if symbol.endswith(".BA") else "NYSE")
        minutes = market_minutes_between(a + pd.Timedelta(minutes=duration), b, cal)
        classified.append({"symbol": symbol, "tf": tf, "start": a.isoformat(), "end": b.isoformat(),
                           "calendar": cal, "market_minutes_missing": minutes,
                           "classification": "Pausa normal del calendario" if minutes <= 0 else "Posible falta de datos con mercado abierto"})
    summary["gap_classifications"] = dict(Counter(row["classification"] for row in classified))
    summary["gaps_by_asset"] = dict(Counter(row["symbol"] for row in classified if row["market_minutes_missing"] > 0))
    (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (folder / "gap-audit.json").write_text(json.dumps(classified, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
