"""
fred_adapter.py — Adaptador para datos macroeconómicos de FRED (Federal Reserve Bank of St. Louis).
Descarga series temporales y entrega datos estandarizados con timestamp UTC y valor de cierre.
"""

import os
import time
import logging
from typing import Optional
import pandas as pd
from fredapi import Fred
from src.data.base_adapter import BaseAdapter

logger = logging.getLogger(__name__)


class FredAdapter(BaseAdapter):
    """Adaptador para series macroeconómicas de la Reserva Federal (FRED)."""

    def __init__(self, api_key: Optional[str] = None, max_retries: int = 3):
        super().__init__(name="fred")
        self.api_key = api_key or os.getenv("FRED_API_KEY")
        if not self.api_key:
            raise ValueError("No se encontró FRED_API_KEY en variables de entorno.")
        self.fred = Fred(api_key=self.api_key)
        self.max_retries = max_retries

    def fetch_series(
        self,
        series_id: str,
        since: Optional[pd.Timestamp] = None,
    ) -> pd.DataFrame:
        """
        Descarga una serie temporal de FRED.
        Retorna DataFrame con ['timestamp', 'value'].
        """
        start_date = None
        if since is not None:
            start_date = since.strftime("%Y-%m-%d")

        s = None
        for attempt in range(1, self.max_retries + 1):
            try:
                s = self.fred.get_series(series_id, observation_start=start_date)
                break
            except Exception as e:
                logger.warning(f"Intento {attempt}/{self.max_retries} falló para FRED {series_id}: {e}")
                if attempt == self.max_retries:
                    raise
                time.sleep(1.5 * attempt)

        if s is None or s.empty:
            return pd.DataFrame(columns=["timestamp", "value"])

        df = s.dropna().reset_index()
        df.columns = ["timestamp", "value"]

        # Timestamp en UTC
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna().sort_values("timestamp").drop_duplicates(subset=["timestamp"]).reset_index(drop=True)

        return df

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1D",
        since: Optional[pd.Timestamp] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Adapta la serie FRED al formato OHLCV común (donde open=high=low=close=value, volume=0)
        para permitir compatibilidad si se requiere tratar como activo.
        """
        df = self.fetch_series(symbol, since=since)
        if df.empty:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        df["open"] = df["value"]
        df["high"] = df["value"]
        df["low"] = df["value"]
        df["close"] = df["value"]
        df["volume"] = 0.0

        res = self.validate_df(df[["timestamp", "open", "high", "low", "close", "volume"]])
        if limit is not None:
            res = res.tail(limit).reset_index(drop=True)
        return res
