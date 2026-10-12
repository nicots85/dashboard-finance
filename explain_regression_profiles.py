"""Desglose de nodos capturados, no confundir escenarios con contenido nuevo."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--step3", required=True)
    parser.add_argument("--group4", required=True)
    args = parser.parse_args()
    step3 = json.loads(Path(args.step3).read_text())
    group4 = json.loads(Path(args.group4).read_text())
    group4 = group4.get("readings", group4)
    for name, values in (("Perfil anterior", step3), ("Perfil ampliado", group4)):
        states = {k: v for k, v in values.items() if k.endswith("/indices")}
        print(f"{name}: {len(states)} estados; {sum(len(v) for v in states.values())} elementos acumulados")
        for state, nodes in states.items():
            print(f"- {state}: {len(nodes)} elementos")
    a, b = step3["default/indices"], group4["default/indices"]
    print(f"Vista inicial: {len(a)} y {len(b)} elementos; igualdad completa: {a == b}")


if __name__ == "__main__":
    main()
