"""Respaldo coherente de SQLite, ZIP verificable y retención por períodos."""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import contextmanager, closing
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BACKUP_DIR = ROOT / "backups"
NAME = re.compile(r"^finance_(\d{8}T\d{6}\.\d{6}Z)\.zip$")


def utc_now():
    return datetime.now(timezone.utc)


def connect_readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=30)


def digest(path):
    sha = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def database_summary(path):
    with closing(connect_readonly(path)) as conn:
        integrity = [row[0] for row in conn.execute("PRAGMA integrity_check")]
        if integrity != ["ok"]:
            raise ValueError("La base no pasó la verificación de integridad: " + "; ".join(integrity))
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )]
        if "candles" not in tables:
            raise ValueError("El archivo no es una base de dashboard-finance: falta la tabla de velas.")
        counts = {name: conn.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]
                  for name in tables}
        latest = conn.execute("SELECT MAX(timestamp) FROM candles").fetchone()[0]
    return {"integrity": "ok", "counts": counts, "candles": counts["candles"], "last_candle": latest}


@contextmanager
def exclusive_file(path):
    """Evita dos respaldos/restauraciones simultáneas; no sustituye cerrar la app."""
    path = Path(path)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(f"Hay otra operación en curso ({path}). Si se interrumpió, revisá ese archivo.") from exc
    try:
        with os.fdopen(fd, "w") as file:
            file.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)


def snapshot_database(source, destination):
    source = Path(source).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"No existe la base: {source}")
    src = connect_readonly(source)
    dst = sqlite3.connect(destination)
    try:
        src.backup(dst, pages=1024, sleep=0.05)
        dst.execute("PRAGMA journal_mode=DELETE")
    finally:
        dst.close()
        src.close()


def prune_backups(folder, keep, period):
    """Conserva la copia más nueva de cada día/semana/mes; nunca toca archivos ajenos."""
    buckets = {}
    files = []
    for file in Path(folder).glob("finance_*.zip"):
        match = NAME.match(file.name)
        if not match:
            continue
        date = datetime.strptime(match.group(1), "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=timezone.utc)
        key = date.date() if period == "daily" else date.isocalendar()[:2] if period == "weekly" else (date.year, date.month)
        files.append(file)
        if key not in buckets or file.name > buckets[key].name:
            buckets[key] = file
    retained = set(sorted(buckets.values(), key=lambda p: p.name, reverse=True)[:keep])
    for file in files:
        if file not in retained:
            file.unlink()


def create_backup(db_path, backup_dir=DEFAULT_BACKUP_DIR, retention=None, now=None, compression_level=6):
    retention = retention or {"daily": 7, "weekly": 4, "monthly": 3}
    if any(not isinstance(retention.get(k), int) or retention[k] < 1 for k in ("daily", "weekly", "monthly")):
        raise ValueError("La cantidad de copias debe ser un entero positivo en cada período.")
    folder = Path(backup_dir).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    now = now or utc_now()
    if now.tzinfo is None:
        raise ValueError("La fecha del respaldo debe incluir zona horaria.")
    now = now.astimezone(timezone.utc)
    name = "finance_" + now.strftime("%Y%m%dT%H%M%S.%fZ") + ".zip"
    with exclusive_file(folder / ".backup.lock"), tempfile.TemporaryDirectory(dir=folder) as tmp:
        raw = Path(tmp) / "finance.db"
        snapshot_database(db_path, raw)
        summary = database_summary(raw)
        manifest = {"format": 1, "created_at": now.isoformat(), "raw_bytes": raw.stat().st_size,
                    "sha256": digest(raw), **summary}
        archive = Path(tmp) / name
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=compression_level) as zip_file:
            zip_file.write(raw, "finance.db")
            zip_file.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        paths = []
        for period in ("daily", "weekly", "monthly"):
            target_dir = folder / period
            target_dir.mkdir(exist_ok=True)
            pending = target_dir / (name + ".tmp")
            shutil.copyfile(archive, pending)
            final = target_dir / name
            pending.replace(final)
            paths.append(str(final))
        # Solo después de terminar y comprobar la copia se aplica la retención.
        for period in ("daily", "weekly", "monthly"):
            prune_backups(folder / period, retention[period], period)
        return {"archive": paths[0], "copies": paths, "compressed_bytes": Path(paths[0]).stat().st_size,
                **manifest}


def ensure_daily_backup(db_path, backup_dir=DEFAULT_BACKUP_DIR, **kwargs):
    """Respaldo automático antes de actualizar, si aún no hay copia de ese día."""
    today = utc_now().strftime("%Y%m%d")
    if any(NAME.match(p.name) for p in (Path(backup_dir) / "daily").glob(f"finance_{today}T*.zip")):
        return None
    return create_backup(db_path, backup_dir, **kwargs)


def unpack_and_verify(archive, directory):
    raw = Path(directory) / "finance.db"
    with zipfile.ZipFile(archive) as zip_file:
        if set(zip_file.namelist()) != {"finance.db", "manifest.json"}:
            raise ValueError("El respaldo no contiene la base y su comprobante esperados.")
        manifest = json.loads(zip_file.read("manifest.json"))
        if manifest.get("format") != 1:
            raise ValueError("Formato de respaldo no reconocido.")
        if zip_file.getinfo("finance.db").file_size != manifest["raw_bytes"]:
            raise ValueError("El tamaño de la base no coincide con el comprobante.")
        with zip_file.open("finance.db") as source, raw.open("wb") as output:
            shutil.copyfileobj(source, output)
    if digest(raw) != manifest["sha256"]:
        raise ValueError("La copia está dañada: su comprobación no coincide.")
    summary = database_summary(raw)
    if summary["counts"] != manifest["counts"] or summary["last_candle"] != manifest["last_candle"]:
        raise ValueError("La cantidad de registros o el último dato no coinciden con el respaldo.")
    return raw, manifest, summary


def restore_backup(archive, destination, replace=False, safety_dir=None):
    """Verifica primero; por defecto restaura en una base nueva, nunca sobre la real."""
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not replace:
        raise FileExistsError("El destino ya existe. Elegí una base de prueba nueva o indicá --reemplazar.")
    with exclusive_file(str(destination) + ".restore-lock"), tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
        raw, manifest, summary = unpack_and_verify(archive, tmp)
        if any(Path(str(destination) + suffix).exists() for suffix in ("-wal", "-shm")):
            # No borrar journals a mano: SQLite confirma y retira los temporales.
            try:
                with closing(sqlite3.connect(destination, timeout=1)) as conn:
                    checkpoint = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                    if checkpoint and checkpoint[0]:
                        raise RuntimeError("Hay una lectura/escritura en curso.")
                    if conn.execute("PRAGMA journal_mode=DELETE").fetchone()[0] != "delete":
                        raise RuntimeError("No se pudo cerrar el modo de escritura temporal.")
            except (sqlite3.Error, RuntimeError) as exc:
                raise RuntimeError("La base está en uso. Cerrá la app y los procesos antes de restaurar; no borres -wal/-shm a mano.") from exc
        safety = None
        if destination.exists():
            safety = create_backup(destination, safety_dir or DEFAULT_BACKUP_DIR / "before_restore")
        raw.replace(destination)
        return {"destination": str(destination), "created_at": manifest["created_at"],
                "safety_backup": safety["archive"] if safety else None, **summary}
