# Paso 3: Cripto y aclaraciones de Metales

## Aclaraciones de Metales

La comparación inicial contra el dólar se implementó por la opción elegida en
la pregunta anterior. Resta el rendimiento de DTWEXBGS al del metal sobre ruedas
comunes con FRED; no ordena los cuatro metales sobre el mismo período reciente.
Se añadió el ranking entre los cuatro usando el mismo comienzo y fin para todos.
Es ahora el indicador grande principal de fuerza. La comparación contra el
dólar queda como contexto secundario, con fecha de corte y aviso de rezago.

Las fotos no guardaban el nuevo ratio, su media y distancias, ni estos
rendimientos. Ahora los guardan y los muestran en Historial, sin completar
fotos anteriores con datos actuales.

- Formato con los nuevos campos de Metales: versión 6.
- Formato que también incorpora ratios, VWAP, exchanges y cobertura de Cripto: versión 7.
- Campos de Metales: `ratios`, `relative_strength.between_assets`, `relative_strength.against_benchmark`, fecha del benchmark y `kpis.strongest_20_sessions`.
- Campos de Cripto: ratios con percentil y exchanges, `session_vwaps`, `exchange_sources`, `pair_coverage` e indicadores grandes.

## Funcionamiento de Cripto

`render_section_pilot` muestra Cripto mediante `config/sections.yaml`, sin copiar
la pantalla. El conteo diario, la alineación, ETH/BTC, SOL/BTC y la mayor distancia
al VWAP son los indicadores grandes. La tabla tiene Activo, Dirección,
Alineación, Distancia y Dato.

Se filtra el historial por exchange antes de calcular: el precio y volumen del
VWAP siempre pertenecen a la misma fuente. Si cambia el proveedor se avisa y se
identifica la fuente efectiva, sin sumar volúmenes de exchanges distintas.
Hyperliquid prefiere Bybit; las demás criptos prefieren Binance. La fuente por
temporalidad, sus cambios y calidad quedan en el desplegable.

La sesión reinicia a medianoche UTC. No se aplica un calendario bursátil,
descuento de fin de semana, feriado o pausa nocturna. Un cierre a medianoche
pertenece a la última vela del día anterior; la nueva sesión comienza con la
vela que abre a medianoche. El eje temporal continuo no tiene `rangebreaks` y
los huecos reales de datos se avisan.

Las distancias del ranking de VWAP usan la misma sesión y un cierre común.
Se excluyen de la elección las sesiones con volumen insuficiente o sin comienzo
de sesión disponible.

- Reinicio del VWAP: 00:00 UTC.
- Cobertura mínima de volumen válido para el ranking: 95%.
- Media y desvío muestral de ratios: 50 cierres diarios comunes.
- Percentil: distribución de la distancia por desvío con signo entre las últimas 250 observaciones válidas; mínimo 20 observaciones para publicarlo.
- Cointegración: bloques disjuntos de 500 cierres, mínimo 5 bloques y al menos 4 confirmados para «estable», junto con las demás comprobaciones aprobadas.
- Ventanas principal y contraste: 500 y 1000 cierres.
- Gráficos móviles diarios: cada 21 ruedas.
- Gráficos móviles intradía: cada 250 velas. La regla de estados y las ventanas de prueba no se reducen.

La cointegración se calcula bajo demanda en cada temporalidad. La cobertura
queda visible aun cuando el par no sea calculable. La beta larga es la misma
para las comparaciones reciente y larga. No se aplicó una regla especial a
Solana. Se conservan Fuentes y calidad, Glosario, Cómo leer esto, Vista anterior
y alineación por grupos de escalas. Dólar y VIX muestran la fecha del dato FRED.

## Propuesta para Solana — no aplicada

Propongo conservar los estados aprobados y agregar una marca visible de
«historia limitada», sin simular evidencia inexistente:

- Mínimo: 4 bloques disjuntos de 500 cierres comunes positivos, es decir, 2000 cierres.
- «Estable», marcado como provisional/historia limitada: confirmación de los 4 bloques en ambos órdenes, confirmación actual y contraste concordantes, p-valores inferiores a 0,05 en ambos órdenes y rango Johansen de 1 en ambas ventanas.
- «Intermitente»: confirmaciones parciales o discrepancias entre órdenes o ventanas, según el criterio actual.
- «Sin relación»: sin evidencia en bloques ni ventanas, y sin rango Johansen de 1.
- «No calculable»: menos de 4 bloques, prueba inválida o dispersión insuficiente.

Exigir todos los bloques compensa conservadoramente la historia más corta;
aun así no equivale a la evidencia temporal de la regla aprobada. La propuesta
requiere confirmación. La implementación continúa exigiendo cinco bloques.

## Valores reales de esta corrida

Lectura de la base disponible, **no cotizaciones en vivo**. AppTest usó una copia
SQLite consistente de los datos reales, sin descargar precios ni modificar la
base productiva.

- Captura: 2026-10-10 01:41:25 UTC, equivalente al 2026-10-09 22:41:25 de Buenos Aires.
- Metales, último cierre usado: 2026-10-05 21:00 UTC.
- Cripto, último cierre diario: 2026-10-06 00:00 UTC, correspondiente a la sesión del 2026-10-05.
- Dólar amplio: dato del 2026-09-25.
- Tasas y VIX: datos del 2026-10-01.

### Metales

