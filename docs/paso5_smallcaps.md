# Paso 5 — actualización auditada, regla binomial y piloto Small caps

## Actualización real, respaldo y cobertura

Se ejecutaron `update_data.py`, `update_indices_references.py` y `run_calc.py`,
con respaldo automático previo y verificación de integridad y SHA-256. Se
conservaron copias consistentes antes/después, logs y conteo de claves, sin
confundir filas recibidas con precios corregidos o velas nuevas.

- Respaldo: `finance_20261011T051754.869407Z.zip`; integridad `ok`.
- Índices: 15385 velas nuevas; sesiones diarias hasta 2026-10-09. La etiqueta UTC de Nikkei es 2026-10-08 15:00, equivalente al 2026-10-09 en Tokio.
- Metales: 31901 velas nuevas; último diario 2026-10-09.
- Equity: 45351 velas nuevas; último diario 2026-10-09.
- Small caps: 9652 velas nuevas; último diario 2026-10-09.
- Cripto: 67622 velas nuevas; diario almacenado hasta 2026-10-11; la vela diaria abierta no se considera terminada.
- Argentina: 19528 velas nuevas; diario hasta 2026-10-09.
- Referencias negociables adicionales del piloto: 32345 velas nuevas.
- Total de claves nuevas: 221784.
- Velas existentes corregidas: 154.
- Claves retiradas por reconstrucción: 0.
- Registros nuevos FRED: 35, repartidos en las series configuradas.
- Errores fatales de descarga y cálculo: 0.
- `update_data.py` retornó código 1 por actualizaciones parciales, no por un fallo fatal.
- Avisos de límite de descarga: 37, principalmente la recuperación histórica de un minuto de Yahoo.
- Avisos de bloques incompletos de cuatro horas: 68. No se inventaron precios para completarlos.
- Avisos de excepciones de apertura de cuatro horas: 4.
- Avisos de posibles huecos: 2804. Auditoría con calendarios: 87 son pausas normales; 2717 son posibles faltas de datos con mercado abierto, no confirmación automática de errores.

La mayoría de los posibles huecos corresponden a ADR/acciones argentinas y
ETF poco líquidos; se preservan los avisos y la evidencia. La pausa de almuerzo
de Japón y el cierre/mantenimiento de futuros no se cuentan como velas faltantes
en la auditoría por calendario.

## Lectura actualizada de esta corrida

Los valores se extraen de los modelos que usa la interfaz. Tienen su corte
explícito; no se presentan como precios posteriores a la descarga.

- BTC: 83077,78, cierre de un minuto de 2026-10-11 05:28 UTC, Binance.
- ETH: 2508,94, mismo corte, Binance.
- Cripto: 1 de 6 con dirección diaria alcista; las otras 5 son laterales.
- ETH/BTC: 0,03020327; distancia a media -4,43%; percentil 3,2%.
- SOL/BTC: 0,00132657; distancia a media -1,10%; percentil 48,0%.
- Mayor separación de VWAP: HYPE en Bybit, -0,4774% al corte común 2026-10-11 05:29 UTC.
- Oro: 4216,2998, último cierre de un minuto guardado de 2026-10-09 20:59 UTC, Yahoo.
- Metales: 1 sube, 2 bajan y 1 está lateral; Cobre es el alcista.
- Cobre sobre las veinte ruedas comunes: +3,4792%; Oro -4,3337%; Plata -5,0339%; Platino -5,7760%.
- Ratio Oro/Plata: 69,0653; media 68,3084; distancia +1,11% y +0,67 desvíos.
- Equity: 3 de 11 sectores suben; Tecnología, Energía y Salud. Bajan 3 y están laterales 5.
- Líder sectorial contra S&P 500: Tecnología, +3,90 puntos porcentuales.
- Rezagado: Financiero, -6,42 puntos.
- Tecnológicas: 6 de 7 suben; Alphabet está lateral.
- Mayor separación normalizada: Microsoft, +8,86% y +3,12 desvíos.
- VIX: 15,41, dato del 2026-10-08.
- Tasa a diez años: 5,22, dato del 2026-10-08.
- Spread high yield: 3,15, mismo día.
- Índice amplio del dólar: 121,3848, dato del 2026-10-02; se mantiene el aviso de rezago de publicación.

