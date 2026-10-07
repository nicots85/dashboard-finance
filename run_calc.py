#!/usr/bin/env python3
"""
run_calc.py — Motor de ejecución de cálculos cuantitativos para dashboard-finance.
Lee parámetros de config/calc.yaml y config/pairs.yaml.
Calcula y almacena en SQLite:
  - Régimen de mercado (dirección + volatilidad)
  - Semáforo multi-temporalidad (1m a 1D)
  - Z-Score normalizado por ATR y desvío estándar (|z| > 2)
  - Cointegración de pares (1h, 4h, 1D) con estabilidad histórica
  - Referencias macroeconómicas de FRED (nivel, cambio 1M, percentil 10A)
Imprime en consola una tabla resumen en español por sección.

Uso:
  python run_calc.py                        # Calcula todo
  python run_calc.py --seccion cripto       # Solo cripto
  python run_calc.py --tf 1D                # Solo diario
"""

import sys
import os
import argparse
import yaml
import pandas as pd
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

from src.data import DatabaseManager
from src.data.db_manager import DEFAULT_DB_PATH
from src.data.four_hour import market_results, prepare_stored, label as four_hour_label
from src.calc import (
    get_latest_market_regime,
    compute_multi_timeframe_trends,
    get_latest_zscore,
    evaluate_pair_cointegration,
    analyze_fred_series,
)


