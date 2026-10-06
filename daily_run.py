#!/usr/bin/env python3
"""Corrida diaria: respaldo + actualización + cálculos + foto del tablero."""
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

from src.data.backup import ROOT
from src.data.db_manager import DEFAULT_DB_PATH
from src.data.snapshots import take_snapshot


def main():
    ops = yaml.safe_load((ROOT / "config/operations.yaml").read_text(encoding="utf-8"))["backups"]
    hour, minute = [int(v) for v in ops.get("schedule_time", "21:15").split(":")]
    # Buenos Aires no usa horario de verano: UTC-3 fijo.
    now_utc = datetime.now(timezone.utc)
    now_art = now_utc - timedelta(hours=3)
    scheduled = now_art.replace(hour=hour, minute=minute, second=0, microsecond=0)
    late = now_art > scheduled + timedelta(minutes=30)

    steps = [
        [sys.executable, str(ROOT / "backup_data.py")],
        [sys.executable, str(ROOT / "update_data.py")],
        [sys.executable, str(ROOT / "run_calc.py")],
    ]
    errors, codes = [], []
    for cmd in steps:
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
        codes.append(result.returncode)
        if result.returncode:
            errors.append(f"{Path(cmd[1]).name}: código {result.returncode}")
    status = "ok" if not errors else "partial"
    try:
        pid = take_snapshot(DEFAULT_DB_PATH, trigger="daily", status=status, errors=errors, late=late)
        print(f"Foto diaria: {pid} · estado {status} · tardía {late}")
    except Exception as exc:
        print(f"❌ No se pudo guardar la foto diaria: {exc}")
        return 1
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
