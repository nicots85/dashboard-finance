"""Trazabilidad de precios y cálculos. No cambia las fórmulas de los indicadores."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pandas as pd

CALC_TABLES = {"calc_regimes": "symbol", "calc_zscores": "symbol", "calc_cointegration": "pair", "calc_macro": "series_id"}
INTERVALS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400}


def clock():
    return datetime.now(timezone.utc)


def stamp(date=None):
    return (date or clock()).astimezone(timezone.utc).isoformat(timespec="microseconds")


def parameters_hash(parameters):
    return hashlib.sha256(json.dumps(parameters, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def candle_end(timestamp, symbol, timeframe, source):
    """Fin de vela según su rueda local; contempla DST y últimos bloques parciales."""
    ts = pd.to_datetime(timestamp, utc=True).to_pydatetime()
    if timeframe == "4h" and str(source).startswith("via "):
        # El símbolo base es un índice, pero el precio y horario son del futuro.
        return candle_end(timestamp, str(source)[4:], timeframe, "yahoo")
    if timeframe == "4h" and source == "session_4h_us":
        from src.indices_math import schedule
        local_date = ts.astimezone(ZoneInfo("America/New_York")).date()
        sch = schedule("NYSE", str(local_date), str(local_date))
        if len(sch):
            closing = sch.market_close.iloc[0].to_pydatetime()
            return min(ts + timedelta(hours=4), closing)
    crypto = "/" in symbol or source in {"binance", "bybit", "okx", "hyperliquid"}
    if crypto:
        if timeframe == "1D":
            return ts.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return ts + timedelta(seconds=INTERVALS[timeframe])
    zone, hour, minute = "America/New_York", 16, 0
    if symbol.endswith(".BA"):
        zone, hour = "America/Argentina/Buenos_Aires", 17
    elif symbol == "^GDAXI":
        zone, hour, minute = "Europe/Berlin", 17, 30
    elif symbol == "^N225":
        zone, hour, minute = "Asia/Tokyo", 15, 30
    elif symbol.endswith("=F"):
        hour = 17
    local = ts.astimezone(ZoneInfo(zone))
    day = local.date()
    if symbol.endswith("=F") and local.weekday() == 6:
        day += timedelta(days=1)  # vela diaria dominical de la sesión del lunes
    close = datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo(zone))
    if timeframe == "1D":
        return close.astimezone(timezone.utc)
    end = ts + timedelta(seconds=INTERVALS[timeframe])
    # Mercado regular: la última vela horaria puede durar menos de una hora.
    if not symbol.endswith("=F") and local < close:
        end = min(end, close.astimezone(timezone.utc))
    elif symbol.endswith("=F") and local.weekday() == 4 and local < close:
        end = min(end, close.astimezone(timezone.utc))  # último bloque parcial del viernes
    return end


def recent_gaps(df, symbol, timeframe, source):
    """Conservador: cripto continua, saltos dentro de rueda y cortes largos (>7 días).

    No califica noches/fines de semana como pérdidas. No certifica feriados.
    """
    if df.empty or len(df) < 2:
        return []
    ts = pd.to_datetime(df["timestamp"], utc=True).drop_duplicates().sort_values().tail(1000)
    crypto = "/" in symbol or source in {"binance", "bybit", "okx", "hyperliquid"}
    seconds = 86400 if timeframe == "1D" else INTERVALS[timeframe]
    gaps = []
    previous = None
    for current in ts:
        if previous is not None:
            delta = (current - previous).total_seconds()
            suspicious = crypto and delta > seconds * 1.5
            if not crypto and delta > 7 * 86400:
                suspicious = True
            if not crypto and timeframe in INTERVALS:
                zone = "America/Argentina/Buenos_Aires" if symbol.endswith(".BA") else "Europe/Berlin" if symbol == "^GDAXI" else "Asia/Tokyo" if symbol == "^N225" else "America/New_York"
                a, b = previous.tz_convert(zone), current.tz_convert(zone)
                same_day = a.date() == b.date() and a.dayofweek < 5
                if same_day:
                    a_min, b_min = a.hour * 60 + a.minute, b.hour * 60 + b.minute
                    effective = delta
                    if symbol.endswith("=F") and a_min < 17 * 60 and b_min >= 18 * 60:
                        effective -= 3600  # pausa normal 17:00–18:00 NY
                    if symbol == "^N225" and a_min < 11 * 60 + 30 and b_min >= 12 * 60 + 30:
                        effective -= 3600  # pausa de almuerzo de Tokio
                    if effective > seconds * 1.5:
                        suspicious = True
            if suspicious:
                gaps.append({"kind": "gap", "message": f"Posible hueco de {symbol} en {timeframe}: entre {previous.isoformat()} y {current.isoformat()}. Compará con la fuente; no se inventaron velas."})
        previous = current
    return gaps


def initialize_audit(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS audit_schema (version INTEGER PRIMARY KEY)")
    if conn.execute("SELECT 1 FROM audit_schema WHERE version=1").fetchone():
        return
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS candle_corrections (
          id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
          timestamp TEXT NOT NULL, observed_at TEXT NOT NULL,
          old_values TEXT NOT NULL, new_values TEXT NOT NULL, changed_fields TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_corrections_asset ON candle_corrections(symbol,timeframe,observed_at);
        CREATE TABLE IF NOT EXISTS data_versions (
          kind TEXT NOT NULL, asset TEXT NOT NULL, timeframe TEXT NOT NULL,
          revision INTEGER NOT NULL, latest_timestamp TEXT, changed_at TEXT NOT NULL,
          PRIMARY KEY(kind,asset,timeframe));
        CREATE TABLE IF NOT EXISTS data_notices (
          id INTEGER PRIMARY KEY, kind TEXT NOT NULL, asset TEXT NOT NULL,
          timeframe TEXT NOT NULL, message TEXT NOT NULL, first_seen TEXT NOT NULL,
          last_seen TEXT NOT NULL, resolved_at TEXT,
          UNIQUE(kind,asset,timeframe,message));
    """)
    conn.execute("""INSERT OR IGNORE INTO data_versions
        SELECT 'candles',symbol,timeframe,1,MAX(timestamp),COALESCE(MAX(updated_at),datetime('now'))
        FROM candles GROUP BY symbol,timeframe""")
    conn.execute("""INSERT OR IGNORE INTO data_versions
        SELECT 'fred',series_id,'1D',1,MAX(timestamp),COALESCE(MAX(updated_at),datetime('now'))
        FROM fred_series GROUP BY series_id""")
    columns = {"calculated_at": "TEXT", "last_data_timestamp": "TEXT", "input_versions_json": "TEXT",
               "params_json": "TEXT", "params_hash": "TEXT", "calc_status": "TEXT", "error_message": "TEXT"}
    for table in CALC_TABLES:
        current = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, datatype in columns.items():
            if name not in current:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {datatype}")
        conn.execute(f"""UPDATE {table} SET last_data_timestamp=timestamp,
                     calc_status='untracked' WHERE calculated_at IS NULL""")
    conn.execute("INSERT INTO audit_schema(version) VALUES (1)")


