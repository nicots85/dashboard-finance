# Auditoría de avisos y correcciones de la actualización

Reconstruido desde el registro de la base de datos y desde el respaldo previo a la
actualización (`finance_20261011T051754.869407Z.zip`, integridad `ok`). No se descargó ni
modificó ningún dato para producir este informe.

## 1. Avisos de posible hueco

Avisos de hueco sin resolver: **2804**. Todos pudieron analizarse porque su
mensaje incluye las dos marcas de tiempo entre las que se detectó la ausencia.

### Criterio de clasificación

Para cada aviso se toma el final de la vela anterior y el inicio de la vela siguiente,
se avanza un minuto la primera marca (la vela anterior estaba abierta durante ese
tramo) y se cuentan los minutos en los que el mercado de ese instrumento estaba
abierto, usando su calendario real: feriados, cambio de hora, pausa de almuerzo,
cierre anticipado y horario del proveedor.

- **0 minutos de mercado** → pausa normal del calendario (no falta un dato).
- **1 minuto o más** → posible falta de datos con mercado abierto.

El conteo se hace sobre minutos de mercado, no sobre tiempo de reloj, para no
confundir fines de semana, feriados o pausas con datos perdidos. Se cuentan solo
las temporalidades de 1m, 5m, 15m, 1h y 4h: en diario no existe aviso porque cada
sesión es un solo cierre y el cierre se compara con el de la fuente.

Resultado: **87 pausas normales** y **2717 posibles faltas con mercado abierto**.

### Posibles faltas por sección

| Sección | Avisos |
| --- | ---: |
| argentina | 2441 |
| smallcaps | 164 |
| metales | 96 |
| equity | 9 |
| sin sección | 7 |

Total: **2717**.

### Posibles faltas por temporalidad

| Temporalidad | Avisos | Minutos faltantes: mediana | máximo |
| --- | ---: | ---: | ---: |
| 1m | 2423 | 1 | 28 |
| 5m | 266 | 5 | 35 |
| 15m | 28 | 15 | 30 |

**Daily: 0 avisos. 4h: 0 avisos.** Ninguna posible falta afecta a la escala que
usa el régimen diario ni a la que usa la cointegración.

La mediana de un minuto perdido por vela indica que el caso habitual es una vela
ausente aislada, no un tramo perdido. Argentina concentra la mayoría porque sus
series locales y ADR son poco líquidas y el proveedor entrega historia parcial.

### Activos con más avisos

| Activo | Avisos |
| --- | ---: |
| PAM | 684 |
| CEPU | 525 |
| BMA | 371 |
| BMA.BA | 249 |
| CEPU.BA | 225 |
| GGAL | 207 |
| YPF | 145 |
| IWN | 87 |
| IWO | 76 |
| PL=F | 67 |
| HG=F | 22 |
| PAMP.BA | 19 |
| GGAL.BA | 14 |
| SI=F | 7 |
| RTY=F | 4 |

## 2. Velas modificadas por la actualización

Se comparó la base actual con el respaldo previo: **154 filas cambiaron** en
apertura, máximo, mínimo, cierre, volumen o fuente.

| Dimensión | Reparto |
| --- | --- |
| Por temporalidad | 1h: 70, 4h: 28, 1D: 22, 15m: 13, 5m: 13, 1m: 8 |
| Por sección | sin sección: 72, cripto: 36, equity: 23, indices: 15, smallcaps: 8 |
| Campos | volume: 140, close: 71, low: 35, open: 30, high: 11 |

### Mayor diferencia de cierre por activo y temporalidad

