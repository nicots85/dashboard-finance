"""C3: fotos versionadas de lo que decía el tablero. Genérico, para las seis secciones."""
import hashlib
import io
import json
import platform
import sqlite3
import subprocess
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.data.backup import ROOT
from src.data.db_manager import DEFAULT_DB_PATH
from src.data.four_hour import series_descriptor, policy
from src.indices_math import alignment, prepare_bars, session_vwap

SCHEMA_VERSION = 5
ALL_TF = ["1m", "5m", "15m", "1h", "4h", "1D"]
SECTIONS = ["indices", "metales", "equity", "smallcaps", "cripto", "argentina"]


def machine_name():
    return platform.node() or "máquina desconocida"


def app_version():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "sin-version"


def config_hash():
    h = hashlib.sha256()
    for name in ["calc.yaml", "operations.yaml", "assets.yaml", "pairs.yaml", "indices_pilot.yaml"]:
        path = ROOT / "config" / name
        if path.exists():
            h.update(path.read_bytes())
    return h.hexdigest()[:12]


def ensure_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS snapshot_photos (
        id TEXT PRIMARY KEY, created_at TEXT NOT NULL, machine TEXT NOT NULL,
        trigger TEXT NOT NULL, status TEXT NOT NULL, late INTEGER NOT NULL,
        app_version TEXT, params_hash TEXT, tfs_scope TEXT, errors_json TEXT,
        sections_json TEXT NOT NULL)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_photos_created ON snapshot_photos(created_at)")


def latest_calc_rows(conn, table, section_assets):
    out = {}
    for sym in section_assets:
        rows = conn.execute(f"""SELECT r.* FROM {table} r JOIN (SELECT symbol,timeframe,MAX(timestamp) mt
            FROM {table} GROUP BY symbol,timeframe) m ON r.symbol=m.symbol AND r.timeframe=m.timeframe AND r.timestamp=m.mt
            WHERE r.symbol=?""", (sym,)).fetchall()
        out[sym] = rows
    return out


def _instrument_and_session(sym):
    spec = policy(sym)
    if spec and spec["method"] == "future_utc":
        return spec["reference"], "CME_Equity"
    if "/" in sym:
        return sym, "24/7"
    if sym.endswith(".BA"):
        return sym, "America/Argentina/Buenos_Aires"
    if sym == "^GDAXI":
        return sym, "Europe/Berlin"
    if sym == "^N225":
        return sym, "Asia/Tokyo"
    if sym.endswith("=F"):
        return sym, "CME_Equity"
    return sym, "NYSE"


def _distance_for_tf(conn, sym, tf):
    df = pd.read_sql_query("SELECT timestamp,open,high,low,close,volume FROM candles WHERE symbol=? AND timeframe=? ORDER BY timestamp DESC LIMIT 60",
                           conn, params=(sym, tf))
    df = df.iloc[::-1].reset_index(drop=True)
    if df.empty or len(df) < 50:
        return None
    df["timestamp"] = pd.to_datetime(df.timestamp, utc=True, format="mixed")
    instrument, session_name = _instrument_and_session(sym)
    cal = "CME_Equity" if instrument.endswith("=F") else "NYSE"
    if "/" in sym:
        cal = "24/7"
    elif sym.endswith(".BA"):
        cal = "XBUE"
    elif sym == "^GDAXI":
        cal = "XETR"
    elif sym == "^N225":
        cal = "JPX"
    bars = prepare_bars(df, instrument, tf, cal)
    if bars.empty:
        return None
    ema50 = bars.close.ewm(span=50, adjust=False).mean()
    dist_ema = float((bars.close.iloc[-1] - ema50.iloc[-1]) / ema50.iloc[-1] * 100) if len(ema50) else None
    dist_vwap = None
    try:
        vw = session_vwap(bars)
        if vw.vwap.notna().any() and vw.vwap.iloc[-1] > 0:
            dist_vwap = float((vw.close.iloc[-1] - vw.vwap.iloc[-1]) / vw.vwap.iloc[-1] * 100)
    except Exception:
        pass
    return {"ema50_pct": dist_ema, "vwap_pct": dist_vwap, "instrument": instrument, "session": session_name}