## Nueva regla binomial

Se usa una prueba unilateral de cola superior: para los bloques válidamente
evaluados se encuentra el menor número de confirmaciones cuya probabilidad
binomial de ocurrir por azar no excede el nivel establecido. La regla es por par
y temporalidad, sobre bloques disjuntos; no equivale a garantizar una relación.

- Probabilidad nula de confirmación por azar: 5%.
- Nivel de significación: 5%.
- Con 6 bloques evaluados: mínimo 2 confirmaciones.
- Con 13: mínimo 3.
- Con 20: mínimo 4.
- Con 80: mínimo 8.
- Una confirmación que no alcanza el mínimo produce «sin relación (compatible con azar)».
- «Intermitente» requiere alcanzar el mínimo binomial; la historia significativa puede ser intermitente aunque el tramo reciente no confirme.
- «Estable» conserva además las condiciones aprobadas de tramo reciente, ambas direcciones, contraste y Johansen.
- Solana conserva el modo limitado de cuatro bloques y el rótulo máximo «Estable (provisional)»; también debe pasar el filtro binomial.
- Las pruebas inválidas no se cuentan como confirmaciones negativas: se muestra el número válido evaluado y se usa ese número en la prueba.
- Fotos: formato 9 por cambio de significado, con `cointegration_definition=binomial_blocks_v1` y evidencia guardada; las anteriores se rotulan «Regla anterior: sin filtro binomial de azar» sin reescribir sus JSON.

Antes/después sobre los mismos datos ya actualizados:

- Nasdaq/S&P diario: intermitente → compatible con azar; 1/20 confirmados, azar esperado 1,00, mínimo 4.
- S&P/Dow diario: sin relación → compatible con azar; 0/17, esperado 0,85, mínimo 4.
- Nasdaq/Russell diario: sin relación → compatible con azar; 0/19, esperado 0,95, mínimo 4.
- Oro/Plata diario: sin relación → compatible con azar; 0/13, esperado 0,65, mínimo 3.
- Oro/Cobre diario: sin relación → compatible con azar; 0/13, esperado 0,65, mínimo 3.
- BTC/ETH diario: intermitente → intermitente; 2/6, esperado 0,30, mínimo 2.
- BTC/ETH 1h: intermitente → compatible con azar; 4/80, esperado 4,00, mínimo 8.
- BTC/ETH 4h: intermitente → compatible con azar; 1/40, esperado 2,00, mínimo 5.
- ETH/SOL diario: sin relación → compatible con azar; 0/4, esperado 0,20, mínimo 2.
- ETH/SOL 1h: sin relación → compatible con azar; 2/54, esperado 2,70, mínimo 7.
- ETH/SOL 4h: sin relación → compatible con azar; 2/27, esperado 1,35, mínimo 4.
- BTC/SOL diario: sin relación → compatible con azar; 0/4, esperado 0,20, mínimo 2.
- BTC/SOL 1h: sin relación → compatible con azar; 2/54, esperado 2,70, mínimo 7.
- BTC/SOL 4h: sin relación → compatible con azar; 2/27, esperado 1,35, mínimo 4.
- Tecnología/Consumo discrecional diario: sin relación → compatible con azar; 0/13, esperado 0,65, mínimo 3.
- Financiero/Industrial diario: intermitente → compatible con azar; 2/13, esperado 0,65, mínimo 3.

## Por qué cambió el total de elementos comparados

El contador era acumulado por escenarios, no el número de elementos únicos de
la pestaña inicial. Se reconstruyó la explicación usando los volcados guardados:

