# Cómo correr las pruebas

Todas las pruebas usan el intérprete del proyecto y la base real. Para que la
máquina no suspenda la ejecución ni compita por núcleos, conviene correrlas
así:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 caffeinate -i .venv/bin/python -B -m unittest test_c1
```

## Suite completa en un solo comando

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 caffeinate -i .venv/bin/python -B -m unittest \
  test_c0 test_c1 test_c2 test_c3 test_four_hour test_four_hour_app test_metales \
  test_pilot_photos test_block_statistics test_binomial test_refresh_report \
  test_calendar_equivalence test_crypto test_equity test_smallcaps test_argentina \
  test_regression test_crypto_regression test_crypto_adjustments_regression \
  test_equity_regression test_rule_regression test_smallcaps_regression \
  test_argentina_regression
```

Las pruebas sintéticas no son `unittest`: se corren aparte.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 caffeinate -i .venv/bin/python -B test_synthetic.py
```

## Por qué conviene dividirla

La suite completa **no entra en una sesión razonable**: las regresionesComparan
dos versiones completas de la aplicación en procesos separados y cada una tarda
más de una hora. Medido en esta máquina:

| Bloque | Pruebas | Duración medida |
| --- | ---: | ---: |
| Rápido (C0, C1, C2, C3, 4h, fotos, bloques, binomial, auditoría, calendarios) | 85 | 34 min |
| Sintéticas | 5 | menos de 1 min |
| Pantalla: 4h app, Metales, Cripto, Equity, Small caps, Argentina | 26 | ~1 h 50 min |
| Argentina (AppTest de las seis pestañas y foto) | 7 de las 26 anteriores | 18 min |
| Regresión histórica de Equity | 1 | 32 min |
| Regresión de ajustes de Cripto | 1 | 32 min |
| Regresión de la regla binomial | 1 | 2 h 10 min |
| Regresión de Small caps | 1 | 41 min |
| Regresión de Argentina | 1 | 75 min |

Total estimado de punta a punta: **más de ocho horas**. Por eso el bloque
rápido se puede repetir seguido, y las regresiones largas se lanzan por
separado.

## Bloques recomendados

```bash
# 1. Rápido: se puede correr seguido mientras se trabaja.
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 caffeinate -i .venv/bin/python -B -m unittest \
  test_c0 test_c1 test_c2 test_c3 test_four_hour test_pilot_photos test_block_statistics \
  test_binomial test_refresh_report test_calendar_equivalence

# 2. Pantalla: abre la aplicación real en las seis pestañas.
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 caffeinate -i .venv/bin/python -B -m unittest \
  test_four_hour_app test_metales test_crypto test_equity test_smallcaps test_argentina

# 3. Regresiones: una por vez, cada una en su propia corrida.
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 caffeinate -i .venv/bin/python -B test_equity_regression.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 caffeinate -i .venv/bin/python -B test_crypto_adjustments_regression.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 caffeinate -i .venv/bin/python -B test_rule_regression.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 caffeinate -i .venv/bin/python -B test_smallcaps_regression.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 caffeinate -i .venv/bin/python -B test_argentina_regression.py
```

## Conservar la evidencia

Varias pruebas escriben su volcado si se les da la variable de entorno:

| Variable | Prueba | Qué guarda |
| --- | --- | --- |
| `SMALLCAPS_READING_OUTPUT` | `test_smallcaps.py` | lectura de pantalla de Small caps |
| `ARGENTINA_READING_OUTPUT` | `test_argentina.py` | CCL de las cinco empresas y mediana |
| `REGRESSION_OUTPUT_DIR` | `test_regression.py` | volcados históricos y diferencias |
| `RULE_REGRESSION_OUTPUT_DIR` | `test_rule_regression.py` | antes y después de la regla binomial |
| `SMALLCAPS_REGRESSION_OUTPUT_DIR` | `test_smallcaps_regression.py` | antes y después de Small caps |
| `ARGENTINA_REGRESSION_OUTPUT_DIR` | `test_argentina_regression.py` | antes y después de Argentina |
| `CRYPTO_REGRESSION_OUTPUT_DIR` | `test_crypto_regression.py` | antes y después de Cripto |
| `CRYPTO_ADJUSTMENTS_REGRESSION_OUTPUT_DIR` | `test_crypto_adjustments_regression.py` | ajustes de Cripto |

## El tiempo y las regresiones

Dos reglas evitan falsos negativos y falsos positivos:

1. **Un reloj monotónico** para la espera de AppTest (`testing_clock.py`). Un
   salto del reloj del sistema puede agotar el plazo sin que haya pasado el
   tiempo de ejecución.
2. **El mismo corte de evaluación en los dos procesos** de una regresión
   (`FINANCE_REGRESSION_ASOF`). La antigüedad del dato y qué escalas están
   vigentes cambian con la hora; sin un corte compartido, dos versiones
   legítimas se comparan en instantes distintos y aparecen diferencias falsas.

Ninguna de las dos reglas normaliza los avisos, la antigüedad ni las velas
abiertas: esos efectos siguen visible y se comparan.

## Avisos que no son fallos

- `use_container_width will be removed after 2025-12-31`: advertencia de Streamlit.
- `ResourceWarning: unclosed database`: conexiones SQLite de las pruebas.
- `missing ScriptRunContext`: AppTest corre la aplicación sin servidor.