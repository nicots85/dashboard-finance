"""Cripto: sesión UTC, exchange única, cobertura real y lectura AppTest."""
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import yaml
from streamlit.testing.v1 import AppTest

from _regdump import normalize
from src.data.backup import ROOT, snapshot_database
from src.data.db_manager import DEFAULT_DB_PATH, DatabaseManager
from src.data.snapshots import list_photos
from src.indices_math import prepare_bars, session_vwap, freshness, unexpected_gaps, pair_analysis
from src.pilot_math import select_exchange, crypto_vwap_readings, pair_coverage, ratio_reading


def candles(times, prices, source="binance"):
    return pd.DataFrame({"timestamp": pd.to_datetime(times, utc=True), "open": prices,
                         "high": prices, "low": prices, "close": prices, "volume": 10., "source": source})


def live_tab(tab):
    return {"metrics": [{"label": m.label, "value": m.value, "delta": m.delta} for m in tab.metric],
            "captions": [c.value for c in tab.caption], "warnings": [w.value for w in tab.warning],
            "summary": tab.dataframe[0].value.to_dict("records"),
            "charts": [{"key": e.key, "figure": normalize(json.loads(e.proto.spec))} for e in tab.get("plotly_chart")]}


def pair_state(tab):
    state = next(e.value for e in tab.markdown if e.value.startswith("**Estado:"))
    tests = []
    for element in tab.json:
        value = json.loads(element.value) if isinstance(element.value, str) else element.value
        if "ventana_principal" in value:
            tests.append(value)
    return {"state": state, "tests": tests,
            "captions": [c.value for c in tab.caption if "bloques" in c.value.lower() or "Bloques sin solape" in c.value]}


def print_live_reading(reading):
    print("\nLectura AppTest de esta corrida: " + reading["generated_at"], flush=True)
    for section in ("metales", "cripto"):
        metrics = reading[section]["metrics"]
        seen = set()
        allowed = {"Dirección", "Más alineado", "Más fuerte entre metales", "Más alejado", "ETH/BTC", "SOL/BTC",
                   "Mayor separación del VWAP", "Ratio Oro / Plata", "Distancia a la media del ratio", "Distancia por desvío del ratio",
                   "Ratio ETH/BTC", "Ratio SOL/BTC", "Percentil de ETH/BTC", "Percentil de SOL/BTC"}
        for metric in metrics:
            is_macro = any(f"({symbol})" in metric["label"] for symbol in ("DGS10", "DFII10", "DTWEXBGS", "VIXCLS"))
            if (metric["label"] in allowed or is_macro) and metric["label"] not in seen:
                seen.add(metric["label"])
                print(f"- {section}: {metric['label']} = {metric['value']} · {metric['delta']}", flush=True)
        if section == "cripto":
            ratio_label = None
            for metric in metrics:
                if metric["label"] in ("Ratio ETH/BTC", "Ratio SOL/BTC"):
                    ratio_label = metric["label"].removeprefix("Ratio ")
                elif ratio_label and metric["label"] in ("Distancia a la media del ratio", "Distancia por desvío del ratio"):
                    print(f"- {ratio_label}: {metric['label']} = {metric['value']}", flush=True)
        for caption in reading[section]["captions"]:
            if caption.startswith(("Datos al:", "Período común de los cuatro:", "Comparación de rendimientos", "VWAP comparado de la sesión", "Fecha del dato:")):
                print("- " + section + ": " + caption, flush=True)
    between = next(c for c in reading["metales"]["charts"] if c["key"] == "metales_pilot_between_assets")["figure"]["data"][0]
    for label, value in zip(between["y"], between["x"]):
        print(f"- Rendimiento entre metales: {label} = {value:+.4f}%", flush=True)
    gold = next(c for c in reading["gold_15m"]["charts"] if c["key"] == "metales_pilot_price_chart")["figure"]["data"]
    price = next(t for t in gold if t["type"] == "candlestick")
    vw = next(t for t in gold if t.get("name", "").startswith("VWAP"))
    vwap_value = f"{vw['y'][-1]:.4f}" if vw["y"][-1] is not None else "no disponible"
    print(f"- Oro 15m: última vela {price['x'][-1]} · cierre {price['close'][-1]:.4f} · VWAP {vwap_value}", flush=True)
    print(f"- Oro 15m OHLC: {price['open'][-1]:.4f} / {price['high'][-1]:.4f} / {price['low'][-1]:.4f} / {price['close'][-1]:.4f}", flush=True)
    upper = next(t for t in gold if t.get("name") == "+1 desvío")
    if vw["y"][-1] is not None and upper["y"][-1] is not None:
        sigma = upper["y"][-1] - vw["y"][-1]
        bands = (price["close"][-1] - vw["y"][-1]) / sigma if sigma > 0 else None
        print(f"- Oro 15m: distancia {((price['close'][-1] / vw['y'][-1] - 1) * 100):+.4f}% · sigma {sigma:.4f} · bandas {bands}", flush=True)
    for caption in reading["gold_15m"]["captions"]:
        if caption.startswith(("VWAP de ", "Línea base larga", "Sesión de VWAP", "Diamante naranja")) or "velas visibles" in caption:
            print("- Oro 15m: " + caption, flush=True)
    for warning in reading["gold_15m"]["warnings"]:
        if "VWAP" in warning or "huecos" in warning:
            print("- Oro 15m: " + warning, flush=True)
    for key, pair in reading["metal_pairs"].items():
        print(f"- Metales par {key}: {pair['state']}", flush=True)
        for caption in pair["captions"]:
            print("- " + caption, flush=True)
    for key, pair in reading["crypto_pairs"].items():
        print(f"- Cripto par {key}: {pair['state']}", flush=True)
        for caption in pair["captions"]:
            if "cierres comunes" in caption or caption.startswith("Bloques sin solape"):
                print("- " + caption, flush=True)
    for row in reading["crypto_coverage"]:
        print(f"- Cobertura {row['Par']} · {row['Escala']}: {row['Cierres comunes']} cierres / {row['Bloques disponibles']} bloques / {row['Bloques requeridos']} requeridos", flush=True)


