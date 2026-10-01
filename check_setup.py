"""
check_setup.py — Verificación del entorno de dashboard-finance
Prueba las 3 fuentes de datos: FRED, yfinance y ccxt (Binance).
Resultado esperado: 3 líneas con "OK".
"""

import sys
from dotenv import load_dotenv
import os

# Cargar variables del archivo .env
load_dotenv()

errores = []

# ── 1. FRED (VIXCLS) ──────────────────────────────────────────────
print("Probando FRED (VIXCLS)...", end=" ")
try:
    from fredapi import Fred
    clave = os.getenv("FRED_API_KEY")
    if not clave:
        raise ValueError("No se encontró FRED_API_KEY en el archivo .env")
    fred = Fred(api_key=clave)
    datos = fred.get_series("VIXCLS", limit=1)
    if datos is None or datos.empty:
        raise ValueError("FRED devolvió datos vacíos")
    print(f"OK ── último valor VIX: {datos.dropna().iloc[-1]:.2f}")
except Exception as e:
    msg = f"ERROR en FRED: {e}"
    print(msg)
    errores.append(msg)

# ── 2. yfinance (^NDX = Nasdaq 100) ───────────────────────────────
print("Probando yfinance (^NDX)...", end=" ")
try:
    import yfinance as yf
    ticker = yf.Ticker("^NDX")
    hist = ticker.history(period="5d")
    if hist.empty:
        raise ValueError("yfinance devolvió datos vacíos para ^NDX")
    ultimo = hist["Close"].iloc[-1]
    print(f"OK ── último cierre Nasdaq 100: {ultimo:,.2f}")
except Exception as e:
    msg = f"ERROR en yfinance: {e}"
    print(msg)
    errores.append(msg)

# ── 3. ccxt / Binance (BTC/USDT) ──────────────────────────────────
print("Probando ccxt/Binance (BTC/USDT)...", end=" ")
try:
    import ccxt
    binance = ccxt.binance({"enableRateLimit": True})
    ticker_btc = binance.fetch_ticker("BTC/USDT")
    precio = ticker_btc["last"]
    if precio is None:
        raise ValueError("ccxt devolvió precio None para BTC/USDT")
    print(f"OK ── último precio BTC/USDT: {precio:,.2f}")
except Exception as e:
    msg = f"ERROR en ccxt/Binance: {e}"
    print(msg)
    errores.append(msg)

# ── Resumen ────────────────────────────────────────────────────────
print("\n" + "=" * 50)
if not errores:
    print("✅ TODO OK — Las 3 fuentes de datos funcionan correctamente.")
else:
    print(f"⚠️  Hubo {len(errores)} error(es):")
    for err in errores:
        print(f"   • {err}")
    sys.exit(1)
