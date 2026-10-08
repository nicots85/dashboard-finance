"""Volcador de la pestaña Indices via AppTest. Uso:
    python _regdump.py <app_main.py_abs> <out_json_abs>
Imprime un JSON con:
  - "apptest": volcado normalizado de la vista por defecto de la pestana Indices
  - "model":   volcado exacto (reloj fijo) de view_model + cointegration
Solo usa streamlit/json/pandas; es agnostico a la version del repo.
"""
import json
import os
import re
import sys

import numpy as np
import pandas as pd


def repo_of(app_main_py):
    app_dir = os.path.dirname(os.path.abspath(app_main_py))
    return os.path.dirname(app_dir)


def norm_text(s):
    if not isinstance(s, str):
        s = str(s)
    # hora de calculo (volatil)
    s = re.sub(r"Calculado: \d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}", "Calculado: <T>", s)
    # antiguedad de los datos (volatil)
    s = re.sub(r"hace \d+ (?:min|h|dias)", "hace <edad>", s)
    # uid generados por plotly (no deterministas entre corridas/versiones)
    s = re.sub(r'"uid":\s*"[0-9a-f]+"', '"uid": "<uid>"', s)
    return s


def cell(v):
    if v is None:
        return None
    if isinstance(v, float) and np.isnan(v):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        v = float(v)
    if isinstance(v, pd.Timestamp):
        return norm_text(v.isoformat())
    if isinstance(v, (np.datetime64,)):
        return norm_text(str(v))
    return norm_text(v) if isinstance(v, str) else v


def df_dump(df):
    cols = [str(c) for c in df.columns]
    rows = []
    for _, r in df.iterrows():
        rows.append({c: cell(r[df.columns[i]]) for i, c in enumerate(cols)})
    return {"columns": cols, "rows": rows}


def leaf(node):
    """Valor normalizado de un elemento hoja, o None si es solo contenedor."""
    t = node.type
    try:
        if t in {"dataframe"}:
            return {"dataframe": df_dump(node.value)}
        if t == "table":
            return {"table": node.value}
        if t == "metric":
            m = node
            return {"metric": {"label": norm_text(m.label), "value": norm_text(m.value),
                               "delta": norm_text(m.delta) if m.delta is not None else None,
                               "help": norm_text(getattr(m, "description", "") or "")}}
        if t in {"json"}:
            return {"json": _jsonable(node.value)}
        if t == "plotly_chart":
            spec = json.loads(node.proto.spec)
            return {"chart": _chart(spec)}
        if t in {"markdown", "caption", "info", "success", "warning", "error",
                 "subheader", "text", "json", "header", "title", "alert"}:
            return {t: norm_text(node.value)}
    except Exception as exc:  # noqa: BLE001
        return {"error": norm_text(f"{t}: {exc}")}
    return None


def _jsonable(v):
    try:
        return json.loads(json.dumps(v, default=str))
    except Exception:  # noqa: BLE001
        return norm_text(str(v))


def _chart(spec):
    out = {"data": [], "layout": {}}
    for tr in spec.get("data", []):
        entry = {"type": tr.get("type")}
        for k in ("x", "y", "open", "high", "low", "close", "name", "customdata"):
            if k in tr:
                val = tr[k]
                if isinstance(val, list):
                    val = [None if (isinstance(x, float) and np.isnan(x)) else (norm_text(x) if isinstance(x, str) else x) for x in val]
                out["data"].append({tr.get("name") or tr.get("type") or "?": {**entry, k: val}})
        if "name" not in tr:
            out["data"].append({entry.get("type") or "?": entry})
    lay = spec.get("layout", {})
    out["layout"] = {"title": _jsonable(lay.get("title")), "yaxis_title": _jsonable(lay.get("yaxis_title", {}).get("text") if isinstance(lay.get("yaxis_title"), dict) else lay.get("yaxis_title")), "xaxis_title": _jsonable(lay.get("xaxis_title", {}).get("text") if isinstance(lay.get("xaxis_title"), dict) else lay.get("xaxis_title"))}
    return out


def walk(node, acc, in_expander=False):
    kids = getattr(node, "children", {})
    for idx in sorted(kids.keys()):
        child = kids[idx]
        child_in_exp = in_expander or (child.type == "expander")
        leaf_val = leaf(child)
        acc.append({"type": child.type, "in_expander": child_in_exp, "value": leaf_val})
        walk(child, acc, child_in_exp)


def apptest_dump(app_main_py):
    from streamlit.testing.v1 import AppTest
    a = AppTest.from_file(os.path.abspath(app_main_py), default_timeout=900).run()
    if a.exception:
        raise SystemExit("AppTest exception: " + str([e.value for e in a.exception]))
    acc = []
    walk(a.tabs[0], acc)  # solo la pestana Indices
    return acc


def model_dump(repo, db):
    os.chdir(repo)
    if repo not in sys.path:
        sys.path.insert(0, repo)
    import importlib
    import inspect

    import app.indices as ix
    importlib.reload(ix)
    from src.data import DatabaseManager

    cfg = ix.configs
    if "section" in inspect.signature(cfg).parameters:
        assets, calc, pilot, ops, pairs = cfg("indices")
    else:
        assets, calc, pilot, ops, pairs = cfg()
    signature = DatabaseManager(db).data_signature()
    minute = "2025-06-10T00:00:00+00:00"
    sj = json.dumps([assets, calc, pilot, ops, pairs], sort_keys=True)

    def call(fn, **extra):
        params = inspect.signature(fn).parameters
        kw = {"db_path": db, "settings_json": sj, "_minute": minute}
        kw.update(extra)
        kw = {k: v for k, v in kw.items() if k in params}
        if "section" in params:
            kw["section"] = "indices"
        return fn(**kw)

    vm = call(ix.view_model, signature=signature)
    out = {
        "pilot_pairs": [("indices", len(pairs.get("indices", [])))],
        "rows": [{k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in r.items()} for r in vm["rows"]],
        "alignment": {s: {k: v for k, v in a.items() if k != "groups"} | {"groups": a["groups"]} for s, a in vm["alignment"].items()},
        "quality": df_dump(vm["quality"]),
        "performance": df_dump(vm["performance"].dropna(how="all")),
    }
    coint = []
    for p in pairs.get("indices", []):
        res = call(ix.cointegration_model, signature=signature, y=p["y"], x=p["x"])
        entry = {k: (round(v, 10) if isinstance(v, float) else v) for k, v in res.items()
                 if k not in {"spread", "rolling"}}
        if "spread" in res:
            entry["spread_last"] = round(float(res["spread"].iloc[-1]), 10)
            entry["spread_len"] = int(len(res["spread"]))
        if "rolling" in res:
            r = res["rolling"]
            entry["rolling_len"] = int(len(r))
            entry["p_yx_last"] = round(float(r["p_yx"].iloc[-1]), 10)
            entry["p_xy_last"] = round(float(r["p_xy"].iloc[-1]), 10)
        coint.append(entry)
    out["cointegration"] = coint
    return out


def main():
    app_main_py, out_json = sys.argv[1], sys.argv[2]
    repo = repo_of(app_main_py)
    os.chdir(repo)
    if repo not in sys.path:
        sys.path.insert(0, repo)
    db = os.path.join(repo, "data", "finance.db")
    result = {"apptest": apptest_dump(app_main_py), "model": model_dump(repo, db)}
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1, sort_keys=True, default=str)
    print("wrote", out_json)


if __name__ == "__main__":
    main()
