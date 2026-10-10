"""Volcado fiel de Índices mediante AppTest; incluye TODOS los desplegables.

Se ejecuta en un proceso separado por versión para aislar módulos y cachés.
FINANCE_DB_PATH apunta a la misma copia SQLite en todas las versiones.
Solo se normalizan antigüedad y hora de cálculo. Los IDs de transporte de
Streamlit/Styler no son contenido visible y no se comparan.
"""
import base64
import json
import os
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd
from google.protobuf.json_format import MessageToDict


def normalize(value):
    if isinstance(value, dict):
        if "bdata" in value and "dtype" in value:
            arr = np.frombuffer(base64.b64decode(value["bdata"]), dtype=value["dtype"])
            if value.get("shape"):
                arr = arr.reshape(tuple(int(n) for n in value["shape"].split(",")))
            return normalize(arr.tolist())
        return {k: normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [normalize(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"Calculado: \d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}", "Calculado: <hora>", value)
        value = re.sub(r"\bFaltan \d+ ruedas\b", "Faltan <edad> ruedas", value)
        return re.sub(r"\bhace \d+ (?:días|dias|min|h|d)\b", "hace <edad>", value)
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.integer, np.bool_)):
        return value.item()
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return str(value)
    return value


def dataframe_dump(frame):
    return normalize({"columns": list(frame.columns), "index": list(frame.index),
                      "rows": frame.to_numpy().tolist()})


def payload(node):
    kind = node.type
    if kind == "dataframe":
        from streamlit.dataframe_util import convert_arrow_bytes_to_pandas_df
        out = {"data": dataframe_dump(node.value), "columns": json.loads(node.proto.columns or "{}"),
               "column_order": list(node.proto.column_order)}
        styler = node.proto.arrow_data.styler
        if styler.display_values:
            out["display"] = dataframe_dump(convert_arrow_bytes_to_pandas_df(styler.display_values))
        if styler.styles:
            out["styles"] = styler.styles.replace(styler.uuid, "<table-id>") if styler.uuid else styler.styles
        return normalize(out)
    if kind == "plotly_chart":
        return normalize(json.loads(node.proto.spec))  # TODAS las trazas, ayudas y layout
    if kind == "json":
        value = node.value
        return normalize(json.loads(value) if isinstance(value, str) else value)
    if hasattr(node, "children"):
        return {"label": getattr(node, "label", None)}
    out = MessageToDict(node.proto, preserving_proto_field_name=True)
    for key in ("id", "form_id"):
        out.pop(key, None)
    return normalize(out)


def dump_tab(tab):
    out = []

    def walk(node):
        for child in getattr(node, "children", {}).values():
            out.append({"type": child.type, "content": payload(child)})
            walk(child)

    walk(tab)
    return out


def run(repo, output, original=False):
    os.chdir(repo)
    sys.path.insert(0, str(repo))
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(repo / "app/main.py"), default_timeout=1200)
    snapshots = {}

    def capture(label):
        if app.exception:
            raise AssertionError(f"{label}: {[e.value for e in app.exception]}")
        if len(app.tabs) != 6:
            raise AssertionError("La app no mostró las seis pestañas")
        snapshots[label] = dump_tab(app.tabs[0])

    app.run()
    capture("default")
    # Un expander cerrado también ejecuta su cuerpo: no se excluye ningún nodo.
    for pair in range(1 if original else 3):
        app.selectbox(key="pilot_pair").set_value(pair)
        app.button(key="pilot_load_pair").click().run()
        capture(f"pair_{pair}")
    if not original:
        # Volver al estado sin un par cargado; cubrir detalle diario, VWAP y 4h.
        app.session_state["pilot_loaded_pair"] = None
        for tf in ("1h", "4h"):
            app.selectbox(key="pilot_tf").set_value(tf).run()
            capture(f"price_{tf}")
        app.selectbox(key="pilot_reference_^NDX").set_value("QQQ").run()
        capture("price_4h_etf")
    output.write_text(json.dumps(snapshots, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(f"Volcado completo: {repo.name} · {sum(len(v) for v in snapshots.values())} elementos", flush=True)


if __name__ == "__main__":
    run(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), "--original" in sys.argv[3:])
