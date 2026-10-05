#!/usr/bin/env python3
"""
check_data.py — Auditoría y validación de calidad de datos en dashboard-finance.
Verifica:
 1. Ausencia de duplicados en la base de datos local.
 2. Detección de huecos sospechosos en series temporales.
 3. Últimos precios de cierre de control (^NDX, GC=F, BTC/USDT) para cotejar con plataforma.
 4. Alerta de activos con datos desactualizados (> 3 días para mercados activos o > 5 para fin de semana).
"""

import os
import sys
import json
from datetime import datetime, timezone
import pandas as pd
from src.data.db_manager import DatabaseManager
import yaml
from pathlib import Path
from src.data.audit import recent_gaps


def check_duplicates(db: DatabaseManager):
    """Verifica si existen duplicados para cualquier (symbol, timeframe, timestamp)."""
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT symbol, timeframe, timestamp, COUNT(*) as c
            FROM candles
            GROUP BY symbol, timeframe, timestamp
            HAVING c > 1;
            """
        )
        dups_candles = cursor.fetchall()

        cursor.execute(
            """
            SELECT series_id, timestamp, COUNT(*) as c
            FROM fred_series
            GROUP BY series_id, timestamp
            HAVING c > 1;
            """
        )
        dups_fred = cursor.fetchall()

    return dups_candles, dups_fred


def check_split_alerts(db: DatabaseManager):
    """Alerta de posibles splits: variación de cierre a cierre > 40% en 1D."""
    alertas = []
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT symbol FROM candles WHERE timeframe='1D'")
        for (sym,) in cursor.fetchall():
            cursor.execute(
                "SELECT timestamp, close FROM candles WHERE symbol=? AND timeframe='1D' ORDER BY timestamp DESC LIMIT 60",
                (sym,),
            )
            rows = list(reversed(cursor.fetchall()))  # cronológico: últimos 60 días
            for i in range(1, len(rows)):
                prev_ts, prev_c = rows[i - 1]
                ts, c = rows[i]
                if prev_c and prev_c > 0:
                    cambio = abs(c / prev_c - 1)
                    if cambio > 0.40:
                        alertas.append({"symbol": sym, "fecha": str(ts)[:10], "cambio": cambio * 100})
    return alertas


def check_control_prices(db: DatabaseManager):
    """Obtiene el último precio de cierre guardado para los tres activos de control."""
    control_assets = [
        ("^NDX", "Nasdaq 100"),
        ("GC=F", "Oro Futuros"),
        ("BTC/USDT", "Bitcoin / Tether"),
    ]

    results = []
    with db._get_connection() as conn:
        cursor = conn.cursor()
        for sym, nombre in control_assets:
            # Buscar el registro más reciente en cualquier temporalidad (preferentemente 1D o 1h)
            cursor.execute(
                """
                SELECT timeframe, timestamp, close, source
                FROM candles
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT 1;
                """,
                (sym,),
            )
            row = cursor.fetchone()
            if row:
                results.append({
                    "symbol": sym,
                    "nombre": nombre,
                    "tf": row[0],
                    "timestamp": row[1],
                    "close": row[2],
                    "source": row[3],
                })
            else:
                results.append({
                    "symbol": sym,
                    "nombre": nombre,
                    "tf": "-",
                    "timestamp": "-",
                    "close": None,
                    "source": "-",
                })
    return results


def check_outdated_assets(db: DatabaseManager, max_stale_days: int = 4):
    """Detecta activos cuyo último dato tenga una antigüedad superior a max_stale_days días."""
    now_utc = datetime.now(timezone.utc)
    outdated = []

    with db._get_connection() as conn:
        cursor = conn.cursor()
        # Velas
        cursor.execute(
            """
            SELECT symbol, timeframe, MAX(timestamp)
            FROM candles
            GROUP BY symbol, timeframe;
            """
        )
        for sym, tf, max_ts_str in cursor.fetchall():
            if max_ts_str:
                max_ts = pd.to_datetime(max_ts_str, utc=True)
                diff_days = (now_utc - max_ts).total_seconds() / 86400.0
                if diff_days > max_stale_days:
                    outdated.append({
                        "symbol": sym,
                        "tipo": f"Velas {tf}",
                        "ultimo_dato": max_ts_str,
                        "dias_retraso": round(diff_days, 1),
                    })

        # FRED
        cursor.execute(
            """
            SELECT series_id, MAX(timestamp)
            FROM fred_series
            GROUP BY series_id;
            """
        )
        for s_id, max_ts_str in cursor.fetchall():
            if max_ts_str:
                max_ts = pd.to_datetime(max_ts_str, utc=True)
                diff_days = (now_utc - max_ts).total_seconds() / 86400.0
                if diff_days > max_stale_days:
                    outdated.append({
                        "symbol": s_id,
                        "tipo": "FRED macro",
                        "ultimo_dato": max_ts_str,
                        "dias_retraso": round(diff_days, 1),
                    })

    return outdated


def main():
    print("\n" + "=" * 70)
    print("🔍 AUDITORÍA DE CALIDAD DE DATOS (check_data.py)")
    print("=" * 70)

    db = DatabaseManager()

    # 1. Chequeo de duplicados
    print("\n1️⃣  Verificación de registros duplicados:")
    dups_candles, dups_fred = check_duplicates(db)
    if not dups_candles and not dups_fred:
        print("   ✅ Excelente: 0 registros duplicados encontrados en la base de datos.")
    else:
        print(f"   ⚠️  Alerta: {len(dups_candles)} duplicados en velas, {len(dups_fred)} en FRED.")

    # 2. Precios de control
    print("\n2️⃣  Precios de control para comparar con tu plataforma:")
    print("   " + "-" * 66)
    print(f"   {'ACTIVO':<10} | {'DESCRIPCIÓN':<18} | {'ÚLTIMO CIERRE':<14} | {'FECHA (UTC)':<16}")
    print("   " + "-" * 66)

    control = check_control_prices(db)
    for c in control:
        if c["close"] is not None:
            cierre_str = f"{c['close']:,.2f}"
            ts_str = str(c["timestamp"])[:16]
            print(f"   {c['symbol']:<10} | {c['nombre']:<18} | {cierre_str:>14} | {ts_str:<16}")
        else:
            print(f"   {c['symbol']:<10} | {c['nombre']:<18} | {'(Sin datos)':>14} | {'-':<16}")
    print("   " + "-" * 66)

    # 3. Datos desactualizados
    print("\n3️⃣  Verificación de antigüedad de datos:")
    outdated = check_outdated_assets(db, max_stale_days=4)
    if not outdated:
        print("   ✅ Todos los activos cuentan con datos recientes (últimos 4 días).")
    else:
        print(f"   ℹ️  Se detectaron {len(outdated)} activos/series con datos de más de 4 días:")
        for o in outdated[:10]:
            print(f"      • {o['symbol']} ({o['tipo']}): último dato {o['ultimo_dato'][:10]} ({o['dias_retraso']} días)")
        if len(outdated) > 10:
            print(f"      ... y {len(outdated) - 10} más.")
        print("   (Nota: Si es lunes o fin de semana largo, los mercados tradicionales reportan el último cierre hábil).")

    # 3.b Alerta de posibles splits
    print("\n3️⃣b  Alerta de posibles splits (variación de cierre > 40% en 1D):")
    alertas = check_split_alerts(db)
    if not alertas:
        print("   ✅ Sin splits sospechosos en los últimos 60 días.")
    else:
        for a in alertas[:15]:
            print(f"   ⚠️  {a['symbol']} el {a['fecha']}: variación de {a['cambio']:.0f}% — posible split. Verificá el proveedor y ejecutá backup_data.py antes de corregir; no borres historia intradía que la fuente ya no ofrece.")
        if len(alertas) > 15:
            print(f"   ... y {len(alertas) - 15} más.")

    # 4. Resumen general de la base de datos
    print("\n4️⃣  Correcciones a velas terminadas y avisos de descarga:")
    with db._get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM candle_corrections").fetchone()[0]
        corrections = conn.execute("SELECT symbol,timeframe,timestamp,observed_at,changed_fields,old_values FROM candle_corrections ORDER BY id DESC LIMIT 10").fetchall()
    print(f"   Correcciones registradas desde C0: {count}")
    for sym, tf, ts, observed, fields, old_values in corrections:
        print(f"   • {sym} {tf} · vela {ts} · corregida {observed}: {fields}")
        if "_fecha_recepcion" in json.loads(old_values):
            print("     Recepción anterior a C0 no verificable: puede incluir una primera finalización, no necesariamente una corrección histórica.")
    with db._get_connection() as conn:
        series = conn.execute("SELECT DISTINCT symbol,timeframe FROM candles").fetchall()
        for sym, tf in series:
            recent = pd.read_sql_query("SELECT timestamp,source FROM candles WHERE symbol=? AND timeframe=? ORDER BY timestamp DESC LIMIT 1000", conn, params=(sym, tf))
            if not recent.empty:
                for notice in recent_gaps(recent, sym, tf, recent.source.iloc[0]):
                    db.record_data_notice(sym, tf, notice["kind"], notice["message"])
    for notice in db.get_data_notices():
        print(f"   ⚠️ {notice['asset']} {notice['timeframe']}: {notice['message']}")
    print("\n5️⃣  Resultados guardados frente a la versión actual de precios:")
    with open(Path(__file__).parent / "config/calc.yaml", encoding="utf-8") as file:
        calc_config = yaml.safe_load(file)
    pending = [r for r in db.get_calculation_health(calc_config) if r["status"] != "ok"]
    if not pending:
        print("   ✅ Cálculos comprobados: fechas, parámetros y versiones de precios coinciden.")
    for result in pending:
        print(f"   ⚠️ {result['asset']} {result['timeframe']} · cálculo {result['calculated_at']} · último dato usado {result['last_data_timestamp']}: {result['reason']}")
    stats = db.get_summary_stats()
    total_registros = sum(s["count"] for s in stats)
    print(f"\n📊 Total de series/activos en base local: {len(stats)} | Registros totales: {total_registros:,}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
