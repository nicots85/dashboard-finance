"""Actualización completa real, respaldo automático y auditoría de claves nuevas.

Guarda evidencia antes/después en --output-dir. No confunde velas recibidas o
corregidas con nuevas: cuenta claves (símbolo, temporalidad, timestamp).
"""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import pandas as pd
import yaml
from dotenv import load_dotenv

from src.data.backup import ROOT, ensure_daily_backup, snapshot_database, connect_readonly, unpack_and_verify
from src.data.db_manager import DEFAULT_DB_PATH, DatabaseManager


def inventory(path):
    with closing(connect_readonly(path)) as conn:
        candles = conn.execute("SELECT symbol,timeframe,COUNT(*),MIN(timestamp),MAX(timestamp) FROM candles GROUP BY symbol,timeframe ORDER BY symbol,timeframe").fetchall()
        macro = conn.execute("SELECT series_id,COUNT(*),MAX(timestamp) FROM fred_series GROUP BY series_id ORDER BY series_id").fetchall()
    return {"candles": [dict(zip(["symbol", "tf", "count", "first", "last"], row)) for row in candles],
            "macro": [dict(zip(["series", "count", "last"], row)) for row in macro]}


def changes(before, after):
    with closing(connect_readonly(after)) as conn:
        conn.execute("ATTACH DATABASE ? AS prior", (str(before),))
        added = conn.execute("""SELECT c.symbol,c.timeframe,COUNT(*) FROM main.candles c
            LEFT JOIN prior.candles p ON c.symbol=p.symbol AND c.timeframe=p.timeframe AND c.timestamp=p.timestamp
            WHERE p.timestamp IS NULL GROUP BY c.symbol,c.timeframe""").fetchall()
        removed = conn.execute("""SELECT p.symbol,p.timeframe,COUNT(*) FROM prior.candles p
            LEFT JOIN main.candles c ON c.symbol=p.symbol AND c.timeframe=p.timeframe AND c.timestamp=p.timestamp
            WHERE c.timestamp IS NULL GROUP BY p.symbol,p.timeframe""").fetchall()
        corrected = conn.execute("""SELECT c.symbol,c.timeframe,COUNT(*) FROM main.candles c
            JOIN prior.candles p ON c.symbol=p.symbol AND c.timeframe=p.timeframe AND c.timestamp=p.timestamp
            WHERE c.open IS NOT p.open OR c.high IS NOT p.high OR c.low IS NOT p.low OR c.close IS NOT p.close
            OR c.volume IS NOT p.volume OR c.source IS NOT p.source GROUP BY c.symbol,c.timeframe""").fetchall()
        fred = conn.execute("""SELECT c.series_id,COUNT(*) FROM main.fred_series c LEFT JOIN prior.fred_series p
            ON c.series_id=p.series_id AND c.timestamp=p.timestamp WHERE p.timestamp IS NULL GROUP BY c.series_id""").fetchall()
    def rows(values):
        return [dict(zip(["symbol", "tf", "count"], row)) for row in values]
    return {"added": rows(added), "removed": rows(removed), "corrected": rows(corrected),
            "fred_added": [dict(zip(["series", "count"], row)) for row in fred]}


def clean_log(text):
    for key in ("FRED_API_KEY",):
        value = os.getenv(key)
        if value:
            text = text.replace(value, "<redacted>")
    return re.sub(r"([?&]api_key=)[^&\s]+", r"\1<redacted>", text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DEFAULT_DB_PATH)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    folder = Path(args.output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    before, after = folder / "before.db", folder / "after.db"
    if before.exists() or after.exists():
        raise FileExistsError("Usar un directorio nuevo: no se sobrescribe evidencia de una corrida anterior.")
    ops = yaml.safe_load((ROOT / "config/operations.yaml").read_text())["backups"]
    backup = ensure_daily_backup(args.db, ROOT / ops["directory"],
                                retention={k: ops[k] for k in ("daily", "weekly", "monthly")},
                                compression_level=ops["compression_level"])
    if backup is None:
        archive = max((ROOT / ops["directory"] / "daily").glob("finance_*.zip"), key=lambda p: p.name)
        backup = {"archive": str(archive), "already_daily": True}
    with tempfile.TemporaryDirectory(dir=folder) as verification:
        _, manifest, summary = unpack_and_verify(backup["archive"], verification)
        backup.update(sha256=manifest["sha256"], integrity=summary["integrity"])
    snapshot_database(args.db, before)
    report = {"started_at": pd.Timestamp.now(tz="UTC").isoformat(), "backup": backup, "before": inventory(before), "commands": []}
    (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Respaldo previo comprobado: " + backup["archive"], flush=True)
    for script in ("update_data.py", "update_indices_references.py", "run_calc.py"):
        cmd = [sys.executable, "-B", str(ROOT / script), "--db", args.db]
        print("Ejecutando " + script, flush=True)
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=21600)
        (folder / (script + ".log")).write_text(clean_log(result.stdout + result.stderr), encoding="utf-8")
        report["commands"].append({"script": script, "exit": result.returncode})
        (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{script}: código {result.returncode}", flush=True)
    snapshot_database(args.db, after)
    report.update(after=inventory(after), changes=changes(before, after),
                  notices=DatabaseManager(args.db).get_data_notices(), completed_at=pd.Timestamp.now(tz="UTC").isoformat())
    assets = yaml.safe_load((ROOT / "config/assets.yaml").read_text())
    report["sections"] = {}
    for section, spec in assets.items():
        symbols = set(spec.get("activos", []))
        records = [r for r in report["after"]["candles"] if r["symbol"] in symbols]
        added = sum(r["count"] for r in report["changes"]["added"] if r["symbol"] in symbols)
        dates = [r["last"] for r in records if r["tf"] == "1D"]
        report["sections"][section] = {"added": added, "earliest_daily": min(dates) if dates else None,
                                      "latest_daily": max(dates) if dates else None, "series": records}
        print(f"{section}: {added} velas nuevas · diario {min(dates) if dates else 'FRED'} → {max(dates) if dates else 'FRED'}", flush=True)
    (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Total de claves de velas agregadas: " + str(sum(r["count"] for r in report["changes"]["added"])), flush=True)
    print("Total de claves retiradas por reconstrucción: " + str(sum(r["count"] for r in report["changes"]["removed"])), flush=True)
    print("Corrida completada; revisar report.json y logs para errores, límites y huecos.", flush=True)
    return int(any(r["exit"] for r in report["commands"]))


if __name__ == "__main__":
    raise SystemExit(main())
