"""
db_manager.py — Gestor de base de datos SQLite para dashboard-finance.
Maneja almacenamiento de velas OHLCV y series FRED, inserción incremental
(UPSERT / REPLACE) y consultas de última fecha guardada para evitar descargas redundantes.
"""

import os
import sqlite3
import logging
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Tuple
import pandas as pd
from src.data.audit import DataAuditMixin, initialize_audit, clock, stamp

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.environ.get("FINANCE_DB_PATH") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "finance.db",
)


class DatabaseManager(DataAuditMixin):
    """Administra la base de datos SQLite local para velas y series macro."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = os.fspath(db_path)
        # Asegurar que el directorio data/ exista
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self.init_db()

    @contextmanager
    def _get_connection(self):
        """Abre conexión con SQLite activando WAL mode y timeout para concurrencia."""
        if os.path.exists(self.db_path + ".restore-lock"):
            raise RuntimeError("La base se está restaurando. Esperá a que termine para actualizar o abrir el tablero.")
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def init_db(self):
        """Crea las tablas e índices si no existen."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Tabla de velas OHLCV
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS candles (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamp TEXT NOT NULL,   -- Formato ISO 8601 UTC (ej: '2025-01-01T00:00:00+00:00')
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL,
                    source TEXT,               -- yahoo, binance, bybit, etc.
                    updated_at TEXT DEFAULT (datetime('now')),
                    PRIMARY KEY (symbol, timeframe, timestamp)
                );
                """
            )

            # Índices para acelerar consultas por símbolo y rango temporal
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_candles_symbol_tf_ts 
                ON candles (symbol, timeframe, timestamp);
                """
            )

            # 2. Tabla de series macroeconómicas de FRED
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS fred_series (
                    series_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,   -- ISO 8601 UTC
                    value REAL,
                    updated_at TEXT DEFAULT (datetime('now')),
                    PRIMARY KEY (series_id, timestamp)
                );
                """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_fred_series_id_ts 
                ON fred_series (series_id, timestamp);
                """
            )

            # 3. Tablas de Cálculos Cuantitativos (Fase 3)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS calc_regimes (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    direction TEXT,
                    volatility TEXT,
                    regime TEXT,
                    adx REAL,
                    atr_percentile REAL,
                    updated_at TEXT DEFAULT (datetime('now')),
                    PRIMARY KEY (symbol, timeframe, timestamp)
                );
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS calc_zscores (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    z_atr REAL,
                    z_std REAL,
                    is_extreme INTEGER,
                    percentile REAL,
                    updated_at TEXT DEFAULT (datetime('now')),
                    PRIMARY KEY (symbol, timeframe, timestamp)
                );
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS calc_cointegration (
                    pair TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    p_value REAL,
                    beta REAL,
                    z_spread REAL,
                    half_life REAL,
                    is_cointegrated INTEGER,
                    pct_coint_windows REAL,
                    updated_at TEXT DEFAULT (datetime('now')),
                    PRIMARY KEY (pair, timeframe, timestamp)
                );
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS calc_macro (
                    series_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    current_value REAL,
                    change_1m REAL,
                    pct_change_1m REAL,
                    percentile REAL,
                    updated_at TEXT DEFAULT (datetime('now')),
                    PRIMARY KEY (series_id, timestamp)
                );
                """
            )
            initialize_audit(conn)
            conn.commit()

    def get_latest_candle_timestamp(self, symbol: str, timeframe: str) -> Optional[pd.Timestamp]:
        """
        Retorna la fecha UTC de la última vela guardada para un activo y temporalidad.
        Si no hay registros, retorna None.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT MAX(timestamp) FROM candles 
                WHERE symbol = ? AND timeframe = ?;
                """,
                (symbol, timeframe),
            )
            row = cursor.fetchone()
            if row and row[0]:
                return pd.to_datetime(row[0], utc=True)
            return None

    def get_latest_fred_timestamp(self, series_id: str) -> Optional[pd.Timestamp]:
        """Retorna la fecha UTC del último dato guardado para una serie FRED."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT MAX(timestamp) FROM fred_series 
                WHERE series_id = ?;
                """,
                (series_id,),
            )
            row = cursor.fetchone()
            if row and row[0]:
                return pd.to_datetime(row[0], utc=True)
            return None

    def save_candles(self, df: pd.DataFrame, symbol: str, timeframe: str, source: str = "", observed_at=None) -> int:
        """
        Guarda un DataFrame OHLCV en la tabla candles usando INSERT OR REPLACE.
        Retorna la cantidad de registros insertados o actualizados.
        """
        if df.empty:
            return 0

        # Preparar datos
        df_to_save = df.drop_duplicates(subset=["timestamp"], keep="last").copy()
        if not pd.api.types.is_datetime64_any_dtype(df_to_save["timestamp"]):
            df_to_save["timestamp"] = pd.to_datetime(df_to_save["timestamp"], utc=True)
        else:
            if df_to_save["timestamp"].dt.tz is None:
                df_to_save["timestamp"] = df_to_save["timestamp"].dt.tz_localize("UTC")
            else:
                df_to_save["timestamp"] = df_to_save["timestamp"].dt.tz_convert("UTC")

        # Formato estándar de fecha ISO en string para SQLite
        df_to_save["ts_str"] = df_to_save["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S%z")

        records = [
            (
                symbol,
                timeframe,
                row["ts_str"],
                float(row["open"]) if pd.notna(row["open"]) else None,
                float(row["high"]) if pd.notna(row["high"]) else None,
                float(row["low"]) if pd.notna(row["low"]) else None,
                float(row["close"]) if pd.notna(row["close"]) else None,
                float(row["volume"]) if pd.notna(row["volume"]) else 0.0,
                source,
            )
            for _, row in df_to_save.iterrows()
        ]

        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            now = observed_at or clock()
            fields = ["open", "high", "low", "close", "volume", "source"]
            previous = {row[0]: row for row in conn.execute(
                "SELECT timestamp,open,high,low,close,volume,source,updated_at FROM candles WHERE symbol=? AND timeframe=? AND timestamp BETWEEN ? AND ?",
                (symbol, timeframe, min(r[2] for r in records), max(r[2] for r in records)))}
            changed = False
            for record in records:
                old = previous.get(record[2])
                new = dict(zip(fields, record[3:]))
                if old is None:
                    changed = True
                elif tuple(old[1:7]) != tuple(record[3:]):
                    changed = True
                    self._record_correction(conn, symbol, timeframe, record[2], dict(zip(fields, old[1:7])), new, old[7], now)
            cursor.executemany(
                """
                INSERT OR REPLACE INTO candles 
                (symbol, timeframe, timestamp, open, high, low, close, volume, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                [record + (stamp(now),) for record in records],
            )
            if changed:
                self._touch_version(conn, "candles", symbol, timeframe, now)
            conn.commit()

        return len(records)

    def save_fred_series(self, df: pd.DataFrame, series_id: str) -> int:
        """Guarda registros de FRED en la tabla fred_series."""
        if df.empty:
            return 0

        df_to_save = df.copy()
        if not pd.api.types.is_datetime64_any_dtype(df_to_save["timestamp"]):
            df_to_save["timestamp"] = pd.to_datetime(df_to_save["timestamp"], utc=True)
        else:
            if df_to_save["timestamp"].dt.tz is None:
                df_to_save["timestamp"] = df_to_save["timestamp"].dt.tz_localize("UTC")
            else:
                df_to_save["timestamp"] = df_to_save["timestamp"].dt.tz_convert("UTC")

        df_to_save["ts_str"] = df_to_save["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S%z")

        records = [
            (
                series_id,
                row["ts_str"],
                float(row["value"]) if pd.notna(row["value"]) else None,
            )
            for _, row in df_to_save.iterrows()
        ]

        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            old = dict(conn.execute("SELECT timestamp,value FROM fred_series WHERE series_id=?", (series_id,)))
            changed = any(ts not in old or old[ts] != value for _, ts, value in records)
            cursor.executemany(
                """
                INSERT OR REPLACE INTO fred_series 
                (series_id, timestamp, value, updated_at)
                VALUES (?, ?, ?, datetime('now'));
                """,
                records,
            )
            if changed:
                self._touch_version(conn, "fred", series_id, "1D")
            conn.commit()

        return len(records)

    def save_regime_result(self, symbol: str, timeframe: str, regime_data: Dict[str, Any], input_versions=None, params=None) -> None:
        """Guarda o actualiza el resultado de régimen de mercado para la última vela."""
        if not regime_data or not regime_data.get("timestamp"):
            return
        ts_str = pd.to_datetime(regime_data["timestamp"], utc=True).strftime("%Y-%m-%d %H:%M:%S%z")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO calc_regimes 
                (symbol, timeframe, timestamp, direction, volatility, regime, adx, atr_percentile, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'));
                """,
                (
                    symbol,
                    timeframe,
                    ts_str,
                    regime_data.get("direction"),
                    regime_data.get("volatility"),
                    regime_data.get("regime"),
                    regime_data.get("adx"),
                    regime_data.get("atr_percentile"),
                ),
            )
            self._calculation_metadata(conn, "calc_regimes", symbol, timeframe, ts_str, input_versions, params,
                                       "no_calculable" if regime_data.get("direction") == "sin datos" else "ok")
            conn.commit()

    def save_zscore_result(self, symbol: str, timeframe: str, z_data: Dict[str, Any], input_versions=None, params=None) -> None:
        """Guarda o actualiza el z-score para la última vela."""
        if not z_data or not z_data.get("timestamp"):
            return
        ts_str = pd.to_datetime(z_data["timestamp"], utc=True).strftime("%Y-%m-%d %H:%M:%S%z")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO calc_zscores 
                (symbol, timeframe, timestamp, z_atr, z_std, is_extreme, percentile, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'));
                """,
                (
                    symbol,
                    timeframe,
                    ts_str,
                    z_data.get("z_atr"),
                    z_data.get("z_std"),
                    1 if z_data.get("is_extreme") else 0,
                    z_data.get("z_percentile"),
                ),
            )
            self._calculation_metadata(conn, "calc_zscores", symbol, timeframe, ts_str, input_versions, params,
                                       "no_calculable" if z_data.get("z_atr") is None else "ok")
            conn.commit()

    def save_cointegration_result(
        self,
        pair: str,
        timeframe: str,
        timestamp: Any,
        coint_data: Dict[str, Any],
        input_versions=None,
        params=None,
    ) -> None:
        """Guarda el resultado del test de cointegración."""
        if not timestamp:
            timestamp = pd.Timestamp.now(tz="UTC")
        ts_str = pd.to_datetime(timestamp, utc=True).strftime("%Y-%m-%d %H:%M:%S%z")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO calc_cointegration 
                (pair, timeframe, timestamp, p_value, beta, z_spread, half_life, is_cointegrated, pct_coint_windows, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'));
                """,
                (
                    pair,
                    timeframe,
                    ts_str,
                    coint_data.get("p_value"),
                    coint_data.get("beta"),
                    coint_data.get("z_spread"),
                    coint_data.get("half_life"),
                    1 if coint_data.get("is_cointegrated") else 0,
                    coint_data.get("pct_coint_windows"),
                ),
            )
            self._calculation_metadata(conn, "calc_cointegration", pair, timeframe, ts_str, input_versions, params,
                                       "no_calculable" if coint_data.get("p_value") is None else "ok", coint_data.get("error_message"))
            if coint_data.get("timestamp") is None and coint_data.get("p_value") is None:
                conn.execute("UPDATE calc_cointegration SET last_data_timestamp=NULL WHERE pair=? AND timeframe=? AND timestamp=?",
                             (pair, timeframe, ts_str))
            conn.commit()

    def save_macro_result(self, series_id: str, macro_data: Dict[str, Any], input_versions=None, params=None) -> None:
        """Guarda el análisis de una serie FRED."""
        if not macro_data or not macro_data.get("timestamp"):
            return
        ts_str = pd.to_datetime(macro_data["timestamp"], utc=True).strftime("%Y-%m-%d %H:%M:%S%z")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO calc_macro 
                (series_id, timestamp, current_value, change_1m, pct_change_1m, percentile, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'));
                """,
                (
                    series_id,
                    ts_str,
                    macro_data.get("current_value"),
                    macro_data.get("change_1m"),
                    macro_data.get("pct_change_1m"),
                    macro_data.get("percentile"),
                ),
            )
            self._calculation_metadata(conn, "calc_macro", series_id, "1D", ts_str, input_versions, params,
                                       "no_calculable" if macro_data.get("current_value") is None else "ok")
            conn.commit()

    def load_candles(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """Carga velas guardadas para un activo en un DataFrame ordenado."""
        query = "SELECT timestamp, open, high, low, close, volume, source FROM candles WHERE symbol = ? AND timeframe = ?"
        params = [symbol, timeframe]

        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date)
        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date)

        query += " ORDER BY timestamp ASC"

        with self._get_connection() as conn:
            conn.execute("BEGIN")
            version = self._input_version(conn, "candles", symbol, timeframe)
            df = pd.read_sql_query(query, conn, params=params)

        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

        df.attrs["data_version"] = version
        return df

    def load_fred_series(self, series_id: str) -> pd.DataFrame:
        """Carga serie de FRED en un DataFrame ordenado."""
        query = "SELECT timestamp, value FROM fred_series WHERE series_id = ? ORDER BY timestamp ASC"
        with self._get_connection() as conn:
            conn.execute("BEGIN")
            version = self._input_version(conn, "fred", series_id, "1D")
            df = pd.read_sql_query(query, conn, params=[series_id])

        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

        df.attrs["data_version"] = version
        return df

    def get_summary_stats(self) -> List[Dict[str, Any]]:
        """Devuelve un resumen de todos los activos, temporalidades y cantidad de velas."""
        stats = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT symbol, timeframe, COUNT(*), MIN(timestamp), MAX(timestamp), source
                FROM candles
                GROUP BY symbol, timeframe
                ORDER BY symbol, timeframe;
                """
            )
            for row in cursor.fetchall():
                stats.append({
                    "symbol": row[0],
                    "timeframe": row[1],
                    "count": row[2],
                    "min_date": row[3],
                    "max_date": row[4],
                    "source": row[5],
                })

            cursor.execute(
                """
                SELECT series_id, '1D' as timeframe, COUNT(*), MIN(timestamp), MAX(timestamp), 'fred' as source
                FROM fred_series
                GROUP BY series_id
                ORDER BY series_id;
                """
            )
            for row in cursor.fetchall():
                stats.append({
                    "symbol": row[0],
                    "timeframe": row[1],
                    "count": row[2],
                    "min_date": row[3],
                    "max_date": row[4],
                    "source": row[5],
                })

        return stats
