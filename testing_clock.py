"""Límite de AppTest con reloj monotónico, sin alterar fechas de la aplicación.

Streamlit usa time.time en su espera de testing: un salto del reloj del sistema
puede agotar el plazo aunque no transcurrió ese tiempo de ejecución. Se cambia
solo el reloj del módulo de espera, no time.time global ni Timestamp.now.
"""
import time
from types import SimpleNamespace


def monotonic_apptest_wait():
    from streamlit.testing.v1 import local_script_runner
    local_script_runner.time = SimpleNamespace(time=time.monotonic, sleep=time.sleep)
