"""Series 4h aprobadas, conservación legacy y procedencia para cálculo/UI/fotos."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
EMPTY_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


@lru_cache(maxsize=8)
def _config(config_time, assets_time, ops_time):
    return tuple(yaml.safe_load((ROOT / "config" / p).read_text(encoding="utf-8"))
                 for p in ["four_hour.yaml", "assets.yaml", "operations.yaml"])


def configuration():
    return _config(*[(ROOT / "config" / p).stat().st_mtime_ns for p in ["four_hour.yaml", "assets.yaml", "operations.yaml"]])


def policy(symbol):
    cfg, assets, ops = configuration()
    if symbol in cfg["index_futures"]:
        platform = ops["platform_4h"]
        return {"method": "future_utc", "reference": cfg["index_futures"][symbol],
                "timezone": platform.get("timezone") or "UTC",
                "starts": platform.get("candle_open_times") or [f"{h:02}:00" for h in range(0, 24, 4)]}
    session_symbols = set(cfg["session_symbols"])
    for section in cfg["session_sections"]:
        session_symbols.update(assets[section]["activos"])
    if symbol in session_symbols:
        return {"method": "session_us", "reference": symbol, "timezone": cfg["session_timezone"], "starts": cfg["session_starts"]}
    return None


def version_for(spec):
    fingerprint = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]
    return f"4h-v2-{spec['method']}-{fingerprint}"


def initialize_series(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS four_hour_series (
        asset TEXT PRIMARY KEY, version TEXT NOT NULL, method TEXT NOT NULL, reference TEXT NOT NULL,
        timezone TEXT NOT NULL, starts_json TEXT NOT NULL, activated_at TEXT NOT NULL,
        rebuilt_at TEXT NOT NULL, input_versions_json TEXT NOT NULL, quality_json TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS four_hour_archives (
        id TEXT PRIMARY KEY, asset TEXT NOT NULL, table_name TEXT NOT NULL,
        archived_at TEXT NOT NULL, payload_json TEXT NOT NULL)""")
    for table in ["calc_regimes", "calc_zscores"]:
        columns = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if columns and "series_version" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN series_version TEXT")


def series_descriptor(symbol, conn=None):
    spec = policy(symbol)
    row = None
    if conn is not None and conn.execute("SELECT 1 FROM sqlite_master WHERE name='four_hour_series'").fetchone():
        row = conn.execute("SELECT version,method,reference,timezone,starts_json,input_versions_json FROM four_hour_series WHERE asset=?", (symbol,)).fetchone()
    if row:
        return {"version": row[0], "method": row[1], "reference": row[2], "timezone": row[3],
                "starts": json.loads(row[4]), "inputs": json.loads(row[5]), "label":
                f"4h vía {row[2]} ({row[3]})" if row[1] == "future_utc" else "4h de sesión: 09:30–13:30 y 13:30–16:00 NY; segunda vela más corta"}
    return {"version": "4h-antigua" if spec else "4h-proveedor-sin-cambio", "method": "legacy" if spec else "provider",
            "reference": symbol, "inputs": [], "label": "4h antigua" if spec else "4h de la fuente; sin cambio"}


def label(symbol, timeframe=None):
    if timeframe != "4h":
        return None
    cfg, assets, _ = configuration()
    name = next((a["nombres"][symbol] for a in assets.values() if symbol in a.get("nombres", {})), symbol)
    spec = policy(symbol)
    if spec and spec["method"] == "future_utc":
        return f"{name} (vía {spec['reference']})"
    return None


def canonical(df):
    out = df.copy()
    out["timestamp"] = pd.to_datetime(out.timestamp, utc=True, format="mixed")
    return out.sort_values("timestamp").drop_duplicates("timestamp", keep="last").reset_index(drop=True)


def _eligible_hours(df, calendar_name, now):
    from src.indices_math import prepare_bars
    bars = prepare_bars(canonical(df), "NQ=F" if calendar_name == "CME_Equity" else "QQQ", "1h", calendar_name, now)
    return bars[bars.closed].copy()