class DataAuditMixin:
    def _input_version(self, conn, kind, asset, timeframe):
        row = conn.execute("SELECT revision,latest_timestamp FROM data_versions WHERE kind=? AND asset=? AND timeframe=?",
                           (kind, asset, timeframe)).fetchone()
        return {"kind": kind, "asset": asset, "timeframe": timeframe,
                "revision": row[0] if row else 0, "latest_timestamp": row[1] if row else None}

    def _touch_version(self, conn, kind, asset, timeframe, observed_at=None):
        if kind == "candles":
            latest = conn.execute("SELECT MAX(timestamp) FROM candles WHERE symbol=? AND timeframe=?", (asset, timeframe)).fetchone()[0]
        else:
            latest = conn.execute("SELECT MAX(timestamp) FROM fred_series WHERE series_id=?", (asset,)).fetchone()[0]
        conn.execute("""INSERT INTO data_versions VALUES (?,?,?,?,?,?)
            ON CONFLICT(kind,asset,timeframe) DO UPDATE SET revision=revision+1,
            latest_timestamp=excluded.latest_timestamp,changed_at=excluded.changed_at""",
            (kind, asset, timeframe, 1, latest, stamp(observed_at)))

    def _record_correction(self, conn, symbol, timeframe, timestamp, old, new, old_updated, observed_at):
        source = old.get("source") or new.get("source") or ""
        # La finalización normal de una vela provisional no es una corrección histórica.
        end = candle_end(timestamp, symbol, timeframe, source)
        legacy = not old_updated or "T" not in str(old_updated)
        if legacy:
            if end > observed_at:
                return
        elif end > pd.to_datetime(old_updated, utc=True).to_pydatetime():
            return
        fields = [key for key in new if new[key] != old[key]]
        if fields:
            if legacy:
                old = {**old, "_fecha_recepcion": "Anterior a C0: hora no verificable; podría ser la primera finalización de una vela provisional."}
            conn.execute("""INSERT INTO candle_corrections
              (symbol,timeframe,timestamp,observed_at,old_values,new_values,changed_fields) VALUES (?,?,?,?,?,?,?)""",
              (symbol, timeframe, timestamp, stamp(observed_at), json.dumps(old), json.dumps(new), json.dumps(fields)))

    def _calculation_metadata(self, conn, table, asset, timeframe, timestamp, input_versions, params, status="ok", error=None):
        if table not in CALC_TABLES:
            raise ValueError("Tabla de cálculo no reconocida")
        key = CALC_TABLES[table]
        tracked = input_versions is not None and params is not None
        data = (stamp(), timestamp, json.dumps(input_versions) if tracked else None,
                json.dumps(params, sort_keys=True, default=str) if tracked else None,
                parameters_hash(params) if tracked else None, status if tracked else "untracked", error)
        tf_sql = " AND timeframe=?" if table != "calc_macro" else ""
        values = data + (asset, timestamp) + ((timeframe,) if tf_sql else ())
        conn.execute(f"""UPDATE {table} SET calculated_at=?,last_data_timestamp=?,input_versions_json=?,
                     params_json=?,params_hash=?,calc_status=?,error_message=?
                     WHERE {key}=? AND timestamp=?{tf_sql}""", values)

    def record_data_notice(self, asset, timeframe, kind, message):
        now = stamp()
        with self._get_connection() as conn:
            conn.execute("""INSERT INTO data_notices(kind,asset,timeframe,message,first_seen,last_seen)
               VALUES (?,?,?,?,?,?) ON CONFLICT(kind,asset,timeframe,message)
               DO UPDATE SET last_seen=excluded.last_seen,resolved_at=NULL""", (kind, asset, timeframe, message, now, now))

    def resolve_data_notices(self, asset, timeframe, kinds):
        with self._get_connection() as conn:
            for kind in kinds:
                conn.execute("UPDATE data_notices SET resolved_at=? WHERE asset=? AND timeframe=? AND kind=? AND resolved_at IS NULL",
                             (stamp(), asset, timeframe, kind))

    def get_data_notices(self, unresolved_only=True):
        where = " WHERE resolved_at IS NULL" if unresolved_only else ""
        with self._get_connection() as conn:
            conn.row_factory = __import__('sqlite3').Row
            return [dict(row) for row in conn.execute("SELECT * FROM data_notices" + where + " ORDER BY last_seen DESC")]

    def data_signature(self):
        with self._get_connection() as conn:
            revision = conn.execute("SELECT COALESCE(SUM(revision),0),MAX(changed_at) FROM data_versions").fetchone()
            calculations = tuple(conn.execute(f"SELECT MAX(calculated_at) FROM {table}").fetchone()[0] for table in CALC_TABLES)
        return str((revision, calculations))

    def get_calculation_health(self, calc_config=None):
        health = []
        config_keys = {"calc_regimes": "regime", "calc_zscores": "zscore", "calc_cointegration": "cointegration", "calc_macro": "macro"}
        with self._get_connection() as conn:
            conn.row_factory = __import__('sqlite3').Row
            for table, key in CALC_TABLES.items():
                group = key + (",timeframe" if table != "calc_macro" else "")
                join = f"r.{key}=m.{key} AND r.timestamp=m.mt" + (" AND r.timeframe=m.timeframe" if table != "calc_macro" else "")
                rows = conn.execute(f"SELECT r.* FROM {table} r JOIN (SELECT {group},MAX(timestamp) mt FROM {table} GROUP BY {group}) m ON {join}")
                for row in rows:
                    if table == "calc_cointegration" and ".BA/" in row[key]:
                        continue  # Resultados antiguos local/ADR conservados, pero ya no usados.
                    status, reason = "ok", ""
                    if row["calc_status"] == "no_calculable":
                        status, reason = "no_calculable", row["error_message"] or "No se pudo calcular con los datos disponibles."
                    elif not row["input_versions_json"]:
                        status, reason = "untracked", "Resultado anterior a C0: no se puede comprobar la versión de precios; recalcular."
                    else:
                        inputs = json.loads(row["input_versions_json"])
                        for source in inputs:
                            current = self._input_version(conn, source["kind"], source["asset"], source["timeframe"])
                            if current["revision"] != source["revision"]:
                                status, reason = "stale", "Los precios o el volumen cambiaron después del cálculo. Recalcular."
                                break
                        if calc_config is not None and row["params_hash"] != parameters_hash(calc_config.get(config_keys[table], {})):
                            status, reason = "stale", "Los parámetros cambiaron después del cálculo. Recalcular."
                    health.append({"table": table, "asset": row[key], "timeframe": row["timeframe"] if table != "calc_macro" else "1D",
                                   "calculated_at": row["calculated_at"] if row["input_versions_json"] else None,
                                   "last_data_timestamp": row["last_data_timestamp"],
                                   "status": status, "reason": reason})
        return health
