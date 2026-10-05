#!/usr/bin/env python3
"""
update_data.py — Comando principal para descarga y actualización incremental del motor de datos.
Permite actualizar todas las secciones o una específica, y filtrar por temporalidades.

Uso:
    python update_data.py                     # Actualiza todo (temporalidades por defecto: 1m,5m,15m,1h,4h,1D)
    python update_data.py --seccion cripto    # Solo criptomonedas
    python update_data.py --tf 1D             # Solo velas diarias
    python update_data.py --tf 1m,5m,15m,1h,4h,1D --seccion indices
"""

import sys
import os
import argparse
import logging
from typing import List, Dict, Any, Optional
import yaml
from dotenv import load_dotenv
import pandas as pd

# Cargar variables de entorno (.env)
load_dotenv()

from src.data import (
    YahooAdapter,
    CryptoAdapter,
    FredAdapter,
    DatabaseManager,
)
from src.data.audit import recent_gaps
from src.data.db_manager import DEFAULT_DB_PATH
from src.data.backup import ROOT, ensure_daily_backup

# Configuración básica de logging limpio
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("update_data")


def load_config(config_path: str = "config/assets.yaml") -> Dict[str, Any]:
    """Carga la configuración de activos desde YAML."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"No se encontró el archivo de configuración en {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def update_market_asset(
    adapter,
    db: DatabaseManager,
    symbol: str,
    timeframes: List[str],
) -> List[Dict[str, Any]]:
    """Descarga y guarda velas de forma incremental para un activo en varias temporalidades."""
    results = []

    for tf in timeframes:
        try:
            # Consultar última fecha guardada en BD
            last_ts = db.get_latest_candle_timestamp(symbol, tf)
            
            # Descargar desde la última fecha conocida (o historia completa si es nuevo)
            df = adapter.fetch_ohlcv(symbol, timeframe=tf, since=last_ts)
            notices = getattr(adapter, "fetch_notices", {}).get((symbol, tf), [])
            db.resolve_data_notices(symbol, tf, ["download_limit", "download_error", "empty_response"])
            for notice in notices:
                db.record_data_notice(symbol, tf, notice["kind"], notice["message"])
                logger.warning(f"   ⚠️ {notice['message']}")

            if df is None or df.empty:
                # Si no vinieron datos nuevos pero ya había datos en BD
                total_in_db = db.load_candles(symbol, tf)
                source_used = getattr(adapter, "source_used", {}).get(symbol, adapter.name)
                if not total_in_db.empty:
                    results.append({
                        "symbol": symbol,
                        "tf": tf,
                        "count": len(total_in_db),
                        "min_date": total_in_db["timestamp"].min().strftime("%Y-%m-%d %H:%M"),
                        "max_date": total_in_db["timestamp"].max().strftime("%Y-%m-%d %H:%M"),
                        "source": source_used,
                        "status": "Sin datos nuevos (no confirma que esté al día)",
                    })
                    db.record_data_notice(symbol, tf, "empty_response", "La fuente no devolvió datos nuevos; se conserva el último dato y no se confirma una actualización.")
                else:
                    results.append({
                        "symbol": symbol,
                        "tf": tf,
                        "count": 0,
                        "min_date": "-",
                        "max_date": "-",
                        "source": source_used,
                        "status": "Sin datos disponibles",
                    })
                continue

            # Determinar fuente usada
            source_used = getattr(adapter, "source_used", {}).get(symbol, adapter.name)

            # Guardar en base de datos
            saved_count = db.save_candles(df, symbol=symbol, timeframe=tf, source=source_used)

            # Consultar estado final en BD
            total_in_db = db.load_candles(symbol, tf)
            db.resolve_data_notices(symbol, tf, ["gap"])
            for notice in recent_gaps(total_in_db.tail(1000), symbol, tf, source_used):
                db.record_data_notice(symbol, tf, notice["kind"], notice["message"])
                logger.warning(f"   ⚠️ {notice['message']}")
            results.append({
                "symbol": symbol,
                "tf": tf,
                "count": len(total_in_db),
                "min_date": total_in_db["timestamp"].min().strftime("%Y-%m-%d %H:%M"),
                "max_date": total_in_db["timestamp"].max().strftime("%Y-%m-%d %H:%M"),
                "source": source_used,
                "status": f"{'PARCIAL' if any(n['kind'] == 'download_limit' for n in notices) else 'OK'} ({len(df)} velas recibidas; pueden incluir correcciones)",
            })

        except Exception as e:
            for notice in getattr(adapter, "fetch_notices", {}).get((symbol, tf), []):
                db.record_data_notice(symbol, tf, notice["kind"], notice["message"])
            db.record_data_notice(symbol, tf, "download_error", f"Falló la descarga: {str(e)}")
            results.append({
                "symbol": symbol,
                "tf": tf,
                "count": 0,
                "min_date": "-",
                "max_date": "-",
                "source": adapter.name,
                "status": f"ERROR: {str(e)[:45]}",
            })

    return results


def update_fred_section(
    fred_adapter: FredAdapter,
    db: DatabaseManager,
    series_list: List[str],
) -> List[Dict[str, Any]]:
    """Descarga y guarda series macroeconómicas de FRED de forma incremental."""
    results = []
    for s_id in series_list:
        try:
            last_ts = db.get_latest_fred_timestamp(s_id)
            df = fred_adapter.fetch_series(s_id, since=last_ts)

            if df is None or df.empty:
                total_in_db = db.load_fred_series(s_id)
                if not total_in_db.empty:
                    results.append({
                        "symbol": s_id,
                        "tf": "1D",
                        "count": len(total_in_db),
                        "min_date": total_in_db["timestamp"].min().strftime("%Y-%m-%d"),
                        "max_date": total_in_db["timestamp"].max().strftime("%Y-%m-%d"),
                        "source": "fred",
                        "status": "Al día (0 nuevas)",
                    })
                else:
                    results.append({
                        "symbol": s_id,
                        "tf": "1D",
                        "count": 0,
                        "min_date": "-",
                        "max_date": "-",
                        "source": "fred",
                        "status": "Sin datos",
                    })
                continue

            db.save_fred_series(df, series_id=s_id)
            db.resolve_data_notices(s_id, "1D", ["download_error"])
            total_in_db = db.load_fred_series(s_id)
            results.append({
                "symbol": s_id,
                "tf": "1D",
                "count": len(total_in_db),
                "min_date": total_in_db["timestamp"].min().strftime("%Y-%m-%d"),
                "max_date": total_in_db["timestamp"].max().strftime("%Y-%m-%d"),
                "source": "fred",
                "status": f"OK (+{len(df)} nuevas)",
            })

        except Exception as e:
            db.record_data_notice(s_id, "1D", "download_error", f"Falló la descarga de FRED: {e}")
            results.append({
                "symbol": s_id,
                "tf": "1D",
                "count": 0,
                "min_date": "-",
                "max_date": "-",
                "source": "fred",
                "status": f"ERROR: {str(e)[:45]}",
            })
    return results


def print_summary_table(results: List[Dict[str, Any]]):
    """Imprime una tabla de resumen prolija en consola en español."""
    print("\n" + "=" * 95)
    print(f"{'ACTIVO':<12} | {'TF':<4} | {'VELAS':<7} | {'DESDE (UTC)':<16} | {'HASTA (UTC)':<16} | {'FUENTE':<10} | {'ESTADO'}")
    print("-" * 95)

    errores = 0
    total_velas = 0

    for r in results:
        status = r["status"]
        if "ERROR" in status:
            errores += 1
        total_velas += r["count"]
        print(
            f"{r['symbol']:<12} | {r['tf']:<4} | {r['count']:<7} | {r['min_date']:<16} | {r['max_date']:<16} | {r['source']:<10} | {status}"
        )

    print("=" * 95)
    print(f"Resumen de actualización:")
    print(f" • Activos procesados: {len(results)}")
    print(f" • Velas/Registros totales en BD: {total_velas:,}")
    if errores == 0:
        print(" • Estado general: ✅ Todas las fuentes actualizaron sin errores fatales.\n")
    else:
        print(f" • Estado general: ⚠️  Se registraron {errores} alertas o errores.\n")


def main():
    parser = argparse.ArgumentParser(description="Actualizador de datos de dashboard-finance")
    parser.add_argument(
        "--seccion",
        type=str,
        default=None,
        help="Sección a actualizar (ej: indices, metales, equity, smallcaps, cripto, argentina, referencias)",
    )
    parser.add_argument(
        "--tf",
        type=str,
        default="1m,5m,15m,1h,4h,1D",
        help="Temporalidades separadas por coma (ej: 1h,1D o 1m,5m,15m,1h,4h,1D). Por defecto: 1m,5m,15m,1h,4h,1D",
    )
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="Base de datos (también permite trabajar sobre una copia de prueba)")
    args = parser.parse_args()

    # Parsear temporalidades
    timeframes = [t.strip() for t in args.tf.split(",") if t.strip()]
    for t in timeframes:
        if t not in ["1m", "5m", "15m", "1h", "4h", "1D"]:
            print(f"❌ Error: Temporalidad '{t}' no es válida. Opciones válidas: 1m, 5m, 15m, 1h, 4h, 1D")
            sys.exit(1)

    # Cargar configuración
    try:
        config = load_config()
    except Exception as e:
        print(f"❌ Error cargando configuración: {e}")
        sys.exit(1)

    # Proteger la base existente antes de descargas y migraciones.
    if os.path.exists(args.db):
        try:
            ops = load_config(str(ROOT / "config/operations.yaml"))["backups"]
            backup = ensure_daily_backup(args.db, ROOT / ops["directory"],
                        retention={k: ops[k] for k in ("daily", "weekly", "monthly")},
                        compression_level=ops["compression_level"])
            if backup:
                print(f"✅ Copia automática previa: {backup['archive']}")
        except Exception as exc:
            print(f"❌ No se actualizó la base porque falló su respaldo: {exc}")
            return 1
    # Inicializar Base de Datos
    db = DatabaseManager(args.db)

    # Inicializar adaptadores
    yahoo_adapter = YahooAdapter()
    crypto_adapter = CryptoAdapter()
    fred_adapter = None
    try:
        fred_adapter = FredAdapter()
    except Exception as e:
        logger.warning(f"Aviso: FRED no inicializado ({e})")

    # Filtrar secciones a ejecutar
    secciones_a_correr = [args.seccion] if args.seccion else list(config.keys())

    all_results = []

    print("\n" + "=" * 60)
    print(f"🚀 INICIANDO ACTUALIZACIÓN DEL MOTOR DE DATOS")
    print(f"   Secciones: {', '.join(secciones_a_correr)}")
    print(f"   Temporalidades: {', '.join(timeframes)}")
    print("=" * 60)

    for sec in secciones_a_correr:
        if sec not in config:
            print(f"⚠️  Sección '{sec}' no existe en config/assets.yaml. Se omite.")
            continue

        sec_cfg = config[sec]
        fuente = sec_cfg.get("fuente")
        activos = sec_cfg.get("activos", [])

        print(f"\n📂 Procesando sección: [{sec.upper()}] ({len(activos)} activos vía {fuente})...")

        if fuente == "fred":
            if not fred_adapter:
                print("   ⚠️  FRED_API_KEY no configurada. Omitiendo referencias FRED.")
                all_results.append({"symbol": "FRED", "tf": "1D", "count": 0,
                    "min_date": "-", "max_date": "-", "source": "fred", "status": "ERROR: FRED no inicializado"})
                continue
            res = update_fred_section(fred_adapter, db, activos)
            all_results.extend(res)

        elif fuente == "yahoo":
            for sym in activos:
                print(f"   ⬇️  Descargando {sym}...", end="\r", flush=True)
                res = update_market_asset(yahoo_adapter, db, sym, timeframes)
                all_results.extend(res)
            print(f"   ✅ Sección {sec.upper()} completada.           ")

        elif fuente == "ccxt":
            for sym in activos:
                print(f"   ⬇️  Descargando {sym}...", end="\r", flush=True)
                res = update_market_asset(crypto_adapter, db, sym, timeframes)
                all_results.extend(res)
            print(f"   ✅ Sección {sec.upper()} completada.           ")

        else:
            print(f"   ⚠️  Fuente desconocida '{fuente}' para sección {sec}.")

    # Imprimir tabla resumen final
    print_summary_table(all_results)
    return 1 if any(r["status"].startswith(("ERROR", "PARCIAL")) for r in all_results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
