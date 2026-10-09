"""C1: texto, nombres y ayudas en las seis pestañas, con una base temporal."""
import html
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
import yaml
from streamlit.testing.v1 import AppTest
from src.data.db_manager import DatabaseManager
from src.calc.regime import get_latest_market_regime
from src.calc.zscore import get_latest_zscore
from src.presentation import ROOT, catalog, asset_label, section_terms, column_specs, refresh_catalog


def without_html(text):
    return html.unescape(re.sub(r"<[^>]*>", "", str(text)))


class TextCatalogTests(unittest.TestCase):
    def test_every_asset_has_name_and_definition(self):
        assets, glossary, _, names = refresh_catalog()
        for section, config in assets.items():
            self.assertEqual(set(config["activos"]), set(config["nombres"]), section)
            for symbol in config["activos"]:
                self.assertTrue(config["nombres"][symbol].strip())
                self.assertTrue(glossary["terminos"][symbol].strip())
                self.assertNotEqual(asset_label(symbol), symbol)

    def test_requested_terms_and_regime_labels_exist(self):
        required = ["ADR", "CCL", "ATR", "ADX", "EMA", "VWAP", "z-score", "p-valor", "beta",
                    "vida media", "cointegración", "régimen", "alineación", "tasa real", "curva de tasas",
                    "VIX", "spread high yield", "ETF", "futuro", "alcista", "bajista", "lateral",
                    "alcista (débil)", "bajista (débil)", "sin datos", "baja vol", "normal vol", "alta vol"]
        for term in required:
            self.assertTrue(catalog()[1]["terminos"][term].strip(), term)

    def test_missing_column_help_is_rejected(self):
        with self.assertRaises(KeyError):
            column_specs(["Columna sin explicación"])

    def test_section_glossaries_have_only_defined_terms_and_are_sorted(self):
        import unicodedata
        for section in catalog()[1]["secciones"]:
            terms = section_terms(section)
            labels = [asset_label(t) if t in catalog()[3] else t for t in terms]
            normalized = [unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().casefold() for s in labels]
            self.assertEqual(normalized, sorted(normalized))
            for term in terms:
                self.assertIn(term, catalog()[1]["terminos"])


class SixTabsTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.tmp.name) / "text_test.db"
        db = DatabaseManager(cls.db_path)
        cfg = yaml.safe_load((ROOT / "config/calc.yaml").read_text(encoding="utf-8"))
        assets, _, pairs, _ = catalog()
        rng = np.random.default_rng(21)
        prices = 100 + np.cumsum(rng.normal(0, .2, 80))
        for section, info in assets.items():
            if section == "referencias":
                continue
            for index, symbol in enumerate(info["activos"]):
                for tf, freq in {"1m": "min", "5m": "5min", "15m": "15min", "1h": "h", "4h": "4h", "1D": "D"}.items():
                    df = pd.DataFrame({"timestamp": pd.date_range("2025-01-01", periods=80, freq=freq, tz="UTC"),
                                       "open": prices + index, "high": prices + index + 1, "low": prices + index - 1,
                                       "close": prices + index, "volume": 100.0})
                    db.save_candles(df, symbol, tf, "bybit" if symbol.startswith("HYPE") else "binance" if section == "cripto" else "yahoo")
                    saved = db.load_candles(symbol, tf)
                    inputs = [saved.attrs["data_version"]]
                    db.save_regime_result(symbol, tf, get_latest_market_regime(saved, cfg["regime"]), inputs, cfg["regime"])
                    db.save_zscore_result(symbol, tf, get_latest_zscore(saved, cfg["zscore"]), inputs, cfg["zscore"])
        for section, section_pairs in pairs.items():
            if section == "argentina":
                continue
            for pair in section_pairs:
                for tf in ["1h", "4h", "1D"]:
                    a, b = db.load_candles(pair["y"], tf), db.load_candles(pair["x"], tf)
                    result = {"timestamp": a.timestamp.iloc[-1], "p_value": .2, "beta": 1., "is_cointegrated": False,
                              "z_spread": .5, "half_life": 10., "pct_coint_windows": 0.}
                    db.save_cointegration_result(f"{pair['y']}/{pair['x']}", tf, result["timestamp"], result,
                        [a.attrs["data_version"], b.attrs["data_version"]], cfg["cointegration"])
        for symbol in assets["referencias"]["activos"]:
            fred = pd.DataFrame({"timestamp": pd.date_range("2025-01-01", periods=80, tz="UTC"), "value": np.linspace(1, 2, 80)})
            db.save_fred_series(fred, symbol)
            result = {"timestamp": fred.timestamp.iloc[-1], "current_value": 2., "change_1m": .1,
                      "pct_change_1m": 5., "percentile": 80.}
            db.save_macro_result(symbol, result, [db.load_fred_series(symbol).attrs["data_version"]], cfg["macro"])
        with patch("src.data.db_manager.DEFAULT_DB_PATH", str(cls.db_path)), patch("src.data.DatabaseManager", side_effect=lambda *a, **k: DatabaseManager(cls.db_path)):
            cls.app = AppTest.from_file(str(ROOT / "app/main.py"), default_timeout=300).run()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_six_tabs_have_no_exceptions_and_each_has_glossary(self):
        self.assertFalse(self.app.exception, [e.value for e in self.app.exception])
        self.assertEqual([t.label for t in self.app.tabs], ["Índices", "Metales", "Equity", "Small caps", "Cripto", "Argentina"])
        # Los pilotos de Índices y Metales conservan también su vista anterior.
        self.assertEqual(sum(e.label == "Glosario" for e in self.app.expander), 8)

    def test_every_rendered_column_and_metric_has_help(self):
        for element in self.app.dataframe:
            field = "columns" if "columns" in element.proto.DESCRIPTOR.fields_by_name else "column_config"
            settings = json.loads(getattr(element.proto, field))
            for column in element.value.columns:
                self.assertTrue(settings[column].get("help"), column)
            self.assertTrue(settings["_index"].get("help"))
        for metric in self.app.metric:
            self.assertTrue(metric.proto.help.strip(), metric.label)
        for selector in self.app.selectbox:
            self.assertTrue(selector.proto.help.strip(), selector.label)

    def test_symbols_are_not_displayed_alone(self):
        texts = []
        for table in self.app.dataframe:
            columns = [c for c in table.value.columns if not pd.api.types.is_numeric_dtype(table.value[c])]
            texts.extend(str(v) for v in table.value[columns].to_numpy().ravel())
        for selector in self.app.selectbox:
            texts.extend(selector.options)
        texts.extend(e.label for e in self.app.metric)
        texts.extend(e.value for e in self.app.markdown)
        texts.extend(e.value for e in self.app.caption)
        texts.extend(e.value for e in self.app.subheader)
        for element in self.app.get("plotly_chart"):
            spec = json.loads(element.proto.spec)
            texts.extend(str(a.get("text", "")) for a in spec["layout"].get("annotations", []))
            for trace in spec["data"]:
                if trace.get("type") == "heatmap":
                    texts.extend(trace["y"])
        labels = [asset_label(symbol) for symbol in catalog()[3]]
        labels.extend(asset_label(symbol, "4h") for symbol in catalog()[0]["indices"]["activos"])
        for text in texts:
            plain = without_html(text)
            explained = {symbol for symbol in catalog()[3] if asset_label(symbol) in plain}
            from src.data.four_hour import policy
            for symbol in catalog()[0]["indices"]["activos"]:
                if asset_label(symbol, "4h") in plain and policy(symbol) and policy(symbol)["method"] == "future_utc":
                    explained.add(policy(symbol)["reference"])
            for label in sorted(labels, key=len, reverse=True):
                plain = plain.replace(label, "")
            for symbol in catalog()[3]:
                if symbol in explained:
                    continue  # Puede repetirse el rótulo «VWAP de NQ=F» junto al nombre completo.
                self.assertIsNone(re.search(r"(?<![\w^])" + re.escape(symbol) + r"(?!\w)", plain), f"Símbolo sin nombre: {symbol} en {text}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
