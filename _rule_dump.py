"""AppTest: cambios de regla explícitos y contenido ajeno a cointegración."""
import json
import os
from pathlib import Path
import sys

from _regdump import dump_tab, payload


def without_cointegration(tab):
    output = []

    def walk(node, scopes):
        for child in getattr(node, "children", {}).values():
            scope = scopes + [child.label] if child.type == "expander" else scopes
            if scope and scope[0].startswith("Relaciones entre "):
                continue
            content = payload(child)
            if child.type == "json" and scope == ["Fuentes, fechas, parámetros y calidad de los datos"]:
                # Argentina no tiene cointegración; no inventar la clave.
                if isinstance(content.get("lectura piloto", {}).get("cointegration"), dict):
                    content["lectura piloto"]["cointegration"].pop("binomial_gate", None)
                    content["lectura piloto"]["cointegration"].pop("all_block_statistics", None)
            output.append({"type": child.type, "content": content})
            walk(child, scope)

    walk(tab, [])
    return output


def run(destination, old_rule=False):
    from streamlit.testing.v1 import AppTest
    from testing_clock import monotonic_apptest_wait, fixed_regression_time
    monotonic_apptest_wait()
    fixed_regression_time()
    import app.indices as pilot
    from src.data.backup import ROOT
    if old_rule:
        original = pilot.configs

        def configs(section="indices"):
            values = original(section)
            if isinstance(values[2].get("cointegration"), dict):
                values[2]["cointegration"].pop("binomial_gate", None)
                if section in ("indices", "metales"):
                    values[2]["cointegration"].pop("all_block_statistics", None)
            return values

        pilot.configs = configs
    app = AppTest.from_file(str(ROOT / "app/main.py"), default_timeout=1800)
    all_nodes, other_nodes = {}, {}

    def capture(state):
        if app.exception or len(app.tabs) != 6:
            raise AssertionError([e.value for e in app.exception])
        for index, section in ((0, "indices"), (1, "metales"), (4, "cripto"), (2, "equity")):
            all_nodes[f"{state}/{section}"] = dump_tab(app.tabs[index])
            other_nodes[f"{state}/{section}"] = without_cointegration(app.tabs[index])

    app.run()
    capture("default")
    for section, key, pairs in [("indices", "pilot", 3), ("metales", "metales_pilot", 2), ("equity", "equity_pilot", 2)]:
        for pair in range(pairs):
            app.selectbox(key=key + "_pair").set_value(pair)
            app.button(key=key + "_load_pair").click().run()
            capture(f"{section}_pair_{pair}")
    for tf in ("1D", "1h", "4h"):
        for pair in range(3):
            app.selectbox(key="cripto_pilot_pair_tf").set_value(tf)
            app.selectbox(key="cripto_pilot_pair").set_value(pair)
            app.button(key="cripto_pilot_load_pair").click().run()
            capture(f"crypto_{tf}_{pair}")
    destination.write_text(json.dumps({"all": all_nodes, "non_cointegration": other_nodes}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    run(Path(sys.argv[1]), "--old-rule" in sys.argv[2:])