def section_snapshot(conn, section, assets_cfg):
    conn.row_factory = sqlite3.Row
    assets = assets_cfg[section].get("activos", [])
    regimes = latest_calc_rows(conn, "calc_regimes", assets)
    zscores = latest_calc_rows(conn, "calc_zscores", assets)
    asset_rows = []
    direction_counts = {"alcista": 0, "bajista": 0, "lateral": 0, "débil": 0, "sin datos": 0}
    for sym in assets:
        per_tf = {}
        directions = {}
        for r in regimes.get(sym, []):
            per_tf[r[1]] = {"direction": r[3], "regime": r[5], "last_data": r[2], "calculated_at": r[9]}
            # Alt 1: agregar strength si está disponible
            if "strength" in r.keys() and r["strength"] is not None:
                per_tf[r[1]]["strength"] = r["strength"]
            directions[r[1]] = r[3]
            if r[1] == "4h":
                descriptor = series_descriptor(sym, conn)
                version = r["series_version"] if "series_version" in r.keys() else None
                if version is None:
                    descriptor = {"method": "legacy", "reference": sym, "label": "4h antigua",
                                  "inputs": json.loads(r["input_versions_json"] or "[]")}
                per_tf[r[1]]["series_4h"] = {**descriptor, "version": version or "4h-antigua"}
                from src.presentation import asset_label
                per_tf[r[1]]["display_name"] = asset_label(sym, "4h") if version else asset_label(sym)
        for tf in ALL_TF:
            if tf in per_tf:
                dist = _distance_for_tf(conn, sym, tf)
                if dist:
                    per_tf[tf]["distance"] = dist
        align = alignment(directions)
        z1d = next((r for r in zscores.get(sym, []) if r[1] == "1D"), None)
        last = max((r[2] for r in regimes.get(sym, [])), default=None)
        direction_counts["alcista"] += sum(1 for v in per_tf.values() if str(v["direction"]).startswith("alcista"))
        direction_counts["bajista"] += sum(1 for v in per_tf.values() if str(v["direction"]).startswith("bajista"))
        direction_counts["lateral"] += sum(1 for v in per_tf.values() if v["direction"] == "lateral")
        direction_counts["débil"] += sum(1 for v in per_tf.values() if "débil" in str(v["direction"]))
        asset_rows.append({
            "symbol": sym,
            "timeframes": per_tf,
            "alignment": {"up": align["up"], "down": align["down"], "weak": align["weak"],
                          "available": align["available"], "missing": align["missing"],
                          "missing_timeframes": [tf for tf in ALL_TF if tf not in directions]},
            "z_atr_1d": z1d[3] if z1d else None,
            "z_std_1d": z1d[4] if z1d else None,
            "z_percentile_1d": z1d[6] if z1d else None,
            "last_data": last,
        })
    pairs = []
    for p in yaml.safe_load((ROOT / "config/pairs.yaml").read_text()).get(section, []):
        key = f"{p['y']}/{p['x']}"
        rows = conn.execute("""SELECT c.* FROM calc_cointegration c JOIN (SELECT pair,timeframe,MAX(timestamp) mt
            FROM calc_cointegration GROUP BY pair,timeframe) m ON c.pair=m.pair AND c.timeframe=m.timeframe AND c.timestamp=m.mt
            WHERE c.pair=?""", (key,)).fetchall()
        if rows:
            pairs.append({"pair": key, "name": p.get("nombre"), "betas": {r[1]: r[4] for r in rows},
                          "states": {r[1]: ("cointegrado" if r[7] else "no cointegrado") for r in rows},
                          "p_values": {r[1]: r[3] for r in rows}, "last_data": max(r[2] for r in rows)})
    macro = []
    if section in ("indices", "metales", "equity", "smallcaps", "cripto", "argentina"):
        rows = conn.execute("""SELECT m.* FROM calc_macro m JOIN (SELECT series_id,MAX(timestamp) mt FROM calc_macro GROUP BY series_id) x
            ON m.series_id=x.series_id AND m.timestamp=x.mt""").fetchall()
        macro = [{"series": r[0], "value": r[2], "change_1m": r[3], "percentile": r[5], "last_data": r[1]} for r in rows]
    return {"assets": asset_rows, "pairs": pairs, "macro": macro, "direction_counts": direction_counts}


def indices_kpis(conn):
    assets = yaml.safe_load((ROOT / "config/assets.yaml").read_text())["indices"]["activos"]
    perf = {}
    for sym in assets:
        df = pd.read_sql_query("SELECT timestamp,close FROM candles WHERE symbol=? AND timeframe='1D' ORDER BY timestamp", conn, params=(sym,))
        df = df.dropna().tail(21)
        if len(df) == 21 and (df.close > 0).all():
            perf[sym] = (df.close.iloc[-1] / df.close.iloc[0] - 1) * 100
    top = max(perf, key=perf.get) if perf else None
    zrows = conn.execute("""SELECT z.symbol,z.z_atr FROM calc_zscores z JOIN (SELECT symbol,timeframe,MAX(timestamp) mt FROM calc_zscores GROUP BY symbol,timeframe) m
        ON z.symbol=m.symbol AND z.timeframe=m.timeframe AND z.timestamp=m.mt WHERE z.timeframe='1D' AND z.symbol IN (%s)""" % ",".join("?"*len(assets)), assets).fetchall()
    stretched = max(zrows, key=lambda r: abs(r[1] or 0))[0] if zrows else None
    aligned = {}
    for sym in assets:
        n = conn.execute("SELECT COUNT(*) FROM calc_regimes WHERE symbol=? AND timeframe IN ('1m','5m','15m','1h','4h','1D')", (sym,)).fetchone()[0]
        up = conn.execute("""SELECT COUNT(*) FROM calc_regimes r JOIN (SELECT symbol,timeframe,MAX(timestamp) mt FROM calc_regimes GROUP BY symbol,timeframe) m
            ON r.symbol=m.symbol AND r.timeframe=m.timeframe AND r.timestamp=m.mt WHERE r.symbol=? AND r.direction LIKE 'alcista%'""", (sym,)).fetchone()[0]
        aligned[sym] = up
    best_aligned = max(aligned, key=aligned.get) if aligned else None
    return {"top_relative_20d": top, "most_stretched_1d": stretched, "most_aligned_up_count": aligned.get(best_aligned), "most_aligned": best_aligned}


