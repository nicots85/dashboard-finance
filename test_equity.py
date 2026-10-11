"""Equity: mismo período sectorial, sesión NY, fotos y lectura AppTest."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from _regdump import normalize
from src.data.backup import ROOT, snapshot_database
from src.data.db_manager import DEFAULT_DB_PATH, DatabaseManager
from src.data.snapshots import list_photos, take_snapshot, get_photo, SCHEMA_VERSION
from src.equity_math import regular_stock_bars, equity_indicators
from src.indices_math import daily_means, session_vwap
from test_crypto import live_tab, pair_state


def bars(times, values, source="yahoo"):
    return pd.DataFrame({"timestamp": pd.to_datetime(times, utc=True), "open": values, "high": values,
                         "low": values, "close": values, "volume": 10., "source": source})


class EquityTests(unittest.TestCase):
    def test_premarket_and_after_close_are_not_part_of_vwap(self):
        raw = bars(["2026-10-02 13:25Z", "2026-10-02 13:30Z", "2026-10-02 19:55Z", "2026-10-02 20:00Z"],
                   [1000., 10., 20., 999.])
        rth = regular_stock_bars(raw, "XLK", "5m", "2026-10-03")
        self.assertEqual(rth.close.tolist(), [10., 20.])
        self.assertEqual(session_vwap(rth).vwap.iloc[-1], 15.)

    def test_session_four_hour_second_candle_is_shorter(self):
        raw = bars(["2026-10-02 11:00Z", "2026-10-02 13:30Z", "2026-10-02 17:30Z", "2026-10-02 20:00Z"],
                   [99., 10., 20., 99.], "session_4h_us")
        result = regular_stock_bars(raw, "XLK", "4h", "2026-10-03")
        self.assertEqual(result.close.tolist(), [10., 20.])
        self.assertEqual(((result.bar_end - result.timestamp).dt.total_seconds() / 60).tolist(), [240., 150.])

    def test_sector_comparison_uses_one_period_and_heatmap_order(self):
        days = pd.date_range("2026-01-01", periods=61).strftime("%Y-%m-%d")
        pilot = {"sectors": ["XLK", "XLE"], "mega_caps": ["AAPL"], "relative_strength_sessions": 20}
        daily, frames = {}, {}
        for symbol, values in [("XLK", np.linspace(100, 120, 61)), ("XLE", np.linspace(100, 90, 61)), ("AAPL", np.linspace(100, 110, 61))]:
            frame = pd.DataFrame({"timestamp": pd.to_datetime(days, utc=True), "session": days,
                                  "close": values, "closed": True})
            daily[symbol] = daily_means(frame)
            for tf in ["1m", "5m", "15m", "1h", "4h", "1D"]:
                frames[(symbol, tf)] = frame
        rows = [{"symbol": s, "direction": "bajista" if s == "XLE" else "alcista", "distance_pct": 1., "distance_std": 1.} for s in daily]
        benchmark = pd.Series(np.linspace(100, 110, 61), index=days)
        result = equity_indicators(rows, daily, frames, benchmark, pilot)
        k = result["kpis"]
        self.assertEqual((k["sector_up"], k["mega_up"]), (1, 1))
        self.assertEqual(k["leader"]["symbol"], "XLK")
        self.assertEqual(k["laggard"]["symbol"], "XLE")
        self.assertEqual(result["heatmap"].symbol.tolist(), ["XLK", "XLE"])
        self.assertAlmostEqual(k["leader"]["relative_pp"], ((120 / (100 + 40 / 3) - 1) - (110 / (100 + 20 / 3) - 1)) * 100)

    def test_six_tabs_equity_session_pairs_photos_and_current_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = str(Path(temporary) / "equity.db")
            snapshot_database(DEFAULT_DB_PATH, path)
            before = len(list_photos(path))
            reading = {"generated_at": pd.Timestamp.now(tz="UTC").isoformat()}
            with patch("src.data.db_manager.DEFAULT_DB_PATH", path), patch(
                "src.data.DatabaseManager", side_effect=lambda *a, **k: DatabaseManager(path)
            ):
                app = AppTest.from_file(str(ROOT / "app/main.py"), default_timeout=1800).run()

                def check():
                    self.assertFalse(app.exception, [e.value for e in app.exception])
                    self.assertEqual(len(app.tabs), 6)

                check()
                tab = app.tabs[2]
                reading["equity"] = live_tab(tab)
                labels = [m.label for m in tab.metric]
                for expected in ["Sectores que suben", "Sector líder frente al S&P 500", "Sector rezagado frente al S&P 500", "Fortaleza de las siete tecnológicas", "Mayor separación de la media"]:
                    self.assertIn(expected, labels)
                self.assertEqual(len(tab.dataframe[0].value), 18)
                self.assertEqual(len(tab.dataframe[0].value.columns), 5)
                heat = next(e for e in tab.get("plotly_chart") if e.key == "equity_pilot_sector_heatmap")
                self.assertEqual(len(json.loads(heat.proto.spec)["data"][0]["y"]), 11)
                reading["pairs"] = {}
                for pair in (0, 1):
                    app.selectbox(key="equity_pilot_pair").set_value(pair)
                    app.button(key="equity_pilot_load_pair").click().run()
                    check()
                    reading["pairs"][str(pair)] = pair_state(app.tabs[2])
                app.selectbox(key="equity_pilot_pair_tf").set_value("1h").run()
                check()
                self.assertTrue(any("Historia insuficiente" in e.value for e in app.tabs[2].info))
                for tf in ("15m", "1h", "4h"):
                    app.selectbox(key="equity_pilot_tf").set_value(tf).run()
                    check()
                    fig = next(e for e in app.tabs[2].get("plotly_chart") if e.key == "equity_pilot_price_chart")
                    figure = normalize(json.loads(fig.proto.spec))
                    candle = next(trace for trace in figure["data"] if trace["type"] == "candlestick")
                    times = pd.to_datetime(candle["x"], utc=True).tz_convert("America/New_York")
                    self.assertTrue(all(570 <= t.hour * 60 + t.minute < 960 for t in times))
                    self.assertTrue(any("VWAP" in trace.get("name", "") for trace in figure["data"]))
                    if tf == "4h":
                        self.assertTrue(all((t.hour, t.minute) in [(9, 30), (13, 30)] for t in times))
                        self.assertTrue(any("4h de sesión" in c.value for c in app.tabs[2].caption))
                    reading["detail_" + tf] = live_tab(app.tabs[2])
            self.assertEqual(len(list_photos(path)), before)
            photo = get_photo(take_snapshot(path, trigger="test_equity_fields"), path)
            self.assertEqual(photo["content"]["schema_version"], SCHEMA_VERSION)
            section = photo["content"]["sections"]["equity"]
            self.assertEqual(section["kpis"]["sector_total"], 11)
            self.assertEqual(section["kpis"]["mega_total"], 7)
            self.assertEqual(len(section["sector_heatmap"]), 11)
            self.assertFalse(section["regular_session"]["include_premarket"])
            target = os.environ.get("EQUITY_READING_OUTPUT")
            if target:
                Path(target).write_text(json.dumps(reading, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
                print("\nLectura Equity de esta corrida: " + reading["generated_at"], flush=True)
                for metric in reading["equity"]["metrics"][:8]:
                    print(f"- {metric['label']}: {metric['value']} · {metric['delta']}", flush=True)
                for caption in reading["equity"]["captions"]:
                    if caption.startswith(("Datos al:", "Fecha del dato:", "Rendimiento sectorial")):
                        print("- " + caption, flush=True)
                for row in reading["equity"]["summary"]:
                    print("- " + json.dumps(row, ensure_ascii=False), flush=True)
                for pair, value in reading["pairs"].items():
                    print(f"- Par {pair}: {value['state']}", flush=True)
                    for caption in value["captions"]:
                        print("- " + caption, flush=True)
                for tf in ("15m", "1h", "4h"):
                    for caption in reading["detail_" + tf]["captions"]:
                        if "VWAP de" in caption or "4h de sesión" in caption:
                            print(f"- Detalle {tf}: {caption}", flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
