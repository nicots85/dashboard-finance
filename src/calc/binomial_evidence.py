"""Prueba unilateral de confirmaciones frente a falsos positivos de bloques."""
from functools import lru_cache

from scipy.stats import binom


@lru_cache(maxsize=256)
def minimum_confirmations(evaluated, null_probability=0.05, alpha=0.05):
    if evaluated < 0 or not 0 < null_probability < 1 or not 0 < alpha < 1:
        raise ValueError("Parámetros binomiales inválidos")
    if not evaluated:
        return None
    return next(k for k in range(1, evaluated + 1) if binom.sf(k - 1, evaluated, null_probability) <= alpha)


def binomial_evidence(confirmed, evaluated, null_probability=0.05, alpha=0.05):
    if confirmed < 0 or confirmed > evaluated:
        raise ValueError("Confirmaciones fuera de la cantidad evaluada")
    minimum = minimum_confirmations(evaluated, null_probability, alpha)
    probability = float(binom.sf(confirmed - 1, evaluated, null_probability)) if evaluated else None
    significant = minimum is not None and confirmed >= minimum
    return {"confirmed": confirmed, "evaluated": evaluated, "expected_by_chance": evaluated * null_probability,
            "minimum_confirmed": minimum, "null_probability": null_probability, "alpha": alpha,
            "tail_probability": probability, "significant": significant,
            "conclusion": "Significativo frente al azar" if significant else "Compatible con azar" if evaluated else "Sin bloques evaluables"}