- Perfil anterior: 9 estados de interfaz, 2948 elementos acumulados.
- Vista inicial y primeros estados sin par de Índices cargado: 320 nodos, repetidos 6 veces.
- Par de Índices cargado: 334 nodos.
- Detalle de una hora: 344 nodos.
- Detalle de cuatro horas: 350 nodos.
- Suma del perfil anterior: 6 × 320 + 334 + 344 + 350 = 2948.
- Perfil ampliado: 13 estados, con 320 nodos iniciales y 334 repetidos en los 12 estados posteriores porque el par seguía cargado.
- Suma del perfil ampliado: 320 + 12 × 334 = 4328.
- Vista inicial entre ambos volcados: 320 contra 320; contenido completo idéntico.

No hubo una ganancia involuntaria de contenido. Se amplió el perfil interactivo
y se mantuvo un par cargado. Los informes nuevos incluyen el desglose por estado
para no volver a confundir escenarios con tamaño de pantalla.

Las regresiones históricas quedan fijadas en los commits aprobados anteriores
al filtro binomial. Su corpus de test, compartido por ambos lados, tiene un
cierre diario por sesión de futuro y límites de historia suficientes para las
ventanas antiguas. Esa copia nunca modifica la base productiva. La comparación
de la regla actual y la de Small caps usan la copia íntegra actualizada; no se
ocultan cambios intencionales de clasificación como si fueran regresiones.

La carga de calendarios se optimizó sin cambiar sus resultados. Se verificó
equivalencia de fechas, horario de verano, cierres anticipados y pausas de
almuerzo. Las esperas largas de AppTest usan un reloj monotónico local al módulo
de testing. Para las dos regresiones actuales se fija, además, el mismo corte
de evaluación en ambos procesos. Así se comparan antigüedad, alineación,
velas abiertas y avisos reales con el mismo reloj, sin eliminarlos del volcado.
La aplicación normal no usa ese reloj fijo.

## Small caps implementado

La pestaña usa `render_section_pilot` y `config/sections.yaml`. Los cuatro ETF
son Russell 2000 (IWM), S&P 600 (IJR), crecimiento (IWO) y valor (IWN).
El S&P 500 se carga como denominador externo del ratio; no se suma al conteo.

- Sesión regular de Nueva York, 09:30–16:00, ajustada por calendario, DST y cierres anticipados.
- VWAP con precio y volumen del mismo ETF; sin premercado.
- Cuatro horas reconstruidas por sesión, con segundo bloque más corto cuando corresponde.
- Ratios sobre cierres diarios comunes: IWM/S&P 500 e IWO/IWN.
- Media simple y desvío muestral de 50 cierres comunes, sin ATR sintético.
- Percentil de la distancia por desvío con signo, hasta 250 observaciones válidas y mínimo 20.
- Tendencia por cambio de la media simple frente a cinco cierres comunes atrás.
- Dos pares de cointegración diarios, con prueba binomial y evidencia histórica/recentemente evaluada.
- En escalas intradía se informa historia insuficiente para la comparación de pares.
- Formato de foto 10: KPIs, ratios, percentiles, tendencias, pares y política de sesión guardados al tomarla.
- Navegar o cambiar selectores no genera fotos; las anteriores conservan su JSON.

Lectura extraída del AppTest de esta corrida, calculada el 2026-10-12 a las
20:22 UTC sobre los datos descargados previamente, con cierre común 2026-10-09:

- ETF que suben: 0 de 4; los cuatro tienen dirección diaria bajista.
- IWM/S&P 500: 0,035709; distancia -5,68%; -1,87 desvíos; percentil 12,8%; tendencia decreciente.
- IWO/IWN: 1,691943; distancia -0,50%; -0,40 desvíos; percentil 52,0%; tendencia creciente.
- Mayor separación normalizada: valor (IWN), -2,75% y -1,05 desvíos de su EMA diaria.
- IWM/S&P 500 diario: sin relación (compatible con azar); 0 de 13 bloques confirmados; esperado 0,65; mínimo significativo 3.
- IWO/IWN diario: mismo estado, 0 de 13; esperado 0,65; mínimo 3.
- Tramo reciente de ambos pares: 0 de 5 bloques confirmados.
- Tasa a diez años: 5,22; high yield: 3,15; ambos fechados 2026-10-08.
- La pantalla avisó que los cuatro cierres eran antiguos para la hora de consulta. Estos valores no se presentan como cotización en vivo.