def build_session(df, now=None):
    """Dos velas desde 1h: cuatro horas y dos horas y media; respeta cierres anticipados."""
    from src.indices_math import schedule
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.to_datetime(now, utc=True)
    if df.empty:
        return pd.DataFrame(columns=EMPTY_COLUMNS), {"omitted": 0}
    bars = _eligible_hours(df, "NYSE", now)
    if bars.empty:
        return pd.DataFrame(columns=EMPTY_COLUMNS), {"omitted": 0}
    bars["local"] = bars.timestamp.dt.tz_convert("America/New_York")
    sch = schedule("NYSE", bars.session.iloc[0], bars.session.iloc[-1])
    rows, omitted = [], 0
    for day, group in bars.groupby("session", sort=True):
        opening, close = sch.loc[pd.Timestamp(day), ["market_open", "market_close"]]
        for start in [opening, opening + pd.Timedelta(hours=4)]:
            end = min(start + pd.Timedelta(hours=4), close)
            if start >= end:
                continue
            expected = pd.date_range(start, end, freq="h", inclusive="left")
            part = group[(group.timestamp >= start) & (group.timestamp < end)]
            # Un resumen horario que cruza el límite no se divide ni se reasigna.
            if set(part.timestamp) != set(expected) or (part.bar_end > end).any() or end > now:
                omitted += 1
                continue
            rows.append({"timestamp": start, "open": part.open.iloc[0], "high": part.high.max(),
                         "low": part.low.min(), "close": part.close.iloc[-1], "volume": part.volume.sum()})
    return pd.DataFrame(rows, columns=EMPTY_COLUMNS), {"omitted": omitted, "method": "session_us"}


def build_future(df, spec, now=None):
    """Bloques de reloj desde horas enteras del futuro. No se fraccionan OHLC horarios."""
    from src.indices_math import trading_segments
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.to_datetime(now, utc=True)
    if df.empty:
        return pd.DataFrame(columns=EMPTY_COLUMNS), {"omitted": 0}
    raw = canonical(df)
    bars = _eligible_hours(raw, "CME_Equity", now)
    if bars.empty:
        return pd.DataFrame(columns=EMPTY_COLUMNS), {"omitted": 0}
    starts = sorted(int(t[:2]) * 60 + int(t[3:]) for t in spec["starts"])
    if len(starts) != 6 or any((starts[(i+1) % 6] - starts[i]) % 1440 != 240 for i in range(6)):
        raise ValueError("El horario de plataforma debe tener seis aperturas separadas por cuatro horas.")
    if starts[0] % 60:
        raise ValueError("No se puede reconstruir una apertura a :30 con horas del futuro a :00; falta una fuente horaria compatible.")
    local = bars.timestamp.dt.tz_convert(spec["timezone"])
    shifted = local - pd.Timedelta(minutes=starts[0])
    buckets = shifted.dt.floor("4h", ambiguous="infer", nonexistent="shift_forward") + pd.Timedelta(minutes=starts[0])
    bars["bucket"] = buckets.dt.tz_convert("UTC")
    segments = trading_segments("CME_Equity", raw.timestamp.min() - pd.Timedelta(days=3), raw.timestamp.max() + pd.Timedelta(days=3))
    intervals = pd.IntervalIndex.from_tuples([(a, b) for a, b, _ in segments], closed="left")
    rows, omitted = [], 0
    for start, group in bars.groupby("bucket", sort=True):
        end = start + pd.Timedelta(hours=4)
        grid = pd.date_range(start, end, freq="h", inclusive="left")
        expected = grid[intervals.get_indexer(grid) >= 0]
        if len(expected) == 0 or set(group.timestamp) != set(expected) or (group.bar_end > end).any() or end > now:
            omitted += 1
            continue
        rows.append({"timestamp": start, "open": group.open.iloc[0], "high": group.high.max(),
                     "low": group.low.min(), "close": group.close.iloc[-1], "volume": group.volume.sum()})
    return pd.DataFrame(rows, columns=EMPTY_COLUMNS), {"omitted": omitted, "method": "future_utc"}


def _archive(conn, symbol, table, rows, archived_at):
    for row in rows:
        payload = json.dumps(dict(row), sort_keys=True, default=str)
        key = hashlib.sha256((table + payload).encode()).hexdigest()
        conn.execute("INSERT OR IGNORE INTO four_hour_archives VALUES (?,?,?,?,?)", (key, symbol, table, archived_at, payload))


