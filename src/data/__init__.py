"""
src/data — Módulo de adaptadores de datos y almacenamiento de dashboard-finance.
"""

from src.data.base_adapter import BaseAdapter
from src.data.yahoo_adapter import YahooAdapter
from src.data.crypto_adapter import CryptoAdapter
from src.data.fred_adapter import FredAdapter
from src.data.ibkr_adapter import IBKRAdapter
from src.data.db_manager import DatabaseManager

__all__ = [
    "BaseAdapter",
    "YahooAdapter",
    "CryptoAdapter",
    "FredAdapter",
    "IBKRAdapter",
    "DatabaseManager",
]