def argentina_ccl(conn):
    cfg = yaml.safe_load((ROOT / "config/assets.yaml").read_text())["argentina"]
    equiv = cfg["equivalencias"]
    values = []
    for p in cfg["pares"]:
        ratio = equiv.get(p["adr"])
        if not ratio:
            continue
        local = pd.read_sql_query("SELECT timestamp,close FROM candles WHERE symbol=? AND timeframe='1D' ORDER BY timestamp", conn, params=(p["local"],))
        adr = pd.read_sql_query("SELECT timestamp,close FROM candles WHERE symbol=? AND timeframe='1D' ORDER BY timestamp", conn, params=(p["adr"],))
        if local.empty or adr.empty:
            continue
        a = local.assign(d=pd.to_datetime(local.timestamp, utc=True).dt.date).set_index("d").close
        b = adr.assign(d=pd.to_datetime(adr.timestamp, utc=True).dt.date).set_index("d").close
        idx = a.index.intersection(b.index)
        if len(idx):
            values.append(float(a.loc[idx].iloc[-1] * ratio / b.loc[idx].iloc[-1]))
    return {"median": float(pd.Series(values).median()) if values else None, "companies": len(values)}


def take_snapshot(db_path=DEFAULT_DB_PATH, trigger="manual_full", status="ok", errors=None, tfs_scope=None, late=False):
    assets_cfg = yaml.safe_load((ROOT / "config/assets.yaml").read_text())
    params = yaml.safe_load((ROOT / "config/calc.yaml").read_text())
    conn = sqlite3.connect(db_path)
    try:
        ensure_table(conn)
        sections = {}
        for section in SECTIONS:
            sections[section] = section_snapshot(conn, section, assets_cfg)
        sections["indices"]["kpis"] = indices_kpis(conn)
        sections["argentina"]["ccl"] = argentina_ccl(conn)
        now = datetime.now(timezone.utc)
        photo_id = f"{machine_name()}-{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        conn.execute("""INSERT INTO snapshot_photos VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (
            photo_id, now.isoformat(timespec="seconds"), machine_name(), trigger, status, int(late),
            app_version(), config_hash(), json.dumps(tfs_scope or ALL_TF), json.dumps(errors or [], ensure_ascii=False),
            json.dumps({"schema_version": SCHEMA_VERSION, "four_hour_format": 2, "alignment_format": 1, "direction_definition": "alt3_umbral005", "sections": sections}, ensure_ascii=False, default=str)))
        conn.commit()
        return photo_id
    finally:
        conn.close()


def list_photos(db_path=DEFAULT_DB_PATH, limit=200):
    conn = sqlite3.connect(db_path)
    try:
        ensure_table(conn)
        rows = conn.execute("""SELECT id,created_at,machine,trigger,status,late,app_version,params_hash,tfs_scope,errors_json,sections_json
            FROM snapshot_photos ORDER BY created_at DESC LIMIT ?""", (limit,)).fetchall()
        photos = []
        for r in rows:
            item = dict(zip(["id", "created_at", "machine", "trigger", "status", "late", "app_version", "params_hash", "tfs_scope", "errors"], r[:10]))
            item["four_hour_label"] = "4h versionada" if json.loads(r[10]).get("four_hour_format") == 2 else "4h antigua"
            item["direction_definition_label"] = "definición Alt 1" if json.loads(r[10]).get("direction_definition") == "alt1" else "definición antigua"
            photos.append(item)
        return photos
    finally:
        conn.close()


