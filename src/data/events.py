"""Eventos corporativos (dividendos y splits) de la acción local, desde Yahoo.

Los descarga por símbolo con yfinance y los persiste en la tabla
calendar_events; las fotos los consultan para marcar el «posible evento
corporativo» del CCL implícito durante la ventana configurable desde el
ex-dividendo local.
"""
import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
import sqlite3
import yfinance as yf

logger = logging.getLogger("events")


def ensure_events_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS calendar_events (
        symbol TEXT NOT NULL, kind TEXT NOT NULL, ex_date TEXT NOT NULL,
        amount REAL, recorded_at TEXT NOT NULL,
        PRIMARY KEY (symbol, kind, ex_date))""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_symbol ON calendar_events(symbol, ex_date)")


def _symbol_events(symbol):
    """Dividendos y splits {ex_date: (tipo, valor)} de los últimos 90 días."""
    edi = {}
    limite = (datetime.now(timezone.utc) - timedelta(days=90)).date()
    ticker = yf.Ticker(symbol)
    try:
        for when, amount in ticker.dividends.items():
            fecha = when.date() if hasattr(when, "date") else pd.Timestamp(when).date()
            if fecha >= limite:
                edi[str(fecha)] = ("dividendo", float(amount))
    except Exception as exc:
        logger.warning("Dividendos de %s sin datos: %s", symbol, exc)
    try:
        for when, ratio in ticker.splits.items():
            fecha = when.date() if hasattr(when, "date") else pd.Timestamp(when).date()
            if fecha >= limite:
                edi[str(fecha)] = ("split", float(ratio))
    except Exception as exc:
        logger.warning("Splits de %s sin datos: %s", symbol, exc)
    return edi


def sync_events(conn, symbols):
    """Descarga y guarda los eventos recientes; devuelve (nuevos, vigentes)."""
    ensure_events_table(conn)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    nuevos = 0
    for symbol in symbols:
        for ex_date, (kind, valor) in _symbol_events(symbol).items():
            cur = conn.execute("SELECT amount FROM calendar_events WHERE symbol=? AND kind=? AND ex_date=?",
                               (symbol, kind, ex_date))
            if cur.fetchone() is None:
                conn.execute("INSERT INTO calendar_events VALUES (?,?,?,?,?)",
                             (symbol, kind, ex_date, valor, now))
                nuevos += 1
    conn.execute("DELETE FROM calendar_events WHERE ex_date < ?",
                 ((datetime.now(timezone.utc) - timedelta(days=90)).date().isoformat(),))
    conn.commit()
    vigentes = conn.execute("SELECT COUNT(*) FROM calendar_events").fetchone()[0]
    return nuevos, vigentes


def read_events(conn, symbol):
    rows = conn.execute("SELECT kind, ex_date, amount FROM calendar_events WHERE symbol=? ORDER BY ex_date", (symbol,)).fetchall()
    if not rows and conn.execute("SELECT COUNT(*) FROM calendar_events").fetchone()[0] == 0:
        return None  # tabla sin datos: la marca se omite silenciosamente
    return [{"tipo": kind, "ex_date": ex_date, "monto": amount} for kind, ex_date, amount in rows]
