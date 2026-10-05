"""
yahoo_adapter.py — Adaptador para Yahoo Finance (yfinance).
Maneja límites de temporalidades, agrupación automática de 1h a 4h,
conversión horaria UTC y reintentos ante fallas transitorias.
"""

import time
import logging
from typing import Optional
from datetime import datetime, timezone
import pandas as pd
import yfinance as yf
from src.data.base_adapter import BaseAdapter

logger = logging.getLogger(__name__)


class YahooAdapter(BaseAdapter):
    """Adaptador de mercado para Yahoo Finance."""

    # Mapeo de temporalidades de la app a intervalos válidos de yfinance
    TF_MAP = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "1h",
        "4h": "1h",  # se descarga en 1h y se resamplea a 4h
        "1D": "1d",
    }

    # Límites aproximados de retención de Yahoo Finance (en días)
    MAX_DAYS = {
        "1m": 7,
        "5m": 59,
        "15m": 59,
        "1h": 729,
        "4h": 729,
        "1D": 36500,  # ~100 años / historia completa
    }

    def __init__(self, max_retries: int = 3, retry_delay: float = 2.0):
        super().__init__(name="yahoo")
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.fetch_notices = {}

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1D",
        since: Optional[pd.Timestamp] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Descarga datos OHLCV desde Yahoo Finance.
        Para 4h, descarga en 1h y agrupa las velas con resample ('4h').
        """
        if timeframe not in self.TF_MAP:
            raise ValueError(f"Temporalidad '{timeframe}' no soportada por YahooAdapter.")
        notices = []
        self.fetch_notices[(symbol, timeframe)] = notices

        yf_interval = self.TF_MAP[timeframe]
        max_lookback_days = self.MAX_DAYS[timeframe]

        now_utc = datetime.now(timezone.utc)
        earliest_allowed = now_utc - pd.Timedelta(days=max_lookback_days)

        start_dt = since
        if start_dt is not None:
            if start_dt.tz is None:
                start_dt = start_dt.tz_localize("UTC")
            else:
                start_dt = start_dt.tz_convert("UTC")
            # Respetar límite máximo de la API de Yahoo
            if start_dt < earliest_allowed:
                notices.append({"kind": "download_limit", "message":
                    f"Yahoo solo permite recuperar aproximadamente {max_lookback_days} días en {timeframe}. "
                    f"La actualización de {symbol} pidió desde {start_dt.isoformat()}; el tramo anterior a {earliest_allowed.isoformat()} no se pudo recuperar. Las velas guardadas se conservan."})
                start_dt = earliest_allowed
        else:
            if timeframe in ["1m", "5m", "15m", "1h", "4h"]:
                start_dt = earliest_allowed

        ticker = yf.Ticker(symbol)
        raw_df = pd.DataFrame()

        for attempt in range(1, self.max_retries + 1):
            try:
                if start_dt is not None:
                    # En intradía agregamos un margen hacia atrás para no perder la vela en curso
                    start_str = start_dt.strftime("%Y-%m-%d")
                    raw_df = ticker.history(
                        interval=yf_interval,
                        start=start_str,
                        auto_adjust=False,
                        raise_errors=True,
                    )
                else:
                    raw_df = ticker.history(
                        period="max",
                        interval=yf_interval,
                        auto_adjust=False,
                        raise_errors=True,
                    )
                break
            except Exception as e:
                logger.warning(f"Intento {attempt}/{self.max_retries} falló para {symbol} ({timeframe}): {e}")
                if attempt == self.max_retries:
                    raise
                time.sleep(self.retry_delay * attempt)

        if raw_df is None or raw_df.empty:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        # Estandarizar columnas y timezone
        raw_df = raw_df.reset_index()
        # Columna de fecha puede llamarse 'Date' o 'Datetime'
        date_col = "Datetime" if "Datetime" in raw_df.columns else "Date"
        raw_df = raw_df.rename(
            columns={
                date_col: "timestamp",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )

        raw_df = self.validate_df(raw_df)

        # Si se pidió 4h, agrupar velas de 1h
        if timeframe == "4h":
            raw_df = self._resample_to_4h(raw_df)

        # Filtrar estrictamente 'since' si se especificó
        if since is not None and not raw_df.empty:
            if since.tz is None:
                since = since.tz_localize("UTC")
            raw_df = raw_df[raw_df["timestamp"] >= since].reset_index(drop=True)

        if limit is not None and not raw_df.empty:
            raw_df = raw_df.tail(limit).reset_index(drop=True)

        return raw_df

    def _resample_to_4h(self, df_1h: pd.DataFrame) -> pd.DataFrame:
        """Agrupa velas de 1 hora en velas de 4 horas con regla financiera estándar."""
        if df_1h.empty:
            return df_1h

        df = df_1h.copy().set_index("timestamp")
        resampled = df.resample("4h", label="left", closed="left").agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        ).dropna(subset=["close"])

        resampled = resampled.reset_index()
        return self.validate_df(resampled)
