"""Antes/después de reglas sobre los mismos cierres, sin mezclar cambios de mercado."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    a = json.loads(Path(args.before).read_text())["pairs"]
    b = json.loads(Path(args.after).read_text())["pairs"]
    key = lambda row: (row["section"], row["y"], row["x"], row["tf"])
    old = {key(row): row for row in a}
    rows = []
    for row in b:
        prior = old[key(row)]
        if prior["bars"] != row["bars"]:
            raise ValueError("La comparación de reglas no usa los mismos cierres")
        evidence = row.get("binomial_evidence", {})
        item = {"section": row["section"], "y": row["y"], "x": row["x"], "tf": row["tf"],
                "before": prior["state"], "after": row["state"], "bars": row["bars"], **evidence}
        rows.append(item)
        print(f"- {row['section']} {row['y']}/{row['x']} {row['tf']}: {prior['state']} → {row['state']} · {evidence.get('confirmed')}/{evidence.get('evaluated')} confirmados · azar esperado {evidence.get('expected_by_chance')} · mínimo {evidence.get('minimum_confirmed')}")
    Path(args.output).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