| Sección | Activo | tf | Filas | Mayor variación | Antes → Después | Fecha | Registro |
| --- | --- | --- | ---: | ---: | --- | --- | --- |
| cripto | BNB/USDT | 15m | 1 | -0.14% | 795.5 → 794.39 | 2026-10-05 03:30:00+0000 | sí |
| cripto | BNB/USDT | 1D | 1 | -1.15% | 795.54 → 786.43 | 2026-10-05 00:00:00+0000 | sí |
| cripto | BNB/USDT | 1h | 1 | -0.43% | 795.54 → 792.15 | 2026-10-05 03:00:00+0000 | sí |
| cripto | BNB/USDT | 1m | 1 | +0.01% | 795.4 → 795.51 | 2026-10-05 03:41:00+0000 | sí |
| cripto | BNB/USDT | 4h | 1 | -0.43% | 795.54 → 792.15 | 2026-10-05 00:00:00+0000 | sí |
| cripto | BNB/USDT | 5m | 1 | -0.14% | 795.51 → 794.39 | 2026-10-05 03:40:00+0000 | sí |
| cripto | BTC/USDT | 15m | 1 | -0.06% | 86309.29 → 86260.01 | 2026-10-05 03:30:00+0000 | sí |
| cripto | BTC/USDT | 1D | 1 | -0.63% | 86309.29 → 85766.87 | 2026-10-05 00:00:00+0000 | sí |
| cripto | BTC/USDT | 1h | 1 | -0.26% | 86309.29 → 86085.03 | 2026-10-05 03:00:00+0000 | sí |
| cripto | BTC/USDT | 1m | 1 | -0.02% | 86309.29 → 86290.01 | 2026-10-05 03:41:00+0000 | sí |
| cripto | BTC/USDT | 4h | 1 | -0.26% | 86309.29 → 86085.03 | 2026-10-05 00:00:00+0000 | sí |
| cripto | BTC/USDT | 5m | 1 | -0.06% | 86309.28 → 86260.01 | 2026-10-05 03:40:00+0000 | sí |
| cripto | ETH/USDT | 15m | 1 | -0.06% | 2723.79 → 2722.27 | 2026-10-05 03:30:00+0000 | sí |
| cripto | ETH/USDT | 1D | 1 | -0.50% | 2723.49 → 2709.98 | 2026-10-05 00:00:00+0000 | sí |
| cripto | ETH/USDT | 1h | 1 | -0.27% | 2723.49 → 2716.16 | 2026-10-05 03:00:00+0000 | sí |
| cripto | ETH/USDT | 1m | 1 | -0.01% | 2724.01 → 2723.82 | 2026-10-05 03:41:00+0000 | sí |
| cripto | ETH/USDT | 4h | 1 | -0.27% | 2723.49 → 2716.16 | 2026-10-05 00:00:00+0000 | sí |
| cripto | ETH/USDT | 5m | 1 | -0.06% | 2723.93 → 2722.27 | 2026-10-05 03:40:00+0000 | sí |
| cripto | HYPE/USDT | 15m | 1 | -0.25% | 90.82 → 90.59 | 2026-10-05 03:30:00+0000 | sí |
| cripto | HYPE/USDT | 1D | 1 | +3.71% | 90.82 → 94.19 | 2026-10-05 00:00:00+0000 | sí |
| cripto | HYPE/USDT | 1h | 1 | -0.48% | 90.82 → 90.38 | 2026-10-05 03:00:00+0000 | sí |
| cripto | HYPE/USDT | 1m | 1 | +0.00% | 90.82 → 90.82 | 2026-10-05 03:41:00+0000 | sí |
| cripto | HYPE/USDT | 4h | 1 | -0.48% | 90.82 → 90.38 | 2026-10-05 00:00:00+0000 | sí |
| cripto | HYPE/USDT | 5m | 1 | -0.25% | 90.82 → 90.59 | 2026-10-05 03:40:00+0000 | sí |
| cripto | SOL/USDT | 15m | 1 | -0.07% | 120.84 → 120.75 | 2026-10-05 03:30:00+0000 | sí |
| cripto | SOL/USDT | 1D | 1 | -0.05% | 120.84 → 120.78 | 2026-10-05 00:00:00+0000 | sí |
| cripto | SOL/USDT | 1h | 1 | -0.33% | 120.84 → 120.44 | 2026-10-05 03:00:00+0000 | sí |
| cripto | SOL/USDT | 1m | 1 | +0.02% | 120.84 → 120.87 | 2026-10-05 03:41:00+0000 | sí |
| cripto | SOL/USDT | 4h | 1 | -0.33% | 120.84 → 120.44 | 2026-10-05 00:00:00+0000 | sí |
| cripto | SOL/USDT | 5m | 1 | -0.07% | 120.84 → 120.75 | 2026-10-05 03:40:00+0000 | sí |
| cripto | XRP/USDT | 15m | 1 | -0.03% | 1.5146 → 1.5141 | 2026-10-05 03:30:00+0000 | sí |
| cripto | XRP/USDT | 1D | 1 | -0.48% | 1.515 → 1.5077 | 2026-10-05 00:00:00+0000 | sí |
| cripto | XRP/USDT | 1h | 1 | -0.22% | 1.5146 → 1.5112 | 2026-10-05 03:00:00+0000 | sí |
| cripto | XRP/USDT | 1m | 1 | +0.05% | 1.5149 → 1.5156 | 2026-10-05 03:41:00+0000 | sí |
| cripto | XRP/USDT | 4h | 1 | -0.25% | 1.515 → 1.5112 | 2026-10-05 00:00:00+0000 | sí |
| cripto | XRP/USDT | 5m | 1 | -0.04% | 1.5147 → 1.5141 | 2026-10-05 03:40:00+0000 | sí |
| equity | AAPL | 1D | 1 | +0.00% | 333.69000244140625 → 333.69000244140625 | 2026-10-02 04:00:00+0000 | sí |
| equity | AAPL | 1h | 1 | +0.00% | 333.7900085449219 → 333.7900085449219 | 2026-10-02 19:30:00+0000 | sí |
| equity | AAPL | 4h | 1 | +0.00% | 333.7900085449219 → 333.7900085449219 | 2026-10-02 17:30:00+0000 | no |
| equity | AMZN | 1D | 1 | +0.00% | 251.52000427246094 → 251.52000427246094 | 2026-10-02 04:00:00+0000 | sí |
| equity | AMZN | 1h | 1 | +0.00% | 251.52999877929688 → 251.52999877929688 | 2026-10-02 19:30:00+0000 | sí |
| equity | AMZN | 4h | 1 | +0.00% | 251.52999877929688 → 251.52999877929688 | 2026-10-02 17:30:00+0000 | no |
| equity | GOOGL | 1D | 1 | +0.00% | 343.5 → 343.5 | 2026-10-02 04:00:00+0000 | sí |
| equity | GOOGL | 5m | 1 | +0.00% | 343.5899963378906 → 343.5899963378906 | 2026-10-02 19:55:00+0000 | sí |
| equity | META | 1D | 1 | +0.00% | 728.0800170898438 → 728.0800170898438 | 2026-10-02 04:00:00+0000 | sí |
| equity | MSFT | 1D | 1 | +0.00% | 517.530029296875 → 517.530029296875 | 2026-10-02 04:00:00+0000 | sí |
| equity | MSFT | 5m | 1 | +0.00% | 517.8599853515625 → 517.8599853515625 | 2026-10-02 19:55:00+0000 | sí |
| equity | NVDA | 1D | 1 | +0.00% | 233.9499969482422 → 233.9499969482422 | 2026-10-02 04:00:00+0000 | sí |
| equity | TSLA | 15m | 1 | +0.00% | 370.70001220703125 → 370.70001220703125 | 2026-10-02 19:45:00+0000 | sí |
| equity | TSLA | 1D | 1 | +0.00% | 370.5899963378906 → 370.5899963378906 | 2026-10-02 04:00:00+0000 | sí |
| equity | XLF | 1D | 1 | +0.00% | 53.4900016784668 → 53.4900016784668 | 2026-10-02 04:00:00+0000 | sí |
| equity | XLK | 1h | 1 | +0.00% | 199.86000061035156 → 199.86000061035156 | 2026-10-02 19:30:00+0000 | sí |
| equity | XLK | 4h | 1 | +0.00% | 199.86000061035156 → 199.86000061035156 | 2026-10-02 17:30:00+0000 | no |
| equity | XLU | 15m | 1 | +0.00% | 39.81999969482422 → 39.81999969482422 | 2026-10-02 19:45:00+0000 | sí |
| equity | XLU | 1D | 1 | +0.00% | 39.83000183105469 → 39.83000183105469 | 2026-10-02 04:00:00+0000 | sí |
| equity | XLY | 15m | 1 | +0.00% | 110.04000091552734 → 110.04000091552734 | 2026-10-02 19:45:00+0000 | sí |
| equity | XLY | 1h | 1 | +0.00% | 110.04000091552734 → 110.04000091552734 | 2026-10-02 19:30:00+0000 | sí |
| equity | XLY | 4h | 1 | +0.00% | 110.04000091552734 → 110.04000091552734 | 2026-10-02 17:30:00+0000 | no |
| equity | XLY | 5m | 1 | +0.00% | 110.04000091552734 → 110.04000091552734 | 2026-10-02 19:55:00+0000 | sí |
| indices | ^DJI | 4h | 3 | +0.00% | 51404.0 → 51404.0 | 2026-10-05 04:00:00+0000 | no |
| indices | ^GSPC | 4h | 5 | +0.00% | 7814.25 → 7814.5 | 2026-10-05 12:00:00+0000 | no |
| indices | ^N225 | 1D | 1 | -0.13% | 70037.609375 → 69946.859375 | 2026-10-04 15:00:00+0000 | sí |
| indices | ^N225 | 4h | 1 | -0.41% | 70037.609375 → 69753.78125 | 2026-10-05 00:00:00+0000 | sí |
| indices | ^NDX | 4h | 2 | +0.00% | 31060.0 → 31060.0 | 2026-10-05 04:00:00+0000 | no |
| indices | ^RUT | 4h | 3 | +0.00% | 2847.5 → 2847.5 | 2026-10-05 04:00:00+0000 | no |
| sin sección | ES=F | 1D | 1 | -0.10% | 7834.0 → 7826.25 | 2026-10-05 04:00:00+0000 | sí |
| sin sección | ES=F | 1h | 19 | -0.01% | 7834.0 → 7833.5 | 2026-10-06 03:00:00+0000 | no |
| sin sección | NQ=F | 1D | 1 | -0.10% | 31347.75 → 31317.75 | 2026-10-05 04:00:00+0000 | sí |
| sin sección | NQ=F | 1h | 15 | +0.00% | 31040.0 → 31041.0 | 2026-10-05 06:00:00+0000 | sí |
| sin sección | QQQ | 15m | 1 | -0.01% | 756.1500244140625 → 756.0999755859375 | 2026-10-05 19:45:00+0000 | sí |
| sin sección | QQQ | 1D | 1 | +0.00% | 756.2000122070312 → 756.2000122070312 | 2026-10-05 04:00:00+0000 | sí |
| sin sección | QQQ | 1h | 1 | -0.01% | 756.1500244140625 → 756.0999755859375 | 2026-10-05 19:30:00+0000 | sí |
| sin sección | QQQ | 1m | 1 | -0.01% | 756.1500244140625 → 756.0999755859375 | 2026-10-05 19:59:00+0000 | sí |
| sin sección | QQQ | 4h | 1 | -0.01% | 756.1500244140625 → 756.0999755859375 | 2026-10-05 17:30:00+0000 | no |
| sin sección | QQQ | 5m | 1 | -0.01% | 756.1500244140625 → 756.0999755859375 | 2026-10-05 19:55:00+0000 | sí |
| sin sección | RTY=F | 1D | 1 | -0.00% | 2867.89990234375 → 2867.800048828125 | 2026-10-05 04:00:00+0000 | sí |
| sin sección | RTY=F | 1h | 12 | +0.00% | 2846.89990234375 → 2847.0 | 2026-10-05 09:00:00+0000 | sí |
| sin sección | SPY | 15m | 1 | +0.00% | 774.9400024414062 → 774.9400024414062 | 2026-10-05 19:45:00+0000 | sí |
| sin sección | SPY | 1D | 1 | +0.00% | 774.8300170898438 → 774.8300170898438 | 2026-10-05 04:00:00+0000 | sí |
| sin sección | SPY | 1h | 1 | +0.00% | 774.9400024414062 → 774.9400024414062 | 2026-10-05 19:30:00+0000 | sí |
| sin sección | SPY | 1m | 1 | +0.00% | 774.9400024414062 → 774.9400024414062 | 2026-10-05 19:59:00+0000 | sí |
| sin sección | SPY | 4h | 1 | +0.00% | 774.9400024414062 → 774.9400024414062 | 2026-10-05 17:30:00+0000 | no |
| sin sección | SPY | 5m | 1 | +0.00% | 774.9400024414062 → 774.9400024414062 | 2026-10-05 19:55:00+0000 | sí |
| sin sección | YM=F | 1D | 1 | -0.18% | 51652.0 → 51558.0 | 2026-10-05 04:00:00+0000 | sí |
| sin sección | YM=F | 1h | 10 | -0.05% | 51652.0 → 51627.0 | 2026-10-06 03:00:00+0000 | no |
| smallcaps | IJR | 15m | 1 | +0.01% | 138.52999877929688 → 138.5399932861328 | 2026-10-02 19:45:00+0000 | sí |
| smallcaps | IJR | 1h | 1 | +0.01% | 138.52999877929688 → 138.5399932861328 | 2026-10-02 19:30:00+0000 | sí |
| smallcaps | IJR | 4h | 1 | +0.01% | 138.52999877929688 → 138.5399932861328 | 2026-10-02 17:30:00+0000 | no |
| smallcaps | IJR | 5m | 1 | +0.01% | 138.52999877929688 → 138.5399932861328 | 2026-10-02 19:55:00+0000 | sí |
| smallcaps | IWM | 15m | 1 | +0.00% | 281.4700012207031 → 281.4700012207031 | 2026-10-02 19:45:00+0000 | sí |
| smallcaps | IWM | 1h | 1 | +0.00% | 281.4700012207031 → 281.4700012207031 | 2026-10-02 19:30:00+0000 | sí |
| smallcaps | IWM | 4h | 1 | +0.00% | 281.4700012207031 → 281.4700012207031 | 2026-10-02 17:30:00+0000 | no |
| smallcaps | IWM | 5m | 1 | +0.00% | 281.4700012207031 → 281.4700012207031 | 2026-10-02 19:55:00+0000 | sí |

