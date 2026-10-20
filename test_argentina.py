"""Argentina: CCL implícito, dispersión, sesiones BYMA/NY y foto versionada."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from src.argentina_math import common_window, ccl_series, session_four_hour, dispersion, dispersion_persistente, evento_activo, dividendo_pct, marcas_evento, median_reading
from src.data.backup import ROOT, snapshot_database
from src.data.db_manager import DEFAULT_DB_PATH, DatabaseManager
from src.data.snapshots import list_photos, take_snapshot, get_photo, SCHEMA_VERSION
from testing_clock import monotonic_apptest_wait


def bars(index, closes, session=None):
    index = pd.to_datetime(index, utc=True)
    return pd.DataFrame({"timestamp": index, "open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": 100., "session": session or index.strftime("%Y-%m-%d"),
                         "bar_end": index + pd.Timedelta(minutes=15), "closed": True})


BYMA = {"calendar": "XBUE", "timezone": "America/Argentina/Buenos_Aires", "open": "11:00", "close": "17:00",
        "four_hour": ["11:00-15:00", "15:00-17:00"], "label": "BYMA"}
NYSE = {"calendar": "NYSE", "timezone": "America/New_York", "open": "09:30", "close": "16:00",
        "four_hour": ["09:30-13:30", "13:30-16:00"], "label": "NYSE"}


class ArgentinaMathTests(unittest.TestCase):
    def test_ccl_is_local_times_ratio_over_adr(self):
        local = bars(["2026-10-09"], [1000.0])
        adr = bars(["2026-10-09"], [25.0])
        self.assertAlmostEqual(float(ccl_series(local, adr, 10).iloc[-1]), 400.0)
        self.assertAlmostEqual(float(ccl_series(local, adr, 1).iloc[-1]), 40.0)

    def test_ccl_needs_the_same_session_or_timestamp(self):
        local = bars(["2026-10-08", "2026-10-09"], [1000.0, 1010.0])
        adr = bars(["2026-10-09"], [25.0])
        self.assertEqual([str(d) for d in ccl_series(local, adr, 10).index], ["2026-10-09"])

    def test_common_window_follows_real_dst(self):
        summer, summer_end = common_window(pd.Timestamp("2026-10-09 12:00", tz="UTC"), BYMA, NYSE)
        self.assertEqual(summer.strftime("%H:%M"), "14:00")
        self.assertEqual(summer_end.strftime("%H:%M"), "20:00")
        winter, winter_end = common_window(pd.Timestamp("2026-11-10 12:00", tz="UTC"), BYMA, NYSE)
        self.assertEqual(winter.strftime("%H:%M"), "14:30")
        self.assertEqual(winter_end.strftime("%H:%M"), "20:00")

    def test_session_four_hour_splits_byma_and_keeps_the_short_block(self):
        day = "2026-10-09"
        local_times = pd.date_range(f"{day} 14:00", f"{day} 20:00", freq="15min", tz="UTC")
        frame = bars(local_times, range(len(local_times)))
        result = session_four_hour(frame, BYMA, pd.Timestamp("2026-10-10 00:00", tz="UTC"))
        self.assertEqual([value.strftime("%H:%M") for value in result.timestamp], ["14:00", "18:00"])
        self.assertEqual([value.strftime("%H:%M") for value in result.bar_end], ["18:00", "20:00"])
        self.assertEqual(result.iloc[1].volume, 8 * 100.)
        # 11:00–15:00 tiene 16 velas de quince minutos; 15:00–17:00 tiene 8.
        self.assertEqual(result.iloc[0].volume, 16 * 100.)

    def test_dispersion_highlights_only_beyond_the_threshold(self):
        frame = pd.DataFrame({"A": [100.0, 100.0], "B": [100.0, 105.0], "C": [100.0, 99.0]},
                             index=pd.to_datetime(["2026-10-08", "2026-10-09"]))
        rows = {row["company"]: row for row in dispersion(frame, 2.0)}
        self.assertTrue(rows["B"]["highlight"])
        self.assertFalse(rows["C"]["highlight"])
        self.assertFalse(rows["A"]["highlight"])
        self.assertAlmostEqual(rows["B"]["vs_median_pct"], 5.0, places=6)

    def test_persistent_dispersion_needs_three_of_last_five(self):
        # C supera 2% en las últimas tres ruedas; E en dos; el resto nunca
        # cambia. La mediana no se mueve (solo C se aparta, las demás quedan planas).
        plano = [100.0] * 7
        frame = pd.DataFrame({"C": [100.0] * 4 + [105.0, 105.0, 105.0],
                              "E": [100.0] * 5 + [105.0, 105.0],
                              "B": plano, "A": plano, "D": plano},
                             index=pd.date_range("2026-09-28", periods=7))
        flags = dispersion_persistente(frame, 2.0)
        self.assertTrue(flags["C"])
        self.assertFalse(flags["E"])
        self.assertFalse(flags["B"])
        self.assertFalse(flags["A"])

    def test_evento_window_covers_the_ex_date_and_last_wheel_counts(self):
        sesiones = pd.bdate_range("2026-09-03", "2026-09-25").date  # 17 ruedas
        self.assertTrue(evento_activo(sesiones, "2026-09-18", 8))    # 6 ruedas desde el ex-dividendo: adentro
        self.assertTrue(evento_activo(sesiones, "2026-09-18", 6))    # justo la sexta rueda: sigue adentro
        self.assertFalse(evento_activo(sesiones, "2026-09-18", 5))   # séptima rueda: fuera
        self.assertFalse(evento_activo(sesiones, "2026-09-03", 8))   # 17 ruedas: fuera
        self.assertFalse(evento_activo(sesiones, "2026-10-01", 8))   # ex-dividendo futuro: nada
        self.assertAlmostEqual(dividendo_pct(164.0, 2285.5), 164.0 / 2285.5 * 100)
        self.assertIsNone(dividendo_pct(0, 100))
        self.assertIsNone(dividendo_pct(None, None))

    def test_evento_marks_respect_threshold_and_window(self):
        index = pd.to_datetime(pd.date_range("2026-09-14", "2026-09-18", freq="B")).date
        cierres = pd.Series([2250.0, 2294.0, 2090.0, 2123.0, 2130.0], index=index)
        cepu = [{"tipo": "dividendo", "ex_date": "2026-09-18", "monto": 164.0}]   # 164/2294 ≈ 7.2%
        ggal = [{"tipo": "dividendo", "ex_date": "2026-09-15", "monto": 8.300841}]  # ≈ 0.14%: no marca
        marca = marcas_evento(cierres, cepu, pct_minimo=1.0, dias=8)
        self.assertIsNotNone(marca)
        self.assertEqual(marca["tipo"], "dividendo")
        self.assertGreater(marca["pct"], 1.0)
        self.assertIsNone(marcas_evento(cierres, ggal, pct_minimo=1.0, dias=8))
        # Con ventana de cero ruedas no hay marca.
        notas = marcas_evento(cierres, cepu, pct_minimo=1.0, dias=0)
        self.assertIsNone(notas)
        # Sin tabla de eventos (None): se omite silenciosamente.
        self.assertIsNone(marcas_evento(cierres, None, pct_minimo=1.0, dias=8))

    def test_median_change_uses_five_sessions(self):
        history = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0, 110.0],
                            index=pd.date_range("2026-10-01", periods=6))
        reading = median_reading(history)
        self.assertAlmostEqual(reading["change_5"], 10.0)
        self.assertTrue(reading["last_session"].startswith("2026-10-06"))


class ArgentinaAppTests(unittest.TestCase):
    def test_six_tabs_argentina_ccl_sessions_and_photo(self):
        monotonic_apptest_wait()
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "argentina.db")
            snapshot_database(DEFAULT_DB_PATH, db)
            count = len(list_photos(db))
            report = {"generated_at": pd.Timestamp.now(tz="UTC").isoformat()}
            with patch("src.data.db_manager.DEFAULT_DB_PATH", db), patch("src.data.DatabaseManager", side_effect=lambda *a, **k: DatabaseManager(db)):
                app = AppTest.from_file(str(ROOT / "app/main.py"), default_timeout=2400).run()
                self.assertFalse(app.exception, [e.value for e in app.exception])
                self.assertEqual(len(app.tabs), 6)
                tab = app.tabs[5]
                labels = [m.label for m in tab.metric]
                for title in ("CCL implícito mediano", "Distancia del CCL a su media", "Acciones locales que suben", "Mayor separación de la media"):
                    self.assertIn(title, labels)
                texts = " ".join([c.value for c in tab.caption] + [i.value for i in tab.info] + [d.value for d in tab.subheader])
                self.assertIn("tendencia", texts)
                self.assertIn("14:00", texts)
                table = [d for d in tab.dataframe if list(d.value.columns)[:1] == ["Empresa"]][0]
                self.assertEqual(len(table.value), 5)
                self.assertIn("YPF", " ".join(table.value["Empresa"]))
                self.assertTrue(any("BYMA" in c.value for c in tab.caption))
                self.assertTrue(any(e.label.startswith("Relaciones entre") for e in tab.expander))
                self.assertFalse(any(s.key == "argentina_pilot_pair" for s in tab.selectbox))
                self.assertFalse(any(s.key == "argentina_pilot_pair_tf" for s in tab.selectbox))
                self.assertTrue(any("no se usa cointegración" in i.value.lower() for i in tab.info) or
                                any("brecha" in c.value.lower() for c in tab.caption))
                report["metrics"] = [{"label": m.label, "value": m.value, "delta": m.delta} for m in tab.metric]
                report["ccl"] = table.value.to_dict("records")
                report["captions"] = [c.value for c in tab.caption]
                report["warnings"] = [w.value for w in tab.warning]
                app.selectbox(key="argentina_pilot_tf").set_value("15m").run()
                self.assertTrue(any("VWAP" in c.value or "sesión" in c.value.lower() for c in app.tabs[5].caption))
                app.selectbox(key="argentina_pilot_tf").set_value("4h").run()
                self.assertTrue(any("4h de sesión" in c.value for c in app.tabs[5].caption))
            self.assertEqual(len(list_photos(db)), count)
            photo = get_photo(take_snapshot(db, trigger="test_argentina"), db)
            self.assertEqual(photo["content"]["schema_version"], SCHEMA_VERSION)
            stored = photo["content"]["sections"]["argentina"]
            kpis = stored["kpis"]
            self.assertEqual(len(kpis["ccl_by_company"]), 5)
            self.assertIn("median", kpis["median"])
            self.assertIn("change_5", kpis["median"])
            self.assertIn("dispersion_reference", kpis)
            self.assertIn("BYMA", " ".join(stored["regular_sessions"]))
            self.assertTrue(all(not spec["include_premarket"] for spec in stored["regular_sessions"].values()))
            self.assertIn("four_hour", stored["regular_sessions"]["BYMA 11:00–17:00 Buenos Aires"])
            self.assertTrue(stored["ccl"]["by_company"])
            self.assertIsNotNone(stored["ccl"]["median"])
            target = os.environ.get("ARGENTINA_READING_OUTPUT")
            if target:
                Path(target).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))
                print("\nArgentina de esta corrida: " + report["generated_at"], flush=True)
                for row in report["ccl"]:
                    print(f"- {row['Empresa']}: {row['CCL implícito']} · {row['% vs mediana']} · {row['Estado']}", flush=True)
                for metric in report["metrics"][:4]:
                    print(f"- {metric['label']}: {metric['value']} · {metric['delta']}", flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)