"""Volcados AppTest de las tres pestañas anteriores a Equity."""
import json
import os
from pathlib import Path
import sys

from _regdump import dump_tab, payload


def unaffected_crypto(tab):
    """Solo excepciones explícitas de los ajustes pedidos de cointegración."""
    result = []

    def walk(node, ancestors):
        for child in getattr(node, "children", {}).values():
            scope = ancestors + [child.label] if child.type == "expander" else ancestors
            if scope and scope[0].startswith("Relaciones entre criptomonedas"):
                continue
            content = payload(child)
            if scope == ["Cómo leer esto"] and child.type == "markdown":
                continue
            if child.type == "json" and scope == ["Fuentes, fechas, parámetros y calidad de los datos"]:
                pilot = content["lectura piloto"]
                pilot.pop("limited_history", None)
                pilot.pop("reading_notes", None)
                pilot["cointegration"].pop("all_block_statistics", None)
                pilot.get("cointegration_by_tf", {}).get("1h", {}).pop("block_size", None)
            result.append({"type": child.type, "content": content})
            walk(child, scope)

    walk(tab, [])
    return result


def run(repo, destination):
    os.chdir(repo)
    sys.path.insert(0, str(repo))
    from streamlit.testing.v1 import AppTest
    from testing_clock import monotonic_apptest_wait
    monotonic_apptest_wait()
    app = AppTest.from_file(str(repo / "app/main.py"), default_timeout=2400)
    readings, unaffected = {}, {}

    def capture(state):
        if app.exception:
            raise AssertionError([e.value for e in app.exception])
        if len(app.tabs) != 6:
            raise AssertionError("No se mostraron seis pestañas")
        for index, section in ((0, "indices"), (1, "metales"), (4, "cripto")):
            readings[f"{state}/{section}"] = dump_tab(app.tabs[index])
        unaffected[state] = unaffected_crypto(app.tabs[4])

    app.run()
    capture("default")
    app.button(key="pilot_load_pair").click().run()
    capture("index_pair")
    app.button(key="metales_pilot_load_pair").click().run()
    capture("metal_pair")
    app.selectbox(key="metales_pilot_tf").set_value("15m").run()
    capture("gold_15m")
    for tf in ("1D", "1h", "4h"):
        for pair in (0, 1, 2):
            app.selectbox(key="cripto_pilot_pair_tf").set_value(tf)
            app.selectbox(key="cripto_pilot_pair").set_value(pair)
            app.button(key="cripto_pilot_load_pair").click().run()
            capture(f"crypto_{tf}_{pair}")
    destination.write_text(json.dumps({"readings": readings, "unaffected_crypto": unaffected},
                                     ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(f"{repo.name}: {sum(len(v) for v in readings.values())} elementos en {len(readings)} estados de pestaña", flush=True)


if __name__ == "__main__":
    run(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
