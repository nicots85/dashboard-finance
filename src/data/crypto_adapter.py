"""
crypto_adapter.py — Adaptador para criptomonedas usando ccxt y API pública de Hyperliquid.
Maneja paginación para descargar historial extenso, reintentos y fallback automático:
Binance -> Bybit -> OKX -> Hyperliquid API para tokens especiales como HYPE.
"""

import time
import logging
from typing import Optional, Dict, Any, List
import pandas as pd
import requests
import ccxt
from src.data.base_adapter import BaseAdapter

logger = logging.getLogger(__name__)


class CryptoAdapter(BaseAdapter):
    """Adaptador de cripto con soporte multi-exchange y paginación profunda."""

    TF_MAP = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "1h",
        "4h": "4h",
        "1D": "1d",
    }

    def __init__(self, default_exchange: str = "binance", max_retries: int = 3):
        super().__init__(name="crypto")
        self.default_exchange_name = default_exchange
        self.max_retries = max_retries
        self._exchanges: Dict[str, Any] = {}
        self.source_used: Dict[str, str] = {}  # Registra qué exchange se usó para cada activo

    def _get_exchange(self, name: str):
        """Instancia o reutiliza una conexión ccxt con rate limiting."""
        if name not in self._exchanges:
            exchange_class = getattr(ccxt, name)
            self._exchanges[name] = exchange_class({
                "enableRateLimit": True,
                "timeout": 15000,
            })
        return self._exchanges[name]

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1D",
        since: Optional[pd.Timestamp] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Descarga OHLCV para un activo cripto con paginación y fallback.
        """
        if timeframe not in self.TF_MAP:
            raise ValueError(f"Temporalidad '{timeframe}' no soportada por CryptoAdapter.")

        ccxt_tf = self.TF_MAP[timeframe]

        # Para HYPE o cualquier activo que falle en Binance, probamos en cascada:
        # Binance -> Bybit -> OKX -> Hyperliquid API
        exchanges_to_try = [self.default_exchange_name, "bybit", "okx", "hyperliquid"]
        if symbol.startswith("HYPE"):
            # Ponemos bybit y okx antes porque HYPE no está en spot de Binance
            exchanges_to_try = ["bybit", "okx", "binance", "hyperliquid"]

        last_error = None
        for ex_name in exchanges_to_try:
            try:
                if ex_name == "hyperliquid":
                    df = self._fetch_hyperliquid(symbol, timeframe, since=since, limit=limit)
                else:
                    df = self._fetch_ccxt_paginated(ex_name, symbol, ccxt_tf, since=since, limit=limit)

                if df is not None and not df.empty:
                    self.source_used[symbol] = ex_name
                    return self.validate_df(df)
            except Exception as e:
                last_error = e
                logger.debug(f"Fallo al descargar {symbol} de {ex_name}: {e}")
                continue

        # Si llegamos acá y fallaron todos los exchanges
        if last_error:
            raise RuntimeError(f"No se pudo descargar {symbol} de ningún exchange ({exchanges_to_try}): {last_error}")
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    def _fetch_ccxt_paginated(
        self,
        exchange_name: str,
        symbol: str,
        timeframe: str,
        since: Optional[pd.Timestamp] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """Descarga paginada usando la API de ccxt."""
        ex = self._get_exchange(exchange_name)
        
        # Verificar si el mercado existe en este exchange
        try:
            if not ex.markets:
                ex.load_markets()
        except Exception:
            pass

        if ex.markets and symbol not in ex.markets:
            raise ValueError(f"Símbolo {symbol} no cotiza en {exchange_name}")

        since_ms = int(since.timestamp() * 1000) if since is not None else None
        all_ohlcv: List[list] = []
        batch_limit = 1000

        # Si no se pasó 'since', traemos historia inicial
        max_batches = 10 if since is None else 50
        for _ in range(max_batches):
            ohlcv = None
            for attempt in range(1, self.max_retries + 1):
                try:
                    ohlcv = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=batch_limit)
                    break
                except Exception as e:
                    if attempt == self.max_retries:
                        raise
                    time.sleep(1.0 * attempt)

            if not ohlcv:
                break

            all_ohlcv.extend(ohlcv)

            # Si ya nos devolvió menos del batch_limit, llegamos al presente
            if len(ohlcv) < batch_limit:
                break

            # Avanzar since_ms para la siguiente página
            last_timestamp = ohlcv[-1][0]
            if since_ms is not None and last_timestamp <= since_ms:
                break
            since_ms = last_timestamp + 1

            if limit is not None and len(all_ohlcv) >= limit:
                break

        if not all_ohlcv:
            return pd.DataFrame()

        df = pd.DataFrame(all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df

    def _fetch_hyperliquid(
        self,
        symbol: str,
        timeframe: str,
        since: Optional[pd.Timestamp] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """Descarga directa desde la API pública de Hyperliquid (REST endpoint)."""
        coin = symbol.split("/")[0]  # 'HYPE/USDT' -> 'HYPE'
        interval_map = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1D": "1d"}
        hl_interval = interval_map.get(timeframe, "1d")

        url = "https://api.hyperliquid.xyz/info"
        headers = {"Content-Type": "application/json"}

        start_time = int(since.timestamp() * 1000) if since is not None else 0
        end_time = int(time.time() * 1000)

        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin": coin,
                "interval": hl_interval,
                "startTime": start_time,
                "endTime": end_time,
            },
        }

        res = requests.post(url, json=payload, headers=headers, timeout=10)
        res.raise_for_status()
        candles = res.json()

        if not candles or not isinstance(candles, list):
            return pd.DataFrame()

        records = []
        for c in candles:
            records.append({
                "timestamp": pd.to_datetime(c["t"], unit="ms", utc=True),
                "open": float(c["o"]),
                "high": float(c["h"]),
                "low": float(c["l"]),
                "close": float(c["c"]),
                "volume": float(c["v"]),
            })

        return pd.DataFrame(records)
