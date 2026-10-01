"""
base_adapter.py — Interfaz base para adaptadores de datos de dashboard-finance.
Garantiza que cualquier fuente (Yahoo, CCXT, FRED, IBKR futuro) entregue un DataFrame
estandarizado con columnas:
    ['timestamp', 'open', 'high', 'low', 'close', 'volume']
donde 'timestamp' es datetime con zona horaria UTC.
"""

from abc import ABC, abstractmethod
from typing import Optional
import pandas as pd


class BaseAdapter(ABC):
    """Interfaz estándar para todos los adaptadores de mercado."""

    TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1D"]

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1D",
        since: Optional[pd.Timestamp] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Descarga datos OHLCV para un activo y temporalidad.

        Parámetros:
            symbol: Ticker o símbolo del activo (ej: '^NDX', 'BTC/USDT').
            timeframe: Temporalidad ('1m', '5m', '15m', '1h', '4h', '1D').
            since: Timestamp UTC a partir del cual descargar (para actualización incremental).
            limit: Número máximo de registros (opcional).

        Retorna:
            pd.DataFrame con columnas: ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            index: RangeIndex (timestamp como columna normal en UTC).
        """
        pass

    @staticmethod
    def validate_df(df: pd.DataFrame) -> pd.DataFrame:
        """Valida y limpia el DataFrame para asegurar cumplimiento estricto del estándar."""
        expected_cols = ["timestamp", "open", "high", "low", "close", "volume"]
        if df.empty:
            return pd.DataFrame(columns=expected_cols)

        # Asegurar columnas requeridas
        for col in expected_cols:
            if col not in df.columns:
                raise ValueError(f"Falta columna obligatoria '{col}' en resultado del adaptador")

        # Asegurar timestamp en UTC sin zona horaria ambigua
        df = df.copy()
        if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        else:
            if df["timestamp"].dt.tz is None:
                df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")
            else:
                df["timestamp"] = df["timestamp"].dt.tz_convert("UTC")

        # Ordenar por fecha y eliminar duplicados
        df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"]).reset_index(drop=True)

        # Columnas numéricas
        num_cols = ["open", "high", "low", "close", "volume"]
        for c in num_cols:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        return df[expected_cols]
