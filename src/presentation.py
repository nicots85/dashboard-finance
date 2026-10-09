"""Nombres, glosario y ayudas. Esta capa no descarga ni calcula datos financieros."""
import html
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
TF_LABELS = {"1m": "1 minuto (1m)", "5m": "5 minutos (5m)", "15m": "15 minutos (15m)",
             "1h": "1 hora (1h)", "4h": "4 horas (4h)", "1D": "Diario (1D)"}


@lru_cache(maxsize=4)
def _catalog(assets_time, glossary_time, pairs_time, pilot_time):
    assets = yaml.safe_load((ROOT / "config/assets.yaml").read_text(encoding="utf-8"))
    glossary = yaml.safe_load((ROOT / "config/glossary.yaml").read_text(encoding="utf-8"))
    pairs = yaml.safe_load((ROOT / "config/pairs.yaml").read_text(encoding="utf-8"))
    names = {symbol: name for section in assets.values() for symbol, name in section.get("nombres", {}).items()}
    pilot_file = ROOT / "config/sections.yaml"
    if pilot_file.exists():
        sections = yaml.safe_load(pilot_file.read_text(encoding="utf-8"))
        for section in sections.values():
            if section.get("enabled", False):
                names.update(section.get("names", {}))
    return assets, glossary, pairs, names


_active_catalog = None


def refresh_catalog():
    """Una sola lectura por ejecución de la app; las ediciones entran al recargar."""
    global _active_catalog
    pilot_file = ROOT / "config/sections.yaml"
    _active_catalog = _catalog(*[(ROOT / "config" / file).stat().st_mtime_ns
                                for file in ("assets.yaml", "glossary.yaml", "pairs.yaml")],
                              pilot_file.stat().st_mtime_ns if pilot_file.exists() else 0)
    return _active_catalog


def catalog():
    return _active_catalog if _active_catalog is not None else refresh_catalog()


def asset_label(symbol, timeframe=None):
    names = catalog()[3]
    if symbol not in names:
        raise KeyError(f"Falta el nombre en español de {symbol} en config/assets.yaml")
    if timeframe == "4h":
        from src.data.four_hour import label
        contextual = label(symbol, timeframe)
        if contextual:
            return contextual
    return f"{names[symbol]} ({symbol})"


def pair_label(y, x):
    return f"{asset_label(y)} / {asset_label(x)}"


def entity_label(value):
    assets, _, pairs, names = catalog()
    if value in names:
        return asset_label(value)
    for section_pairs in pairs.values():
        for pair in section_pairs:
            if value == f"{pair['y']}/{pair['x']}":
                return pair_label(pair["y"], pair["x"])
    if value == "FRED":
        return "Base de referencias económicas (FRED)"
    return f"Referencia sin nombre configurado ({value})"


def definition(term):
    definitions = catalog()[1]["terminos"]
    if term not in definitions or not str(definitions[term]).strip():
        raise KeyError(f"Falta la definición de {term} en config/glossary.yaml")
    return definitions[term]


def help_text(*terms):
    return "\n\n".join(f"{asset_label(t) if t in catalog()[3] else t}: {definition(t)}" for t in dict.fromkeys(terms))


def explain_symbols(text):
    """Completa símbolos de avisos sin duplicar nombres que ya están presentes."""
    names = catalog()[3]
    protected = {}
    for index, symbol in enumerate(sorted(names, key=len, reverse=True)):
        label = asset_label(symbol)
        if label in text:
            marker = f"\x00{index}\x00"
            protected[marker] = label
            text = text.replace(label, marker)
    pattern = re.compile(r"(?<![\w^])(" + "|".join(re.escape(s) for s in sorted(names, key=len, reverse=True)) + r")(?!\w)")
    text = pattern.sub(lambda match: asset_label(match.group(0)), text)
    for marker, label in protected.items():
        text = text.replace(marker, label)
    return text


def rich_text(text):
    """Ayuda al pasar sobre términos en textos; escapar HTML de la configuración."""
    definitions = catalog()[1]["terminos"]
    pattern = re.compile(r"(?<!\w)(" + "|".join(re.escape(t) for t in sorted(definitions, key=len, reverse=True)) + r")(?!\w)", re.IGNORECASE)
    lookup = {key.casefold(): key for key in definitions}
    pieces, start = [], 0
    for match in pattern.finditer(text):
        pieces.append(html.escape(text[start:match.start()]))
        key = lookup[match.group(0).casefold()]
        pieces.append(f'<abbr title="{html.escape(definition(key), quote=True)}">{html.escape(match.group(0))}</abbr>')
        start = match.end()
    pieces.append(html.escape(text[start:]))
    return "".join(pieces)


