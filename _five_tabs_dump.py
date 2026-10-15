"""Regresión completa de cinco pestañas antes/después de Argentina."""
import json
import os
from pathlib import Path
import sys

from _regdump import dump_tab
from testing_clock import monotonic_apptest_wait, fixed_regression_time


def run(repo, destination):
    os.chdir(repo)
    sys.path.insert(0, str(repo))
    monotonic_apptest_wait()
    fixed_regression_time()
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(repo / "app/main.py"), default_timeout=2400)
    output = {}

    def capture(state):
        if app.exception or len(app.tabs) != 6:
            raise AssertionError([e.value for e in app.exception])
        for idx, section in ((0, "indices"), (1, "metales"), (4, "cripto"), (2, "equity"), (3, "smallcaps")):
            output[f"{state}/{section}"] = dump_tab(app.tabs[idx])

    app.run()
    capture("default")
    for prefix, pair_count in (("pilot", 3), ("metales_pilot", 2), ("equity_pilot", 2)):
        for pair in range(pair_count):
            app.selectbox(key=prefix + "_pair").set_value(pair)
            app.button(key=prefix + "_load_pair").click().run()
            capture(f"{prefix}_{pair}")
    for tf in ("1D", "1h", "4h"):
        for pair in range(3):
            app.selectbox(key="cripto_pilot_pair_tf").set_value(tf)
            app.selectbox(key="cripto_pilot_pair").set_value(pair)
            app.button(key="cripto_pilot_load_pair").click().run()
            capture(f"crypto_{tf}_{pair}")
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