- Dirección: 0 suben, 2 bajan; los otros 2 son laterales.
- Más alineado: sin escalas vigentes por antigüedad de datos.
- Más fuerte entre los cuatro: Cobre, -0,2425%; es el que menos cayó en este período.
- Más alejado de la media diaria: Oro, -0,96 desvíos.
- Período común: 2026-09-04 a 2026-10-05, con 20 cambios entre 21 cierres comunes.
- Cobre: -0,2425%.
- Platino: -5,2608%.
- Oro: -6,8288%.
- Plata: -6,9148%.
- Ratio Oro/Plata: 67,8416.
- Distancia del ratio a su media: -0,75%.
- Distancia del ratio por desvío: -0,44.
- Tasa nominal a diez años: 5,24; cambio mensual de +0,45.
- Tasa real a diez años: 2,88; cambio mensual de +0,44.
- Dólar amplio: 120,33; cambio mensual de +1,88.
- Oro/Plata: «sin relación», con 0 de 5 bloques confirmados y 6547 cierres comunes.
- Oro/Cobre: «intermitente», con 1 de 5 bloques confirmado y 6548 cierres comunes.
- Oro 15m: 850 velas visibles de 3746 disponibles, desde 2026-09-21 22:00 UTC hasta 2026-10-05 03:30 UTC.
- Última vela de Oro: apertura temporal a 2026-10-05 03:15 UTC.
- OHLC: apertura 4165,7002; máximo 4171,7998; mínimo 4164,2002; cierre 4170,8999.
- VWAP: 4176,9826, con base de cinco minutos del mismo futuro.
- Distancia al VWAP: -0,1456%, equivalente a -0,8001 bandas; desvío ponderado de 7,6027.
- Línea base larga: -3,74% frente a la media de 200 cierres diarios.

El detalle de Oro muestra velas, VWAP y bandas del mismo instrumento, sesión
completa provisional de Nueva York, rango visible y línea base larga. Platino
conserva solo la lectura diaria sin VWAP.

### Cripto

- Dirección diaria: 6 de 6 suben; 0 bajan.
- Más alineado: sin escalas vigentes por antigüedad de datos.
- ETH/BTC: 0,031555; distancia a la media de -0,32%; distancia por desvío de -0,17; percentil de 46,4%.
- SOL/BTC: 0,001400; distancia a la media de +5,65%; distancia por desvío de +1,04; percentil de 77,2%.
- Mayor separación del VWAP: BNB en Binance, -0,79%.
- Sesión de VWAP comparada: 2026-10-05; corte común a 2026-10-05 03:42 UTC; base de un minuto.
- Bitcoin, Ethereum, Solana, XRP y BNB: Binance.
- Hyperliquid: Bybit.
- Dólar amplio: 120,33; VIX: 16,39.
- BTC/ETH diario: «intermitente», 3337 cierres comunes y 6 bloques disponibles.
- ETH/SOL diario: «no calculable», 2247 cierres comunes y 4 bloques disponibles.
- BTC/SOL diario: «no calculable», 2247 cierres comunes y 4 bloques disponibles.
- BTC/ETH 1h: «intermitente», 79936 cierres y 159 bloques.
- ETH/SOL 1h: «intermitente», 53882 cierres y 107 bloques.
- BTC/SOL 1h: «intermitente», 53882 cierres y 107 bloques.
- BTC/ETH 4h: «intermitente», 20000 cierres y 40 bloques.
- ETH/SOL 4h: «sin relación», 13476 cierres y 26 bloques.
- BTC/SOL 4h: «intermitente», 13476 cierres y 26 bloques.

En intradía se evaluaron los cinco bloques más recientes; la tabla distingue
los bloques disponibles de los evaluados. La vista inicial muestra BTC 15m,
exchange, VWAP UTC y bandas; los pares se calculan al solicitarlos.

## Verificación final y reproducción

La base anterior a Cripto es `9014ede`: ya incluye las aclaraciones de Metales.
Sus cambios deliberados no se ocultan como si fueran diferencias causadas por
el agregado de Cripto.

- Regresión posterior a Cripto, Índices: 2948 elementos comparados; 0 diferencias.
- Regresión posterior a Cripto, Metales: 2556 elementos comparados; 0 diferencias.
- Regresión histórica de Índices contra 63c8401: 2319 elementos; 0 diferencias.
- Sintéticas: 5 aprobadas.
- C0: 22 aprobadas.
- C1: 7 aprobadas.
- C2: 20 aprobadas.
- C3: 5 aprobadas.
- Cuatro horas: 16 aprobadas.
- AppTest de cuatro horas e historial: 1 aprobada.
- Metales: 3 aprobadas.
- Indicadores y compatibilidad de fotos: 2 aprobadas.
- Cripto: 8 aprobadas.
- Regresión histórica AppTest: 1 aprobada.
- Regresión del agregado de Cripto: 1 aprobada.
- Total: 91 aprobadas, sin omisiones.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  .venv/bin/python -B test_crypto.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  .venv/bin/python -B test_crypto_regression.py
```

`PILOT_READING_OUTPUT` conserva el JSON de lectura de AppTest.
`CRYPTO_REGRESSION_OUTPUT_DIR` conserva los volcados anterior y actual y el
informe de comparación. Se incluyen todos los desplegables, ayudas, tablas y
datos completos de gráficos; solo se normalizan antigüedad y hora de cálculo,
además de omitir IDs de transporte.

Las pruebas verifican UTC, frontera de medianoche, fines de semana y feriados,
huecos reales, corte común del VWAP, exclusión de sesiones parciales, no mezcla
de exchanges, percentiles con signo, bloques de velas terminadas y conservación
de la regla aprobada para Solana. AppTest cargó las seis pestañas, calculó los
pares en todas las escalas y simuló un cambio de fuente en una copia. No creó
fotos al abrir o cambiar selectores; las fotos anteriores se mantienen intactas.
