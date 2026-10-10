"""AppTest: estados completos de Índices y Metales antes/después de Cripto."""
import json
import os
from pathlib import Path
import sys

from _regdump import dump_tab


def run(repo, destination):
    os.chdir(repo)
    sys.path.insert(0, str(repo))
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(repo / "app/main.py"), default_timeout=1200)
    readings = {}

    def capture(name):
        if app.exception:
            raise AssertionError([e.value for e in app.exception])
        if len(app.tabs) != 6:
            raise AssertionError("No se mostraron las seis pestañas")
        for index, section in [(0, "indices"), (1, "metales")]:
            readings[f"{name}/{section}"] = dump_tab(app.tabs[index])

    app.run()
    capture("default")
    for pair in (0, 1):
        app.selectbox(key="metales_pilot_pair").set_value(pair)
        app.button(key="metales_pilot_load_pair").click().run()
        capture(f"metal_pair_{pair}")
    app.selectbox(key="metales_pilot_tf").set_value("15m").run()
    capture("gold_15m")
    app.selectbox(key="metales_pilot_tf").set_value("4h").run()
    capture("gold_4h")
    app.selectbox(key="metales_pilot_asset").set_value("PL=F").run()
    capture("platinum_daily")
    app.selectbox(key="pilot_pair").set_value(0)
    app.button(key="pilot_load_pair").click().run()
    capture("index_pair")
    for tf in ("1h", "4h"):
        app.selectbox(key="pilot_tf").set_value(tf).run()
        capture(f"index_{tf}")
    destination.write_text(json.dumps(readings, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(f"{repo.name}: {len(readings)} estados de pestaña; {sum(len(v) for v in readings.values())} elementos", flush=True)


if __name__ == "__main__":
    run(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
