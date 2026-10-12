"""Base compartida de pruebas históricas de versiones ya aprobadas.

La normalización solo ocurre en la copia de test: una vela diaria por sesión de
futuro. Versiones antiguas no soportan etiquetas duplicadas cuando Yahoo cambia
el horario de la etiqueta diaria. No se toca la base productiva ni se inventan
precios. Las regresiones de regla actual y Small caps usan la copia íntegra.
El corpus histórico conserva hasta 3000 cierres diarios y 6000 velas intradía
por serie: cubre todas las ventanas/bloques y evita cargar décadas repetidamente
en código antiguo sin la optimización de calendarios. Ambos lados usan el mismo
corpus, y no se atribuye a esta prueba una validación de la regla actual.
"""
import sqlite3

import pandas as pd

from src.data.backup import snapshot_database
from src.indices_math import prepare_bars


def historical_snapshot(source, destination):
    snapshot_database(source, destination)
    with sqlite3.connect(destination) as conn:
        for symbol in ("GC=F", "SI=F", "HG=F", "PL=F"):
            raw = pd.read_sql_query("SELECT * FROM candles WHERE symbol=? AND timeframe='1D' ORDER BY timestamp", conn, params=(symbol,))
            if raw.empty:
                continue
            raw["raw_timestamp"] = raw.timestamp
            prepared = prepare_bars(raw, symbol, "1D", "CME_Equity")
            duplicated = prepared[prepared.session.duplicated(keep="last")]
            for stamp in duplicated.raw_timestamp:
                conn.execute("DELETE FROM candles WHERE symbol=? AND timeframe='1D' AND timestamp=?", (symbol, stamp))
        conn.execute("""DELETE FROM candles WHERE rowid IN (
            SELECT rowid FROM (SELECT rowid,timeframe,ROW_NUMBER() OVER (
                PARTITION BY symbol,timeframe ORDER BY timestamp DESC) AS rn FROM candles)
            WHERE rn > CASE WHEN timeframe='1D' THEN 3000 ELSE 6000 END)""")
