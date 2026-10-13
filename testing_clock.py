"""Controles explícitos de tiempo para testing y regresión.

Streamlit usa time.time en su espera de testing: un salto del reloj del sistema
puede agotar el plazo aunque no transcurrió ese tiempo de ejecución. Se cambia
solo el reloj del módulo de espera. Los volcados de regresión, por separado,
fijan Timestamp.now al mismo corte en sus dos procesos para evaluar antigüedad
y velas abiertas de manera reproducible. La aplicación normal no llama esto.
"""
import time
import os
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd


def monotonic_apptest_wait():
    from streamlit.testing.v1 import local_script_runner
    local_script_runner.time = SimpleNamespace(time=time.monotonic, sleep=time.sleep)


def fixed_regression_time():
    """Mismo corte explícito en ambos procesos; conservar lógica de antigüedad.

    Solo los volcados de regresión llaman esta función. No se normalizan ni
    eliminan los efectos visibles de datos atrasados, velas abiertas o cierres.
    """
    asof = pd.Timestamp(os.environ["FINANCE_REGRESSION_ASOF"])
    if asof.tzinfo is None:
        raise ValueError("El corte de regresión requiere zona horaria")
    asof = asof.tz_convert("UTC")
    clock = patch.object(pd.Timestamp, "now", side_effect=lambda tz=None: asof.tz_convert(tz) if tz else asof.tz_convert(None))
    clock.start()
    return clock
