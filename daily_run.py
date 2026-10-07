#!/usr/bin/env python3
"""Respaldo + descarga + cálculos + foto real, con hora de Buenos Aires y recuperación tardía."""
import argparse
import sqlite3
import subprocess
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from src.data.backup import ROOT
from src.data.db_manager import DEFAULT_DB_PATH
from src.data.snapshots import take_snapshot


def latest_due(now, hour=21, minute=15, zone="America/Argentina/Buenos_Aires"):
    local = now.astimezone(ZoneInfo(zone))
    due = datetime.combine(local.date(), time(hour, minute), tzinfo=ZoneInfo(zone))
    if local < due:
        due -= timedelta(days=1)
    return due


def timing(now, activated_at=None, hour=21, minute=15, zone="America/Argentina/Buenos_Aires"):
    due = latest_due(now, hour, minute, zone)
    active = activated_at is None or due.astimezone(timezone.utc) >= activated_at.astimezone(timezone.utc)
    return due, active, now.astimezone(timezone.utc) > due.astimezone(timezone.utc) + timedelta(minutes=30)


def main():
    parser = argparse.ArgumentParser(description="Corrida diaria con foto real; no inventa fotos de horarios perdidos.")
    parser.add_argument("--scheduled", action="store_true", help="Ejecutar solo si venció una hora diaria que aún no se atendió")
    parser.add_argument("--hora", default="21:15")
    parser.add_argument("--zona", default="America/Argentina/Buenos_Aires")
    parser.add_argument("--activated-at", help="Fecha UTC de instalación de la tarea")
    parser.add_argument("--db", default=DEFAULT_DB_PATH)
    parser.add_argument("--dry-run", action="store_true", help="Mostrar horario sin descargar, crear fotos ni activar una tarea")
    args = parser.parse_args()
    hour, minute = map(int, args.hora.split(":"))
    now = datetime.now(timezone.utc)
    activation = datetime.fromisoformat(args.activated_at) if args.activated_at else None
    due, active, late = timing(now, activation, hour, minute, args.zona)
    if args.dry_run:
        print(f"Hora diaria: {args.hora} {args.zona} · última hora vencida {due.isoformat()} · habilitada {active} · tardía {late}")
        return 0
    if args.scheduled and not active:
        return 0
    due_key = due.astimezone(timezone.utc).isoformat()
    if args.scheduled:
        with sqlite3.connect(args.db, timeout=30) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS daily_due_runs (
                due_utc TEXT PRIMARY KEY, started_at TEXT NOT NULL, status TEXT NOT NULL, photo_id TEXT)""")
            conn.execute("BEGIN IMMEDIATE")
            old = conn.execute("SELECT started_at,status,photo_id FROM daily_due_runs WHERE due_utc=?", (due_key,)).fetchone()
            if old and (old[2] or old[1] != "running" or now - datetime.fromisoformat(old[0]) < timedelta(hours=6)):
                return 0
            conn.execute("INSERT OR REPLACE INTO daily_due_runs VALUES (?,?,?,NULL)", (due_key, now.isoformat(), "running"))
    errors = []
    steps = [
        [sys.executable, str(ROOT / "backup_data.py"), "--db", args.db],
        [sys.executable, str(ROOT / "update_data.py"), "--db", args.db],
        [sys.executable, str(ROOT / "run_calc.py"), "--db", args.db],
    ]
    for cmd in steps:
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
        if result.returncode:
            errors.append(f"{Path(cmd[1]).name}: código {result.returncode}")
            if Path(cmd[1]).name == "backup_data.py":
                break  # no descargar si la copia previa falló
    status = "ok" if not errors else "partial"
    try:
        # La marca describe la hora real de la foto, también si la descarga tardó.
        late = datetime.now(timezone.utc) > due.astimezone(timezone.utc) + timedelta(minutes=30)
        photo = take_snapshot(args.db, trigger="daily", status=status, errors=errors, late=late if args.scheduled else False)
        print(f"Foto tomada realmente ahora: {photo} · {status} · tardía {late if args.scheduled else False}")
        if args.scheduled:
            with sqlite3.connect(args.db) as conn:
                conn.execute("UPDATE daily_due_runs SET status=?,photo_id=? WHERE due_utc=?", (status, photo, due_key))
    except Exception as exc:
        print(f"No se pudo guardar la foto diaria: {exc}")
        return 1
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