class CryptoTests(unittest.TestCase):
    def test_utc_reset_survives_dst_and_weekend(self):
        raw = candles(["2026-03-08 23:59Z", "2026-03-09 00:00Z", "2026-03-09 00:01Z"], [10., 20., 30.])
        bars = prepare_bars(raw, "BTC/USDT", "1m", "24/7", "2026-03-09 00:03Z")
        vw = session_vwap(bars)
        self.assertEqual(vw.vwap.tolist(), [10., 20., 25.])
        self.assertEqual(bars.session.tolist(), ["2026-03-08", "2026-03-09", "2026-03-09"])
        self.assertTrue(bars.closed.all())

    def test_source_change_is_not_blended_into_vwap(self):
        raw = candles(pd.date_range("2026-10-01", periods=3, freq="min", tz="UTC"), [1000., 10., 20.])
        raw["source"] = ["binance", "bybit", "bybit"]
        selected, info = select_exchange(raw, "binance")
        self.assertTrue(info["changed"])
        self.assertEqual(info["exchange"], "bybit")
        self.assertEqual(selected.source.unique().tolist(), ["bybit"])
        bars = prepare_bars(selected, "HYPE/USDT", "1m", "24/7", "2026-10-01 00:04Z")
        self.assertEqual(session_vwap(bars).vwap.iloc[-1], 15.)

    def test_latest_closed_vwap_at_midnight_belongs_to_previous_session(self):
        raw = candles(pd.date_range("2026-10-01", periods=1441, freq="min", tz="UTC"), [10.] * 1440 + [30.])
        previous = prepare_bars(raw, "BTC/USDT", "1m", "24/7", "2026-10-02 00:00Z")
        result = crypto_vwap_readings({("BTC/USDT", "1m"): previous}, ["BTC/USDT"])["BTC/USDT"]
        self.assertEqual(result["session"], "2026-10-01")
        self.assertTrue(result["usable"])
        current = prepare_bars(raw, "BTC/USDT", "1m", "24/7", "2026-10-02 00:01Z")
        result = crypto_vwap_readings({("BTC/USDT", "1m"): current}, ["BTC/USDT"])["BTC/USDT"]
        self.assertEqual(result["session"], "2026-10-02")
        self.assertEqual(result["vwap"], 30.)

    def test_vwap_compares_same_cutoff_and_excludes_partial_session(self):
        raw = candles(pd.date_range("2026-10-01", periods=3, freq="min", tz="UTC"), [10., 20., 30.])
        frames = {(symbol, "1m"): prepare_bars(raw, symbol, "1m", "24/7", "2026-10-01 00:04Z") for symbol in ("BTC/USDT", "ETH/USDT")}
        frames[("ETH/USDT", "1m")] = frames[("ETH/USDT", "1m")].iloc[:2]
        result = crypto_vwap_readings(frames, ["BTC/USDT", "ETH/USDT"])
        self.assertEqual(result["BTC/USDT"]["common_cutoff"], result["ETH/USDT"]["common_cutoff"])
        self.assertEqual(result["BTC/USDT"]["price"], 20.)
        self.assertAlmostEqual(result["BTC/USDT"]["distance_pct"], (20 / 15 - 1) * 100)
        frames[("BTC/USDT", "1m")] = frames[("BTC/USDT", "1m")].iloc[1:]
        self.assertFalse(crypto_vwap_readings(frames, ["BTC/USDT", "ETH/USDT"])["BTC/USDT"]["usable"])

    def test_24h_staleness_and_real_gaps_not_stock_market_breaks(self):
        raw = candles(pd.date_range("2026-12-25 22:00", periods=4, freq="h", tz="UTC"), [10., 11., 12., 13.])
        bars = prepare_bars(raw, "BTC/USDT", "1h", "24/7", "2026-12-27 04:00Z")
        self.assertTrue(freshness(bars, "1h", "24/7", "2026-12-27 04:00Z")["stale"])
        self.assertFalse(unexpected_gaps(bars, "1h", "24/7"))
        self.assertTrue(unexpected_gaps(bars.iloc[[0, 3]], "1h", "24/7"))

    def test_intraday_blocks_use_candles_and_do_not_relax_solana_rule(self):
        pilot = yaml.safe_load((ROOT / "config/sections.yaml").read_text())["cripto"]
        count = 2500
        frames = {}
        for symbol in ("BTC/USDT", "ETH/USDT"):
            for tf, freq in [("1D", "D"), ("1h", "h"), ("4h", "4h")]:
                raw = candles(pd.date_range("2018-01-01", periods=count, freq=freq, tz="UTC"), np.arange(count) + 100.)
                frame = prepare_bars(raw, symbol, tf, "24/7", "2030-01-01")
                frame.loc[frame.index[-1], "closed"] = False
                frames[(symbol, tf)] = frame
        coverage = pair_coverage(frames, [{"y": "BTC/USDT", "x": "ETH/USDT"}], pilot)
        self.assertTrue(all(c["bars"] == 2499 and c["blocks"] == 4 and not c["enough"] for c in coverage))
        self.assertEqual(pilot["cointegration"]["required_blocks"], 5)
        series = pd.Series(np.arange(2000) + 1.)
        result = pair_analysis(series, series, pilot["cointegration"])
        self.assertEqual(result["state"], "no calculable")
        self.assertEqual(result["blocks"], 4)

    def test_ratio_percentile_keeps_sign_and_uses_valid_history(self):
        days = pd.date_range("2026-01-01", periods=30).strftime("%Y-%m-%d")
        daily = {"ETH/USDT": pd.DataFrame({"session": days, "close": list(range(100, 129)) + [10.], "source": "binance"}),
                 "BTC/USDT": pd.DataFrame({"session": days, "close": 10., "source": "binance"})}
        fields, history = ratio_reading(daily, {"y": "ETH/USDT", "x": "BTC/USDT", "label": "ETH/BTC", "window": 3, "percentile_window": 20})
        self.assertLess(fields["distance_std"], 0)
        self.assertEqual(fields["percentile"], 5.)  # el último es el menor de 20 valores válidos
        self.assertTrue(history.percentile.iloc[:21].isna().all())

    def test_six_tabs_crypto_sources_ratios_pairs_and_live_reading(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = str(Path(temporary) / "app.db")
            snapshot_database(DEFAULT_DB_PATH, path)
            before = len(list_photos(path))
            reading = {"generated_at": pd.Timestamp.now(tz="UTC").isoformat()}
            with patch("src.data.db_manager.DEFAULT_DB_PATH", path), patch(
                "src.data.DatabaseManager", side_effect=lambda *a, **k: DatabaseManager(path)
            ):
                app = AppTest.from_file(str(ROOT / "app/main.py"), default_timeout=1200).run()

                def check():
                    self.assertFalse(app.exception, [e.value for e in app.exception])
                    self.assertEqual(len(app.tabs), 6)

                check()
                reading["metales"] = live_tab(app.tabs[1])
                reading["cripto"] = live_tab(app.tabs[4])
                labels = [m.label for m in app.tabs[4].metric]
                for expected in ("Dirección", "Más alineado", "ETH/BTC", "SOL/BTC", "Mayor separación del VWAP", "Percentil de ETH/BTC", "Percentil de SOL/BTC"):
                    self.assertIn(expected, labels)
                self.assertEqual(list(app.tabs[4].dataframe[0].value.columns), ["Activo", "Dirección", "Alineación", "Distancia", "Dato"])
                summary = app.tabs[4].dataframe[0].value
                self.assertTrue(summary.Activo.str.contains("Binance|Bybit").all())
                for pair in [0, 1]:
                    app.selectbox(key="metales_pilot_pair").set_value(pair)
                    app.button(key="metales_pilot_load_pair").click().run()
                    check()
                    reading.setdefault("metal_pairs", {})[str(pair)] = pair_state(app.tabs[1])
                app.selectbox(key="metales_pilot_tf").set_value("15m").run()
                check()
                reading["gold_15m"] = live_tab(app.tabs[1])
                reading["crypto_pairs"] = {}
                for tf in ("1D", "1h", "4h"):
                    for pair in (0, 1, 2):
                        app.selectbox(key="cripto_pilot_pair_tf").set_value(tf)
                        app.selectbox(key="cripto_pilot_pair").set_value(pair)
                        app.button(key="cripto_pilot_load_pair").click().run()
                        check()
                        reading["crypto_pairs"][f"{tf}_{pair}"] = pair_state(app.tabs[4])
                        if tf == "1D" and pair in (1, 2):
                            self.assertIn("no calculable", reading["crypto_pairs"][f"{tf}_{pair}"]["state"])
                # Cobertura de todos los pares, incluyendo los no calculables.
                reading["crypto_coverage"] = next(table.value.to_dict("records") for table in app.tabs[4].dataframe if "Bloques disponibles" in table.value.columns)
                app.selectbox(key="cripto_pilot_asset").set_value("HYPE/USDT").run()
                check()
                hype = next(e for e in app.tabs[4].get("plotly_chart") if e.key == "cripto_pilot_price_chart")
                figure = json.loads(hype.proto.spec)
                self.assertEqual(figure["layout"]["xaxis"]["type"], "date")
                self.assertNotIn("rangebreaks", figure["layout"]["xaxis"])
                self.assertTrue(any("Bybit" in t.get("name", "") for t in figure["data"]))
                self.assertTrue(any("00:00" in c.value and "UTC" in c.value for c in app.tabs[4].caption))
                with sqlite3.connect(path) as conn:
                    conn.execute("UPDATE candles SET source='okx' WHERE symbol='HYPE/USDT' AND timeframe='1m' AND timestamp=(SELECT MAX(timestamp) FROM candles WHERE symbol='HYPE/USDT' AND timeframe='1m')")
                app.session_state["data_signature"] = None
                app.run()
                check()
                self.assertTrue(any("Cambio de fuente" in w.value and "okx" in w.value for w in app.tabs[4].warning))
            self.assertEqual(len(list_photos(path)), before)
            destination = os.environ.get("PILOT_READING_OUTPUT")
            if destination:
                Path(destination).write_text(json.dumps(reading, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
                print_live_reading(reading)


if __name__ == "__main__":
    unittest.main(verbosity=2)
