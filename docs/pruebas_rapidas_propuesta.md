# Prueba rápida: propuesta (no implementada todavía)

La suite completa tarda más de ocho horas, así que después de cada cambio no
se puede correr. Esta es la propuesta para tener una regresión de las seis
pestañas que corra en pocos minutos. Según lo pedido, todavía **no está
implementada**.

## Idea central

Crear una **base de datos de prueba congelada**: una copia chica de la base
real que no vuelve a actualizarse nunca, con un reloj congelado. Con eso, la
regresión de las seis pestañas deja de comparar contra la base grande y
compara contra resultados ya guardados de esa copia chica.

## Qué llevaría esa copia

| Dato | Qué se copia | Por qué alcanza |
|---|---|---|
| 1D | últimos 30 días de cada activo, más los 260 días previos que necesitan las medias de 50/200 y la ventana del régimen (263 velas) | La mediana, el cambio a 5 ruedas y el régimen no se calculan sin esa cola histórica; con ella todo queda igual |
| 4h | la serie ya versionada de cada activo, tal como está guardada | La pestaña nunca reconstruye la 4h al mostrarla |
| 1h | el mes de historia que usa la vista | El selector de 1h nunca muestra más |
| 15m | los 10 días de historia que usan las ventanas intradía configuradas | Los rangos por defecto piden exactamente eso |
| 5m y 1m | últimos 5 y 2 días | Los rangos por defecto piden eso y no más |
| Cálculos | las tablas ya cargadas de régimen, zscore, macro y cointegración, hasta la fecha congelada | Para que «Fuentes, fechas, parámetros y calidad de los datos» renderice con datos reales |
| Avisos y correcciones | las filas registradas hasta la fecha congelada | La sección de avisos queda idéntica |

La copia se genera **solo cuando vos lo pidas**: un comando escribe
`test_fixtures/db_fast.db` con ese recorte y deja guardado cuándo y desde
qué commit se hizo. De ahí en más no se toca.

## Cómo se congela la hora

El proyecto ya tiene el reloj de pruebas (`testing_clock.py`) con reloj
monotónico y la variable `FINANCE_REGRESSION_ASOF`. Se suman dos cosas
nuevas:

- `FINANCE_TEST_FAST_DB` — ruta de la base congelada. Si la variable no
  está, la regresión rápida se saltea y avisa; nunca usa la base grande
  por accidente.
- `FINANCE_TEST_ASOF` — fecha y hora congelada que se aplica al `now` de
  las pantallas y a las fotos. Se guarda junto con la copia para que la
  misma copia dé siempre el mismo resultado.

## Qué correría contra esa base

| Prueba | Hoy | Con la copia congelada |
|---|---|---|
| Regresión de las seis pestañas, incluida Argentina | 75 min | **~7 min** (estimado) |
| Regresión del cambio de regla | 2 h 10 min | **~6 min** (estimado) |
| Bloque rápido (85 tests) | 34 min | ~34 min; los tests de pantalla bajan a **~15 min** si les pasan la variable |
| Total de regresión después de un cambio | 3 h 25 min | **~13 min** |

Las duraciones nuevas son **estimaciones**: la ganancia viene de reducir las
filas que lee cada pantalla (con la base grande, la pestaña de Índices lee
cientos de miles de velas; con la copia, casi diez veces menos). La cifra
exacta se confirmará con una corrida real durante la implementación; si
alcanza con menos recorte, el recorte puede ser aún más chico.

## Cómo se comprueba que da lo mismo

La comprobación es una **paridad** que se corre una vez al crear la copia y
cada vez que se vuelve a generar; no después de cada cambio:

1. Se genera la copia congelada en el commit del día.
2. Se corren las mismas pantallas dos veces, con el mismo reloj congelado:
   una contra la copia congelada y otra contra la base grande real.
3. Se comparan las salidas elemento por elemento, con el mismo comparador
   que ya usan las regresiones (`test_regression.compare`).
4. Si la comparación da cero diferencias, la copia queda **validada**: se
   escribe una marca con el commit y el detalle del recorte. Las regresiones
   rápidas solo corren si la marca existe; si la paridad da distinto, la
   marca no se escribe, la regresión rápida no corre y avisa que hay que
   regenerar la copia o revisar el recorte.
5. El detalle del recorte queda en `test_fixtures/fixture.json` (fecha
   congelada, commit de origen, recuento de filas por tabla), así que
   cualquier resultado posterior se puede reproducir con la copia o
   descartarla con evidencia.

Una aclaración: la paridad se comprueba contra la base grande **de ese
día**. La base grande sigue evolucionando en cada actualización, pero eso
no invalida la copia congelada: lo que debe ser estable es la copia y el
reloj, no la base grande.

## Riesgos y cómo se corrigen

- **Corte mal colocado:** si la fecha congelada cae en medio de una rueda o
  sobre una vela provisional, las pestañas muestran etiquetas «provisional»
  y la paridad marca diferencias. Corrección: la fecha se fija siempre a
  las 05:00 UTC del día siguiente a la última rueda cerrada.
- **Recorte que deja historia insuficiente:** si la copia pierde primeras
  velas que la ventana del régimen pide, activos quedarían «Historia
  insuficiente» y la paridad marcaría diferencia. Corrección: el recorte de
  1D se hace por ruedas (se copian las últimas 290 de cada activo: 30 de la
  ventana de lectura más 260 de cola), no por fecha.
- **Las 4h versionadas:** la serie de 4h guarda su versión y su historia de
  actualizaciones; el recorte se hace después de copiar ese registro
  completo, así la etiqueta «4h versionada» queda igual en ambas bases.
- **Equivocarse de base:** el riesgo mayor de una copia de prueba es
  apuntarla a la base real por error. Mitigación: la carpeta
  `test_fixtures/` queda separada de `data/` y la regresión rápida se
  rechaza si `FINANCE_TEST_FAST_DB` apunta al archivo `data/finance.db`.

## Comando previsto (cuando esté implementado)

```bash
# generar la copia congelada (una vez, o cuando la paridad la pida)
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  caffeinate -i .venv/bin/python make_fast_fixture.py

# comprobación de paridad (solo al crear o regenerar la copia)
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  caffeinate -i .venv/bin/python -B -m unittest test_fast_fixture

# regresión rápida de todos los días, equivalente a las dos regresiones
# largas de la suite en un cuarto de hora:
FINANCE_TEST_FAST_DB="$PWD/test_fixtures/db_fast.db" \
FINANCE_TEST_ASOF="$(.venv/bin/python -c 'import json; print(json.load(open("test_fixtures/fixture.json"))["asof"])')" \
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  caffeinate -i .venv/bin/python -B -m unittest test_rule_regression test_argentina_regression
```
