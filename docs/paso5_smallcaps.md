# Preparación del Paso 5 y piloto Small caps

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
de testing, sin modificar las fechas de la aplicación ni omitir comprobaciones.
