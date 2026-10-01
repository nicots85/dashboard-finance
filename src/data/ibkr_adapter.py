"""
ibkr_adapter.py — Adaptador para Interactive Brokers (TWS / Gateway API).
Lugar previsto y documentado para conectar IBKR en el futuro sin modificar
el resto del motor de datos ni la base de almacenamiento.
"""

from typing import Optional
import pandas as pd
from src.data.base_adapter import BaseAdapter


class IBKRAdapter(BaseAdapter):
    """
    Adaptador planificado para Interactive Brokers (TWS API / ib_insync).
    Para activarlo a futuro:
    1. Instalar cliente IBKR (ej. ib_insync o ibapi).
    2. Configurar host, puerto y client_id de TWS o IB Gateway.
    3. Implementar fetch_ohlcv mapeando el contrato y la resolución temporal.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 7496, client_id: int = 1):
        super().__init__(name="ibkr")
        self.host = host
        self.port = port
        self.client_id = client_id
        self._connected = False

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1D",
        since: Optional[pd.Timestamp] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Descarga OHLCV desde Interactive Brokers (Pendiente de implementación).
        """
        raise NotImplementedError(
            "El adaptador de Interactive Brokers (IBKR) está previsto en la arquitectura "
            "pero aún no está configurado. Conectar mediante TWS API cuando sea requerido."
        )