def rebuild_one(db, symbol, now=None):
    """Prepara antes de escribir; migración atómica e idempotente, archivo antes de reemplazo."""
    import sqlite3
    from src.data.audit import stamp
    spec = policy(symbol)
    if spec is None:
        return {"symbol": symbol, "changed": False, "reason": "Sin cambio según auditoría"}
    source = db.load_candles(spec["reference"], "1h")
    if source.empty:
        raise ValueError(f"Faltan horas de {spec['reference']}; se conserva la serie actual de {symbol}.")
    frame, quality = build_future(source, spec, now) if spec["method"] == "future_utc" else build_session(source, now)
    if frame.empty:
        raise ValueError(f"No hay bloques completos de {spec['reference']}; no se reemplazó {symbol}.")
    frame["timestamp"] = pd.to_datetime(frame.timestamp, utc=True).dt.strftime("%Y-%m-%d %H:%M:%S%z")
    src_name = f"via {spec['reference']}" if spec["method"] == "future_utc" else "session_4h_us"
    new = [(symbol, "4h", str(r.timestamp), float(r.open), float(r.high), float(r.low), float(r.close), float(r.volume), src_name)
           for r in frame.itertuples()]
    now_stamp = stamp()
    with db._get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.row_factory = sqlite3.Row
        initialize_series(conn)
        current = conn.execute("SELECT * FROM candles WHERE symbol=? AND timeframe='4h' ORDER BY timestamp", (symbol,)).fetchall()
        old = [(r["symbol"], r["timeframe"], r["timestamp"], r["open"], r["high"], r["low"], r["close"], r["volume"], r["source"]) for r in current]
        previous = conn.execute("SELECT version,input_versions_json FROM four_hour_series WHERE asset=?", (symbol,)).fetchone()
        version = version_for(spec)
        input_json = json.dumps([source.attrs["data_version"]], sort_keys=True)
        if old == new and previous and previous[0] == version and previous[1] == input_json:
            return {"symbol": symbol, "changed": False, "bars": len(new), "version": version}
        _archive(conn, symbol, "candles", current, now_stamp)
        # Primera generación de Yahoo: se conserva íntegra con otra temporalidad.
        for r in current:
            if r["source"] not in {"session_4h_us", *[f"via {s}" for s in configuration()[0]["index_futures"].values()]}:
                conn.execute("""INSERT OR IGNORE INTO candles
                    (symbol,timeframe,timestamp,open,high,low,close,volume,source,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (symbol, "4h_legacy", r["timestamp"], r["open"], r["high"], r["low"], r["close"], r["volume"], r["source"], r["updated_at"]))
        # Los resultados activos anteriores también se archivan para no mezclar generaciones.
        for table in ["calc_regimes", "calc_zscores"]:
            results = conn.execute(f"SELECT * FROM {table} WHERE symbol=? AND timeframe='4h'", (symbol,)).fetchall()
            _archive(conn, symbol, table, results, now_stamp)
            conn.execute(f"DELETE FROM {table} WHERE symbol=? AND timeframe='4h'", (symbol,))
        pairs = yaml.safe_load((ROOT / "config/pairs.yaml").read_text(encoding="utf-8"))
        for section_pairs in pairs.values():
            for pair in section_pairs:
                if symbol in (pair["y"], pair["x"]):
                    key = f"{pair['y']}/{pair['x']}"
                    results = conn.execute("SELECT * FROM calc_cointegration WHERE pair=? AND timeframe='4h'", (key,)).fetchall()
                    _archive(conn, symbol, "calc_cointegration", results, now_stamp)
                    conn.execute("DELETE FROM calc_cointegration WHERE pair=? AND timeframe='4h'", (key,))
        conn.execute("DELETE FROM candles WHERE symbol=? AND timeframe='4h'", (symbol,))
        conn.executemany("""INSERT INTO candles(symbol,timeframe,timestamp,open,high,low,close,volume,source,updated_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?)""", [r + (now_stamp,) for r in new])
        db._touch_version(conn, "candles", symbol, "4h")
        conn.execute("""INSERT INTO four_hour_series VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(asset)
          DO UPDATE SET version=excluded.version,method=excluded.method,reference=excluded.reference,
          timezone=excluded.timezone,starts_json=excluded.starts_json,rebuilt_at=excluded.rebuilt_at,
          input_versions_json=excluded.input_versions_json,quality_json=excluded.quality_json""",
          (symbol, version, spec["method"], spec["reference"], spec["timezone"], json.dumps(spec["starts"]),
           now_stamp, now_stamp, input_json, json.dumps(quality)))
    return {"symbol": symbol, "changed": True, "bars": len(new), "version": version, **quality}


def sufficient_history(df, calc_config):
    from src.calc.regime import calculate_atr
    regime = calc_config.get("regime", {})
    zscore = calc_config.get("zscore", {})
    # ATR14 deja 13 valores iniciales sin ATR: 250 válidos requiere 263 velas.
    required = max(regime.get("atr_percentile_window", 250) + regime.get("atr_period", 14) - 1,
                   zscore.get("percentile_window", 250) + zscore.get("atr_period", 14) - 1,
                   regime.get("min_bars_required", 60), zscore.get("std_period", 50) + 5)
    if len(df) < required:
        return False, required
    # Contar velas no basta cuando una ventana contiene precios sin ATR válido.
    # Wilder puede arrastrar el ATR anterior ante un NaN: no contarlo como nuevo.
    valid_prices = np.isfinite(df[["high", "low", "close"]]).all(axis=1) & np.isfinite(df.close.shift(1))
    for settings, window_key in [(regime, "atr_percentile_window"), (zscore, "percentile_window")]:
        window = settings.get(window_key, 250)
        atr = calculate_atr(df, settings.get("atr_period", 14)).tail(window)
        if len(atr) < window or not np.isfinite(atr).all() or not valid_prices.tail(window).all():
            return False, required
    return True, required


def prepare_stored(df, symbol, now=None, calendar_name=None):
    """Leer la 4h activa sin recortar la vela del futuro con el horario del índice."""
    from src.indices_math import prepare_bars, schedule, trading_segments
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.to_datetime(now, utc=True)
    if df.empty:
        return df.assign(session=pd.Series(dtype=str), bar_end=pd.Series(dtype="datetime64[ns, UTC]"), closed=pd.Series(dtype=bool))
    out = canonical(df)
    source = str(out.source.iloc[-1]) if "source" in out else ""
    if source == "session_4h_us":
        days = out.timestamp.dt.tz_convert("America/New_York").dt.date
        sch = schedule("NYSE", str(days.min()), str(days.max()))
        closes = {d.date(): r.market_close for d, r in sch.iterrows()}
        limit = pd.to_datetime(days.map(closes), utc=True)
        expected = out.timestamp + pd.Timedelta(hours=4)
        out["bar_end"] = expected.where(expected <= limit, limit)
        out["session"] = days.astype(str)
    elif source.startswith("via "):
        segments = trading_segments("CME_Equity", out.timestamp.min() - pd.Timedelta(days=3), out.timestamp.max() + pd.Timedelta(days=4))
        expected = pd.DatetimeIndex(out.timestamp + pd.Timedelta(hours=4)).as_unit("ns").asi8
        starts = np.array([a.value for a, _, _ in segments], dtype=np.int64)
        ends = np.array([b.value for _, b, _ in segments], dtype=np.int64)
        positions = np.searchsorted(starts, expected, side="left") - 1
        positions = np.maximum(positions, 0)
        out["bar_end"] = pd.to_datetime(np.minimum(expected, ends[positions]), utc=True)
        out["session"] = [segments[p][2] for p in positions]
    else:
        cal = calendar_name
        if cal is None:
            cal = "XETR" if symbol == "^GDAXI" else "JPX" if symbol == "^N225" else "CME_Equity" if symbol.endswith("=F") else "NYSE"
        if "/" in symbol:
            out["bar_end"] = out.timestamp + pd.Timedelta(hours=4)
            out["session"] = out.timestamp.dt.date.astype(str)
        elif symbol.endswith(".BA"):
            from src.data.audit import candle_end
            out["bar_end"] = pd.to_datetime([candle_end(ts, symbol, "4h", source) for ts in out.timestamp], utc=True)
            out["session"] = out.timestamp.dt.tz_convert("America/Argentina/Buenos_Aires").dt.date.astype(str)
        else:
            # Las etiquetas UTC pueden empezar antes de la apertura y contener
            # operaciones posteriores. No eliminar esas velas ya guardadas.
            segments = trading_segments(cal, out.timestamp.min() - pd.Timedelta(days=3), out.timestamp.max() + pd.Timedelta(days=4))
            expected = pd.DatetimeIndex(out.timestamp + pd.Timedelta(hours=4)).as_unit("ns").asi8
            starts = np.array([a.value for a, _, _ in segments], dtype=np.int64)
            ends = np.array([b.value for _, b, _ in segments], dtype=np.int64)
            positions = np.maximum(np.searchsorted(starts, expected, side="left") - 1, 0)
            capped = np.minimum(expected, ends[positions])
            beginning = pd.DatetimeIndex(out.timestamp).as_unit("ns").asi8
            out["bar_end"] = pd.to_datetime(np.where(capped > beginning, capped, expected), utc=True)
            out["session"] = [segments[p][2] for p in positions]
    out["closed"] = out.bar_end <= now
    if "updated_at" in out:
        verified = out.updated_at.astype(str).str.contains("T", regex=False)
        received = pd.to_datetime(out.updated_at, utc=True, errors="coerce", format="mixed")
        out["receipt_verified"] = verified
        out.loc[verified & (received < out.bar_end), "closed"] = False
    return out.reset_index(drop=True)


def market_results(df, calc_config):
    from src.calc.regime import get_latest_market_regime
    from src.calc.zscore import get_latest_zscore
    enough, required = sufficient_history(df, calc_config)
    if enough:
        return get_latest_market_regime(df, calc_config.get("regime")), get_latest_zscore(df, calc_config.get("zscore"))
    message = f"Historia insuficiente en 4h: {len(df)} velas; se necesitan al menos {required} y una ventana completa de observaciones válidas de ATR."
    timestamp = df.timestamp.iloc[-1] if len(df) else None
    reg = {"direction": "sin datos", "volatility": "sin datos", "regime": "Historia insuficiente en 4h", "adx": None,
           "atr": None, "atr_percentile": None, "ema": None, "close": None, "timestamp": timestamp, "error_message": message}
    z = {"z_atr": None, "z_std": None, "is_extreme": False, "z_percentile": None, "mean": None,
         "close": None, "timestamp": timestamp, "error_message": message}
    return reg, z