def get_photo(photo_id, db_path=DEFAULT_DB_PATH):
    conn = sqlite3.connect(db_path)
    try:
        ensure_table(conn)
        row = conn.execute("SELECT * FROM snapshot_photos WHERE id=?", (photo_id,)).fetchone()
        if not row:
            raise KeyError(photo_id)
        cols = ["id", "created_at", "machine", "trigger", "status", "late", "app_version", "params_hash", "tfs_scope", "errors_json", "sections_json"]
        data = dict(zip(cols, row))
        data["errors"] = json.loads(data.pop("errors_json"))
        data["content"] = json.loads(data.pop("sections_json"))
        # Marca derivada al leer; NO reescribe ni completa contenido histórico.
        data["four_hour_label"] = "4h versionada" if data["content"].get("four_hour_format") == 2 else "4h antigua"
        data["direction_definition_label"] = "definición Alt 1" if data["content"].get("direction_definition") == "alt1" else "definición antigua"
        return data
    finally:
        conn.close()


def export_photos(db_path=DEFAULT_DB_PATH, photo_ids=None):
    photos = list_photos(db_path, 100000)
    if photo_ids is not None:
        photos = [p for p in photos if p["id"] in set(photo_ids)]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in photos:
            full = get_photo(p["id"], db_path)
            zf.writestr(f"{p['id']}.json", json.dumps(full, ensure_ascii=False, default=str))
    return buf.getvalue()


def import_photos(data: bytes, db_path=DEFAULT_DB_PATH):
    added, skipped_duplicates, kept_distinct = 0, 0, 0
    conn = sqlite3.connect(db_path)
    try:
        ensure_table(conn)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if not name.endswith(".json"):
                    continue
                photo = json.loads(zf.read(name))
                existing = conn.execute("SELECT sections_json,machine FROM snapshot_photos WHERE id=?", (photo["id"],)).fetchone()
                if existing:
                    if existing[0] == json.dumps(photo["content"], ensure_ascii=False, default=str):
                        skipped_duplicates += 1
                    else:
                        photo["id"] = photo["id"] + "-importado"
                        kept_distinct += 1
                        conn.execute("""INSERT INTO snapshot_photos VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (
                            photo["id"], photo["created_at"], photo["machine"], photo["trigger"], photo["status"], photo["late"],
                            photo["app_version"], photo["params_hash"], photo["tfs_scope"], json.dumps(photo["errors"], ensure_ascii=False),
                            json.dumps(photo["content"], ensure_ascii=False, default=str)))
                        added += 1
                    continue
                conn.execute("""INSERT INTO snapshot_photos VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (
                    photo["id"], photo["created_at"], photo["machine"], photo["trigger"], photo["status"], photo["late"],
                    photo["app_version"], photo["params_hash"], photo["tfs_scope"], json.dumps(photo["errors"], ensure_ascii=False),
                    json.dumps(photo["content"], ensure_ascii=False, default=str)))
                added += 1
        conn.commit()
        return {"added": added, "skipped_duplicates": skipped_duplicates, "kept_distinct": kept_distinct}
    finally:
        conn.close()


def changes_between(a_id, b_id, db_path=DEFAULT_DB_PATH):
    """Solo entre fotos reales, nunca contra datos actuales."""
    a, b = get_photo(a_id, db_path), get_photo(b_id, db_path)
    rows = []
    for section in SECTIONS:
        sa, sb = a["content"]["sections"].get(section, {}), b["content"]["sections"].get(section, {})
        aa = {x["symbol"]: x for x in sa.get("assets", [])}
        bb = {x["symbol"]: x for x in sb.get("assets", [])}
        for sym in sorted(set(aa) & set(bb)):
            da = aa[sym]["timeframes"].get("1D", {}).get("direction")
            db_ = bb[sym]["timeframes"].get("1D", {}).get("direction")
            if da != db_:
                rows.append({"Sección": section, "Activo": sym, "Campo": "Dirección 1D", "Antes": da, "Después": db_})
            za, zb = aa[sym].get("z_atr_1d"), bb[sym].get("z_atr_1d")
            if za is not None and zb is not None and abs(zb - za) > 1.0:
                rows.append({"Sección": section, "Activo": sym, "Campo": "Distancia z 1D", "Antes": round(za, 2), "Después": round(zb, 2)})
        pa = {p["pair"]: p for p in sa.get("pairs", [])}
        pb = {p["pair"]: p for p in sb.get("pairs", [])}
        for pair in sorted(set(pa) & set(pb)):
            if pa[pair]["states"].get("1D") != pb[pair]["states"].get("1D"):
                rows.append({"Sección": section, "Activo": pair, "Campo": "Cointegración 1D", "Antes": pa[pair]["states"].get("1D"), "Después": pb[pair]["states"].get("1D")})
    ca = a["content"]["sections"].get("argentina", {}).get("ccl", {}).get("median")
    cb = b["content"]["sections"].get("argentina", {}).get("ccl", {}).get("median")
    if ca and cb and abs(cb / ca - 1) > 0.01:
        rows.append({"Sección": "argentina", "Activo": "CCL mediano", "Campo": "Mediana", "Antes": round(ca, 1), "Después": round(cb, 1)})
    return rows