## Verificación final de esta etapa

Se completaron 110 pruebas `unittest` y las 5 pruebas sintéticas independientes.
No es una única ejecución ininterrumpida: el comando general alcanzó su límite
de dos horas tras 106 pruebas completadas; los cuatro bloques restantes se
ejecutaron por separado. La primera regresión sin corte compartido detectó
cambios de antigüedad al pasar el tiempo; no se aceptó ese resultado como paridad.
Las dos regresiones actuales se repitieron completas con base íntegra y reloj
de evaluación compartido, y pasaron. No se omitió ninguna suite.

- Sintéticas: 5.
- C0: 22; C1: 7; C2: 20; C3: 5.
- Cuatro horas: 16; pantalla de cuatro horas: 1.
- Metales: 3; fotos/ranking: 2; estadísticas por bloques: 5.
- Binomial: 5; auditoría de actualización: 1; equivalencia de calendarios: 2.
- Cripto: 8; Equity: 4; Small caps: 3.
- Regresiones históricas Índices/refactor, Cripto, ajustes Cripto y Equity: 1 cada una.
- Regresión de cambio binomial: 1; regresión de agregar Small caps: 1.

Regresión Small caps contra `f7aef2e`, misma copia íntegra de SQLite,
17 escenarios por pestaña y corte compartido 2026-10-13 06:48:53,695235 UTC:

- Índices: 6950 elementos comparados; 0 diferencias.
- Metales: 6805 elementos; 0 diferencias.
- Cripto: 5053 elementos; 0 diferencias.
- Equity: 7377 elementos; 0 diferencias.

Cambio de regla binomial con corte compartido 2026-10-13 06:48:53,391774 UTC:

- Índices: 6950 elementos; 145 diferencias intencionales dentro de cointegración; fuera 0.
- Metales: 6805 elementos; 121 diferencias de regla; fuera 0.
- Cripto: 5053 elementos; 67 diferencias de regla; fuera 0.
- Equity: 7377 elementos; 73 diferencias de regla; fuera 0.

Regresiones históricas finales, sobre corpus de test acotado compartido:

- Equity: Índices 5238, Metales 5130, Cripto 3888 elementos; 0 diferencias en los tres.
- Ajustes Cripto: Índices 5238 y Metales 5130; 0 diferencias. Cripto 3888 elementos con 139 diferencias solicitadas; fuera de esos ajustes, 3614 elementos y 0 diferencias.

Estos totales pertenecen a sus propios perfiles y cortes, no reemplazan ni
reinterpretan las mediciones históricas 2948/4328 explicadas arriba.

Evidencia local conservada bajo el directorio de trabajo temporal de OpenCode:
`step5-refresh/`, `smallcaps-live-reading.json`, `smallcaps-tests.log`,
`final-suite-smallcaps.log`, `final-crypto-adjustments.log`,
`final-equity-regression.log`, `regression-smallcaps-fixed-clock/` y
`rule-fixed-clock/`. Los dos últimos contienen las capturas completas,
informes por escenario y `asof.txt` del corte compartido.

Para reproducir los dos últimos bloques:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 caffeinate -i .venv/bin/python -B test_smallcaps_regression.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 caffeinate -i .venv/bin/python -B test_rule_regression.py
```

El siguiente piloto, Argentina, queda sujeto a confirmación del usuario.

## Auditoría posterior de avisos y correcciones

El desglose por sección y temporalidad, las 154 filas modificadas de la
actualización y la verificación de que no hubo ningún salto de split están en
[auditoria_actualizacion.md](auditoria_actualizacion.md). Se reconstruyeron
desde el registro de la base y desde el respaldo previo, sin volver a
descargar ni modificar datos.

El comando para correr la suite completa, cuánto tarda y cómo dividirla está
en [pruebas.md](pruebas.md).