def section_terms(section, macro_symbols=()):
    assets, glossary, pairs, names = catalog()
    terms = set(glossary["comunes"]) | set(glossary["secciones"].get(section, []))
    terms |= set(assets[section]["activos"]) | set(macro_symbols)
    for pair in pairs.get(section, []):
        if section != "argentina":
            terms.update([pair["y"], pair["x"]])
    if section == "smallcaps":
        terms.add("^GSPC")
    def alphabetical(term):
        label = asset_label(term) if term in names else term
        return unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode().casefold()
    return sorted(terms, key=alphabetical)


# Las claves siguen siendo las de los datos originales. Solo cambia la etiqueta.
COLUMNS = {
    "Activo": ("Activo", ("activo",)),
    "Fuente": ("Fuente de datos", ("fuente",)),
    "Régimen (1D)": ("Régimen diario (1D)", ("régimen", "1D", "alcista", "bajista", "alcista (débil)", "bajista (débil)", "lateral", "sin datos", "baja vol", "normal vol", "alta vol")),
    "Z-ATR": ("Z-score por rango (ATR)", ("z-score", "ATR", "EMA")),
    "Z-desvío": ("Z-score por desvío", ("z-score", "desvío estándar", "EMA")),
    "Percentil Z": ("Percentil del z-score", ("percentil del z",)),
    "Par": ("Par de activos", ("par",)),
    "TF": ("Temporalidad", ("temporalidad",)),
    "Cointegrado": ("Relación comprobada", ("cointegración", "cointegrado", "no cointegrado", "no calculable")),
    "p-valor": ("p-valor", ("p-valor",)),
    "Beta": ("Beta", ("beta",)),
    "Z-spread": ("Z-score de la diferencia", ("z-score", "spread", "beta")),
    "Vida media (velas)": ("Vida media (velas)", ("vida media", "vela")),
    "Estabilidad %": ("Ventanas confirmadas (%)", ("estabilidad",)),
    "Activo o par": ("Activo o par", ("activo", "par")),
    "Temporalidad": ("Temporalidad", ("temporalidad",)),
    "Calculado (UTC)": ("Hora del cálculo (UTC)", ("fecha de cálculo", "UTC")),
    "Último dato usado (UTC)": ("Último dato usado (UTC)", ("último dato usado", "UTC")),
    "Estado": ("Estado del resultado", ("estado del dato", "no calculable")),
    "Aviso": ("Aviso", ("aviso",)),
    "Empresa": ("Empresa", ("empresa",)),
    "Local": ("Acción local", ("acción local",)),
    "ADR": ("Certificado estadounidense (ADR)", ("ADR",)),
    "Equiv.": ("Acciones por certificado", ("equivalencia", "ADR")),
    "CCL implícito": ("Dólar implícito (CCL)", ("CCL", "CCL implícito")),
    "% vs mediana": ("Diferencia con la mediana (%)", ("diferencia con mediana", "mediana")),
}


def column_specs(columns, context=None):
    specs = {"_index": {"label": None, "help": help_text("fila")}}
    for column in columns:
        if column in TF_LABELS:
            terms = (column, "antigüedad") if context == "age" else (column, "semáforo")
            label = "4h (método indicado abajo)" if column == "4h" else TF_LABELS[column]
            if column == "4h":
                extra = "Índices estadounidenses: 4h del futuro, rotulada vía NQ=F/ES=F/YM=F/RTY=F. ETF, acciones y ADR de EE.UU.: 4h de sesión 09:30–13:30 y 13:30–16:00 Nueva York (segunda más corta). Otros: método de la fuente, según auditoría."
            else:
                extra = ""
        else:
            if column not in COLUMNS:
                raise KeyError(f"Falta ayuda para la columna visible {column}")
            label, terms = COLUMNS[column]
            extra = ""
        specs[column] = {"label": label, "help": help_text(*terms) + ("\n\n" + extra if extra else "")}
    return specs
