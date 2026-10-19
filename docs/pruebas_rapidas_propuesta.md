# Prueba rápida: propuesta (implementación PAUSADA)

> **Estado: pausa decidida por el dueño (octubre 2026).** La infraestructura
> está escrita y funciona para generar la copia y para saltearse sola, pero
> la PRIMERA PARIDAD falló con **1.434 diferencias** y se decidió no seguir
> depurando ahora. Las regresiones rápidas se saltean por defecto; la suite
> sigue usando las pruebas lentas de siempre cuando se piden a mano.

## Qué ya está implementado (esperando retomar)

- `testing_frozen.py` — resuelve `FINANCE_TEST_FAST_DB`, rechaza la base
  real y las copias sin la marca de paridad, y saltea si la variable no
  está.
- `make_fast_fixture.py` — genera `test_fixtures/db_fast.db` (294 MB,
  1.361.878 filas; la base grande tiene 700 MB y 3.024.697) con
  `asof = 2026-10-12T05:00:00Z` (05:00 UTC del día siguiente a la última
  rueda diaria registrada), recortes por temporalidad conservadores:
  1m 10 días, 5m 40 días, 15m 120 días, 1h 900 días, y las últimas
  1.100 ruedas diarias por símbolo; deja las tres últimas fotos en
  `snapshot_photos`, correcciones completas y avisos de los últimos
  300 días.
- `test_fast_fixture.py` — paridad: mismo volcado de las cinco pestañas
  contra la copia congelada y contra la base grande con el mismo reloj;
  si da 0 diferencias escribe la marca `validado` en
  `test_fixtures/fixture.json`. Mantiene los volcados si se le pasa
  `PARITY_OUTPUT_DIR`.
- `test_rule_regression.py`, `test_smallcaps_regression.py`,
  `test_argentina_regression.py` — integradas a la copia congelada: sin
  la variable se **saltean**; con ella corren en minutos y rechazan
  explícitamente si la variable apunta a la base real.

## Qué mostró la primera paridad (motivo de la pausa)

1.434 diferencias repartidas por sección: índices 404, metales 358,
cripto 254, equity 316, smallcaps 102. Las categorías **sospechadas**
(sin confirmar aún con el detalle) son:

- gráficos diarios que muestran mucha más historia que los 1.100 ruedas
  copiadas (el oro arranca en 1927; algunas ventanas de pares usan
  1.000 ruedas además de las 500 del gráfico),
- horario de cripto desde 2017: el recorte de 1h de 900 días dejó fuera
  historia que algún gráfico muestra,
- con additionally, recortes de 5m/15m quizás insuficientes para las
  ventanas intradía de pares.

Confirmar estas categorías es lo primero al retomar: correr la paridad
con `PARITY_OUTPUT_DIR` y agrupar los detalles por pestaña y tipo de
elemento; luego ampliar los márgenes de `make_fast_fixture.py` (podría
convenir copiar 1D completo y 1h completo: la copia crecería a unos
500–600 MB y el volcado de paridad tomaría de nuevo los mismo minutos de
hoy), regenerar y repetir paridad.

## Qué falta antes de volver a usarla

1. Categorizar las 1.434 diferencias (una corrida con
   `PARITY_OUTPUT_DIR=/tmp/parity_diag` basta).
2. Ampliar recortes y regenerar `test_fixtures/db_fast.db`.
3. Paridad en 0 diferencias (escribe la marca `validado`).
4. Correr las tres regresiones rápidas contra la copia y medir
   tiempos reales para actualizar las cifras de este documento.
5. `docs/pruebas.md` con las duraciones nuevas.

## Comandos previstos (para el día en que se retome)

```bash
# regenerar la copia (reemplaza db_fast.db y fixture.json salvo la marca)
OPENBLAS_NUM_THREADS=1 .venv/bin/python make_fast_fixture.py --forzar

# paridad (escribe la marca si da 0 diferencias; guarda volcados)
PARITY_OUTPUT_DIR=/tmp/parity_diag \
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  .venv/bin/python -B -m unittest test_fast_fixture

# las tres regresiones rápidas (se saltean sin la variable de la copia)
FINANCE_TEST_FAST_DB="$PWD/test_fixtures/db_fast.db" \
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  .venv/bin/python -B -m unittest test_rule_regression test_smallcaps_regression test_argentina_regression
```

La carpeta `test_fixtures/` está ignorada por git (los 294 MB nunca
suben al repositorio); los volcados de diagnóstico viven en /tmp y
tampoco forman parte del repo.