def load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Motor de cálculos de dashboard-finance")
    parser.add_argument(
        "--seccion",
        type=str,
        default=None,
        help="Sección a procesar (indices, metales, equity, smallcaps, cripto, argentina, referencias)",
    )
    parser.add_argument(
        "--tf",
        type=str,
        default="1m,5m,15m,1h,4h,1D",
        help="Temporalidades a procesar separadas por coma. Por defecto: 1m,5m,15m,1h,4h,1D",
    )
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="Base de datos (puede ser una copia de prueba)")
    args = parser.parse_args()

    # Cargar configuraciones
    assets_cfg = load_yaml("config/assets.yaml")
    calc_cfg = load_yaml("config/calc.yaml")
    pairs_cfg = load_yaml("config/pairs.yaml")

    target_tfs = [t.strip() for t in args.tf.split(",") if t.strip()]
    secciones_a_correr = [args.seccion] if args.seccion else list(assets_cfg.keys())

    db = DatabaseManager(args.db)

    print("\n" + "=" * 95)
    print("🧠 EJECUTANDO MOTOR DE CÁLCULOS CUANTITATIVOS (run_calc.py)")
    print(f"   Secciones: {', '.join(secciones_a_correr)}")
    print(f"   Temporalidades: {', '.join(target_tfs)}")
    print("=" * 95)

    resumen_activos = []
    resumen_pares = []
    resumen_macro = []
    fallos = []

    # -------------------------------------------------------------
    # 1. Procesar Secciones de Mercado
    # -------------------------------------------------------------
    for sec in secciones_a_correr:
        if sec not in assets_cfg:
            continue

        sec_data = assets_cfg[sec]
        fuente = sec_data.get("fuente")
        activos = sec_data.get("activos", [])

        if fuente == "fred":
            # Procesar Referencias Macro
            print(f"\n🏛️  Calculando Referencias Macro FRED [{sec.upper()}]...")
            for s_id in activos:
                try:
                    df_series = db.load_fred_series(s_id)
                    if df_series.empty:
                        fallos.append((s_id, "1D", "Sin datos en BD"))
                        continue
                    m_res = analyze_fred_series(
                        df_series,
                        change_days=calc_cfg["macro"].get("change_period_days", calc_cfg["macro"].get("change_days", 30)),
                        percentile_years=calc_cfg["macro"].get("percentile_window_years", 10),
                    )
                    db.save_macro_result(s_id, m_res, input_versions=[df_series.attrs["data_version"]], params=calc_cfg.get("macro", {}))
                    resumen_macro.append({
                        "series_id": s_id,
                        "valor": m_res["current_value"],
                        "cambio_1m": m_res["change_1m"],
                        "pct_1m": m_res["pct_change_1m"],
                        "percentil": m_res["percentile"],
                        "fecha": str(m_res["timestamp"])[:10] if m_res["timestamp"] else "-",
                    })
                except Exception as e:
                    fallos.append((s_id, "1D", f"Error macro: {str(e)[:40]}"))
                    db.record_data_notice(s_id, "1D", "calculation_error", f"Error macro: {e}")
            continue

        print(f"\n📊 Procesando Sección: [{sec.upper()}] ({len(activos)} activos)...")

        for sym in activos:
            # Cargar todas las temporalidades disponibles para el semáforo multi-tf
            dfs_by_tf = {}
            for tf in ["1m", "5m", "15m", "1h", "4h", "1D"]:
                df_loaded = db.load_candles(sym, tf)
                if tf == "4h":
                    df_loaded = prepare_stored(df_loaded, sym)
                    df_loaded = df_loaded[df_loaded.closed]
                if not df_loaded.empty:
                    dfs_by_tf[tf] = df_loaded

            # Calcular semáforo multi-temporalidad
            sem_data = compute_multi_timeframe_trends(sym, dfs_by_tf, regime_config=calc_cfg.get("regime"))
            # Cadena de semáforo visual: 1m 5m 15m 1h 4h 1D
            emoji_map = {"alcista": "🟢", "bajista": "🔴", "alcista (débil)": "🟩", "bajista (débil)": "🟥", "lateral": "⚪", "sin datos": "▫️"}
            sem_str = " ".join([f"{tf}:{emoji_map.get(sem_data['trends'][tf], '▫️')}" for tf in ["15m", "1h", "4h", "1D"]])

            for tf in target_tfs:
                df = dfs_by_tf.get(tf)
                if df is None or df.empty or len(df) < 20:
                    fallos.append((sym, tf, "Datos insuficientes (<20 velas)"))
                    continue

                try:
                    # Régimen
                    reg, z = market_results(df, calc_cfg) if tf == "4h" else (
                        get_latest_market_regime(df, config=calc_cfg.get("regime")), get_latest_zscore(df, config=calc_cfg.get("zscore")))
                    inputs = [df.attrs["data_version"], *df.attrs.get("four_hour_series", {}).get("inputs", [])]
                    if tf == "4h":
                        reg["series_version"] = df.attrs["four_hour_series"]["version"]
                        z["series_version"] = df.attrs["four_hour_series"]["version"]
                    db.save_regime_result(sym, tf, reg, input_versions=inputs, params=calc_cfg.get("regime", {}))

                    # Z-Score
                    db.save_zscore_result(sym, tf, z, input_versions=inputs, params=calc_cfg.get("zscore", {}))
                    if reg["direction"] == "sin datos" or z["z_atr"] is None:
                        fallos.append((sym, tf, "No calculable: falta historia para régimen o dispersión"))
                    else:
                        db.resolve_data_notices(sym, tf, ["calculation_error"])

                    z_str = f"{z['z_atr']:+.2f}" if z['z_atr'] is not None else "-"
                    if z["is_extreme"]:
                        z_str += " ⚠️"

                    resumen_activos.append({
                        "seccion": sec,
                        "symbol": four_hour_label(sym, tf) or sym,
                        "tf": tf,
                        "regime": reg["regime"],
                        "adx": f"{reg['adx']:.1f}" if reg['adx'] else "-",
                        "atr_pct": f"{reg['atr_percentile']:.0f}%" if reg['atr_percentile'] else "-",
                        "z_atr": z_str,
                        "semaforo": sem_str,
                    })

                except Exception as e:
                    fallos.append((sym, tf, f"Error cálculo: {str(e)[:40]}"))
                    db.record_data_notice(sym, tf, "calculation_error", f"Error de cálculo: {e}")

    # -------------------------------------------------------------
    # 2. Procesar Cointegración de Pares
    # -------------------------------------------------------------
    coint_allowed_tfs = [t for t in target_tfs if t in calc_cfg["cointegration"]["allowed_timeframes"]]
    print(f"\n🔗 Procesando Cointegración de Pares (en {', '.join(coint_allowed_tfs)})...")

    for sec in secciones_a_correr:
        if sec == "argentina":
            continue  # Local/ADR se analiza con CCL, no con cointegración.
        pares_seccion = pairs_cfg.get(sec, [])
        for p_info in pares_seccion:
            sym_y = p_info["y"]
            sym_x = p_info["x"]
            nombre = p_info.get("nombre", f"{sym_y}/{sym_x}")
            pair_key = f"{sym_y}/{sym_x}"

            for tf in coint_allowed_tfs:
                df_y = db.load_candles(sym_y, tf)
                df_x = db.load_candles(sym_x, tf)

                try:
                    c_res = evaluate_pair_cointegration(
                        df_y,
                        df_x,
                        window_size=calc_cfg["cointegration"].get("window_size", 250),
                        p_value_threshold=calc_cfg["cointegration"].get("p_value_threshold", 0.05),
                        rolling_windows_eval=calc_cfg["cointegration"].get("rolling_windows_eval", 20),
                    )

                    last_ts = c_res.get("timestamp")
                    if last_ts is None:
                        available = [d["timestamp"].max() for d in (df_y, df_x) if not d.empty]
                        last_ts = max(available) if available else pd.Timestamp.now(tz="UTC")
                    db.save_cointegration_result(pair_key, tf, last_ts, c_res,
                        input_versions=[df_y.attrs["data_version"], df_x.attrs["data_version"]], params=calc_cfg.get("cointegration", {}))
                    calculable = c_res["p_value"] is not None
                    if not calculable:
                        fallos.append((pair_key, tf, c_res.get("error_message", "No calculable")))
                    else:
                        db.resolve_data_notices(pair_key, tf, ["calculation_error"])

                    coint_str = "NO CALCULABLE" if not calculable else "✅ SÍ" if c_res["is_cointegrated"] else "❌ NO"
                    p_val_str = f"{c_res['p_value']:.4f}" if c_res['p_value'] is not None else "-"
                    beta_str = f"{c_res['beta']:.2f}" if c_res['beta'] is not None else "-"
                    z_spr_str = f"{c_res['z_spread']:+.2f}" if (c_res['z_spread'] is not None and c_res['is_cointegrated']) else "-"
                    hl_str = f"{c_res['half_life']:.1f} v" if c_res['half_life'] is not None else "-"

                    resumen_pares.append({
                        "seccion": sec,
                        "par": nombre,
                        "tf": tf,
                        "cointegrado": coint_str,
                        "p_valor": p_val_str,
                        "beta": beta_str,
                        "z_spread": z_spr_str,
                        "half_life": hl_str,
                        "estabilidad": f"{c_res['pct_coint_windows']:.0f}%",
                    })

                except Exception as e:
                    fallos.append((pair_key, tf, f"Error coint: {str(e)[:40]}"))
                    db.record_data_notice(pair_key, tf, "calculation_error", f"No calculable: {e}")

    # -------------------------------------------------------------
    # 3. Imprimir Tablas de Resumen Prolijas en Español
    # -------------------------------------------------------------
    print("\n" + "=" * 95)
    print("📈 TABLA RESUMEN: RÉGIMEN, Z-SCORE Y SEMÁFORO DE TENDENCIAS")
    print("-" * 95)
    print(f"{'SECCIÓN':<10} | {'ACTIVO':<10} | {'TF':<4} | {'RÉGIMEN DE MERCADO':<22} | {'ADX':<5} | {'Z-ATR':<8} | {'SEMÁFORO (15m·1h·4h·1D)'}")
    print("-" * 95)
    for r in resumen_activos:
        print(f"{r['seccion']:<10} | {r['symbol']:<10} | {r['tf']:<4} | {r['regime']:<22} | {r['adx']:<5} | {r['z_atr']:<8} | {r['semaforo']}")
    print("=" * 95)

    if resumen_pares:
        print("\n" + "=" * 95)
        print("🔗 TABLA RESUMEN: COINTEGRACIÓN Y ARBITRAJE ESTADÍSTICO DE PARES")
        print("-" * 95)
        print(f"{'PAR':<35} | {'TF':<4} | {'COINT?':<7} | {'P-VALOR':<8} | {'BETA':<6} | {'Z-SPREAD':<8} | {'HALF-LIFE':<10} | {'ESTABILIDAD'}")
        print("-" * 95)
        for p in resumen_pares:
            print(f"{p['par']:<35} | {p['tf']:<4} | {p['cointegrado']:<7} | {p['p_valor']:<8} | {p['beta']:<6} | {p['z_spread']:<8} | {p['half_life']:<10} | {p['estabilidad']}")
        print("=" * 95)

    if resumen_macro:
        print("\n" + "=" * 95)
        print("🏛️  TABLA RESUMEN: REFERENCIAS MACROECONÓMICAS (FRED)")
        print("-" * 95)
        print(f"{'SERIE':<14} | {'VALOR ACTUAL':<14} | {'CAMBIO 1 MES':<14} | {'CAMBIO %':<12} | {'PERCENTIL 10A':<14} | {'FECHA'}")
        print("-" * 95)
        for m in resumen_macro:
            print(f"{m['series_id']:<14} | {m['valor']:<14} | {m['cambio_1m']:<+14.2f} | {m['pct_1m']:<+11.1f}% | {m['percentil']:<13.1f}% | {m['fecha']}")
        print("=" * 95)

    # 4. Reporte de advertencias o fallos si los hubo
    if fallos:
        print("\nℹ️  Avisos de datos insuficientes o no disponibles:")
        for sym, tf, motivo in fallos[:10]:
            print(f"   • {sym} ({tf}): {motivo}")
        if len(fallos) > 10:
            print(f"   ... y {len(fallos) - 10} más.")
    else:
        print("\n✅ Todos los cálculos se completaron sin omisiones ni errores.")
    health = db.get_calculation_health(calc_cfg)
    stale = [r for r in health if r["status"] != "ok"]
    if stale:
        print(f"\n⚠️ {len(stale)} resultados requieren atención (precios cambiados, falta de trazabilidad o no calculables).")
    print("Cada resultado lleva fecha de cálculo, último dato usado, versión de precios y parámetros.")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