### Registro de correcciones

- Filas con corrección registrada en `candle_corrections`: **129**.
- Filas modificadas sin registro: **25** (4h: 21, 1h: 4).
- La diferencia es esperada y está documentada en `src/data/audit.py`:
  `_record_correction` no cuenta la finalización normal de una vela provisional.
  Las filas de 4h y las de futuros de 1h que aparecen arriba son cierres de velas
  que estaban abiertas; la mayoría solo cambia el volumen y conserva el cierre.
- Ninguna fila sin registro modifica un cierre histórico de forma relevante.

### ¿Alguna es un split mal ajustado?

Filas con variación de cierre de 10% o más: **0**.
Máxima variación observada: **3.71%**
(HYPE/USDT diario del 2026-10-05, de 90,82 a 94,19).

No hay ninguna razón de tipo split (2, 3, 1/3 o similar) ni saltos de magnitud
compatible con un ajuste de acciones. Los cambios grandes están en volumen
(140 de 154 filas), que es el campo que más se revisa al recalcular una vela.

### ¿Alguna es de diario?

Sí: **22 filas de 1D** y **28 de 4h**. Las de diario son recifras
del proveedor sobre cierres ya cerrados; la mayor es +3,71% y la menor
−1,15%. Ninguna afecta al régimen diario de forma estructural.
