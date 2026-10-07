# Corrección aprobada de 4h — auditoría, series y fotos

## Respaldo anterior

- Fecha: **2026-10-06 16:14:56,548 UTC**.
- Tamaño del ZIP anterior registrado: **88,73 MB**.
- Archivo original: `finance_20261006T161456.548276Z.zip`.
- Contenido: **2.760.987 velas**, integridad `ok`, último dato
  `2026-10-06 03:10:00 UTC`.
- Su contenido anterior se restauró fuera del proyecto para comparar. Se
  conservó también en `backups/before_four_hour/`, separado de la retención
   ordinaria para que una copia nueva del mismo día no quite el punto anterior.
- Copia preservada del contenido anterior:
  `backups/before_four_hour/daily/finance_20261006T173327.206408Z.zip`.
  Su nombre corresponde al momento de preservación; la base dentro es la anterior.

## Auditoría de todos los activos (datos guardados, no supuestos)

`python audit_four_hours.py` imprime minutos, cantidades, fechas excepcionales
y aperturas nominales que cruzan límites UTC. Las referencias FRED no tienen
velas horarias: no se les atribuye un minuto de negociación.

| Sección | Activo | Apertura 1h observada | Situación |
|---|---|---|---|
| Índices | ^NDX | :30 | Cambia a NQ=F en 4h |
| Índices | ^GSPC | :30 | Cambia a ES=F en 4h |
| Índices | ^DJI | :30 | Cambia a YM=F en 4h |
| Índices | ^RUT | :30 | Cambia a RTY=F en 4h |
| Índices | ^GDAXI | :00 | Sin cambio de serie |
| Índices | ^N225 | :00 | Sin cambio de serie |
| Metales | GC=F | :00 y 20 horas :30 | Conservar; excepción conocida |
| Metales | SI=F | :00 y 20 horas :30 | Conservar; excepción conocida |
| Metales | HG=F | :00 y 20 horas :30 | Conservar; excepción conocida |
| Metales | PL=F | :00 y 20 horas :30 | Conservar; excepción conocida |
| Equity | XLK | :30 | 4h de sesión NY |
| Equity | XLF | :30 | 4h de sesión NY |
| Equity | XLE | :30 | 4h de sesión NY |
| Equity | XLV | :30 | 4h de sesión NY |
| Equity | XLY | :30 | 4h de sesión NY |
| Equity | XLP | :30 | 4h de sesión NY |
| Equity | XLI | :30 | 4h de sesión NY |
| Equity | XLB | :30 | 4h de sesión NY |
| Equity | XLU | :30 | 4h de sesión NY |
| Equity | XLRE | :30 | 4h de sesión NY |
| Equity | XLC | :30 | 4h de sesión NY |
| Equity | AAPL | :30 | 4h de sesión NY |
| Equity | MSFT | :30 | 4h de sesión NY |
| Equity | NVDA | :30 | 4h de sesión NY |
| Equity | GOOGL | :30 | 4h de sesión NY |
| Equity | AMZN | :30 | 4h de sesión NY |
| Equity | META | :30 | 4h de sesión NY |
| Equity | TSLA | :30 | 4h de sesión NY |
| Small caps | IWM | :30 | 4h de sesión NY |
| Small caps | IJR | :30 | 4h de sesión NY |
| Small caps | IWO | :30 | 4h de sesión NY |
| Small caps | IWN | :30 | 4h de sesión NY |
| Cripto | BTC/USDT | :00 | Fuente nativa, sin cambio |
| Cripto | ETH/USDT | :00 | Fuente nativa, sin cambio |
| Cripto | SOL/USDT | :00 | Fuente nativa, sin cambio |
| Cripto | XRP/USDT | :00 | Fuente nativa, sin cambio |
| Cripto | HYPE/USDT | :00 | Bybit, sin cambio |
| Cripto | BNB/USDT | :00 | Fuente nativa, sin cambio |
| Argentina | GGAL.BA | :00 | Sin cambio de serie |
| Argentina | GGAL | :30 | 4h de sesión NY |
| Argentina | YPFD.BA | :00 | Sin cambio de serie |
| Argentina | YPF | :30 | 4h de sesión NY |
| Argentina | PAMP.BA | :00 | Sin cambio de serie |
| Argentina | PAM | :30 | 4h de sesión NY |
| Argentina | BMA.BA | :00 | Sin cambio de serie |
| Argentina | BMA | :30 | 4h de sesión NY |
| Argentina | CEPU.BA | :00 | Sin cambio de serie |
| Argentina | CEPU | :30 | 4h de sesión NY |
| FRED | DGS10, DGS2, T10Y2Y, DFII10, VIXCLS, DTWEXBGS, BAMLH0A0HYM2 | Sin 1h | Series económicas, no velas |

Los 20 casos :30 de cada metal ocurren en **2024-11-29, 2024-12-24,
2025-07-03, 2025-11-28 y 2025-12-24**. No se afirmó que eran uniformes a :00.
No se puede dividir exactamente su OHLC horario en un límite que atraviesa la
hora; se conserva el dato y se registra el aviso, sin fabricar precios.

También se incorporaron QQQ, SPY y DIA (referencias fuera de assets.yaml) al
método de sesión. IWM ya estaba incluido en Small caps.

## Método activo y conservación

- `4h_legacy`: conserva íntegramente las 4h originales, con sus fuentes y horas.
- `four_hour_archives`: conserva generaciones activas reemplazadas y resultados
  anteriores de régimen/z/pares. Se archiva **antes** de reemplazar; una falla
  de construcción no borra la serie que había. Repetir la reconstrucción con
  los mismos datos no duplica legacy ni aumenta una revisión sin cambios.
- `four_hour_series`: versión, método, instrumento real, zona, aperturas,
  dependencia de las horas y calidad de cada serie activa.
- Índices estadounidenses: precios/volumen de NQ/ES/YM/RTY, armados **desde 1h**
  en bloques UTC (horario configurado, todavía provisional).
- ETF/acciones/ADR estadounidenses: **09:30–13:30 y 13:30–16:00 Nueva York**,
  desde horas. La segunda dura 2,5 horas. Se respeta el cambio de hora y un
  cierre anticipado; en una media rueda no se inventa una segunda vela.
- No se usó 1m/5m/15m para esta reconstrucción. Una hora faltante o que cruza un
  límite se omite y se avisa; no se asigna por adivinación.
- El actualizador mantiene estos métodos, en vez de volver a sobrescribirlos
  con el resample antiguo de Yahoo.

Las series reconstruidas tienen aproximadamente **3.051 velas** de futuros
para índices y **990–991 de sesión** para acciones/ETF/ADR (987 para QQQ/SPY/DIA),
con casi dos años de cobertura. No quedan limitadas a 60 días.

Para el percentil de ATR se requieren **250 ATR válidos**. ATR14 deja 13 valores
iniciales sin cálculo: la protección requiere al menos **263 velas**, no 250
totales. También comprueba que la ventana tenga ATR y precios válidos; no cuenta
como nueva observación un ATR arrastrado por un precio ausente. Si falta historia,
dirección=sin datos, régimen=**Historia insuficiente
en 4h**, z/percentiles no disponibles; no cuenta como una escala alineada.

## Fotos: marca 4h sin reescribir las antiguas

Las nuevas fotos usan formato 2 y cada activo/4h guarda `series_4h` con la
versión usada por el resultado, método, referencia, zona, aperturas y
dependencias. El rótulo de los índices es **Nasdaq 100 (vía NQ=F)** y equivalentes.

Las fotos previas siguen con su JSON original; al leerlas se muestra **4h antigua**.
La marca se muestra en la lista, cabecera de foto y desplegable de versiones.
No se recalculó ni se completó retrospectivamente una foto antigua.

## Campos que realmente guardan hoy las fotos (sin añadir los faltantes)

**Cabecera:** id, created_at, machine, trigger, status, late, app_version,
params_hash, tfs_scope, errors. `schema_version` y marca de formato 4h dentro
del contenido. Ojo: hay hash de parámetros, **no copia íntegra de parámetros**;
el código anterior cargaba calc.yaml pero no lo incorporaba al JSON.

**Todas las seis secciones:**
- `assets[]`: symbol, timeframes, z_atr_1d, z_std_1d, z_percentile_1d, last_data.
- `timeframes[tf]`: direction, regime, last_data, calculated_at, para cada
  temporalidad que tenía un resultado guardado. En 4h se agregan únicamente
  los campos aprobados de versión/rotulado (`series_4h`, `display_name`).
- `pairs[]`: pair, name, betas por TF, states por TF, p_values por TF, last_data.
- `macro[]`: series, value, change_1m, percentile, last_data. Actualmente se
  guarda la misma lista macro en cada sección, no solo sus destacadas.
- `direction_counts`: conteos de direcciones sobre activos **y escalas**,
  no el conteo diario de activos; no confundirlo con el KPI diario.

| Sección | Extras que se guardan hoy |
|---|---|
| Índices | top_relative_20d, most_stretched_1d, most_aligned_up_count, most_aligned |
| Metales | No se guarda aparte el ratio Oro/Plata |
| Equity | No se guarda aparte el mapa de calor |
| Small caps | No se guarda aparte la fuerza relativa IWM/S&P |
| Cripto | No se guardan aparte ETH/BTC y SOL/BTC |
| Argentina | ccl.median y ccl.companies; no CCL individual/z/percentil |

**Respuesta precisa:** sí se guardan dirección y régimen de las seis escalas
**si existía resultado para ellas**; no se crea una casilla explícita de error
para una escala ausente. **No se guarda alineación por activo en seis escalas.
La distancia solo se guarda como z diario; no guarda distancias por TF ni VWAP,
bandas, precio de referencia o sesión de cada lectura.**

Además, los extras antiguos de Índices no reproducen exactamente C2: el líder
se eligió por rendimiento propio, el más alejado por z-ATR y la alineación solo
por conteo alcista, sin el filtro calendario del piloto.

**Propuesta, SIN IMPLEMENTAR:** nueva versión de foto con matriz explícita de
6 escalas por activo, alineación y débiles/disponibles, distancia/%/unidad por
TF, VWAP y bandas del instrumento real, sesión, errores, parámetros completos,
KPIs exactos de C2 y CCL de cada empresa más mediana/z/percentil. Mantener
lectura de versiones anteriores sin completar con datos de hoy. Este trabajo
queda pendiente de aprobación; solo se añadió la versión 4h solicitada.

## Foto diaria a las 21:15 Buenos Aires: comandos exactos (no activada)

La tarea comprueba cada minuto si venció la hora, pero descarga/calcula/fotografía
**solo una vez por hora diaria vencida**. Esto evita depender de la zona horaria
de Mac/Windows. Si vuelve del apagado, atiende la última vencida y toma una foto
real ahora, marcada tardía; no crea una foto por cada horario perdido.

### Mac (desde la carpeta del proyecto)

```bash
source .venv/bin/activate
python install_daily_backup.py --hora 21:15 --zona America/Argentina/Buenos_Aires --instalar
launchctl print "gui/$(id -u)/com.dashboard-finance.backup"
```

Comprobar ProgramArguments con daily_run.py, `--scheduled` y la zona Buenos Aires;
revisar `backups/logs/backup-daily.log` y `backup-daily-errors.log`, y la foto
diaria real en Historial. Al iniciar sesión corre la comprobación y, al despertar,
se vuelve a comprobar. Requiere equipo encendido y usuario conectado.

### Windows (PowerShell, desde la carpeta del proyecto)

```powershell
.venv\Scripts\python.exe install_daily_backup.py --hora 21:15 --zona America/Argentina/Buenos_Aires --instalar
schtasks /Query /TN DashboardFinanceRespaldoDiario /V /FO LIST
schtasks /Run /TN DashboardFinanceRespaldoDiario
```

Comprobar tarea habilitada, ruta de Python del entorno y argumentos daily_run.py
con `--scheduled`/zona. El botón Ejecutar verifica el vencimiento: si no hay hora
pendiente, no descarga ni crea otra foto. StartWhenAvailable está habilitado;
al volver/login se atenderá el último vencimiento. Requiere usuario conectado.

Para ver el horario SIN activar, descargar ni crear foto:

```bash
python daily_run.py --scheduled --hora 21:15 --zona America/Argentina/Buenos_Aires --dry-run
```

No se ejecutó `--instalar` en esta entrega. Instalar solo en la máquina
principal elegida. La definición Windows se prueba como XML; su ejecución
nativa debe comprobarse en la PC al instalar.

## Validación

1. Elegir 4h de Nasdaq: ver **Nasdaq 100 (vía NQ=F)** y datos del futuro, no
   precio del índice mezclado con volumen ajeno.
2. En acciones/ETF/ADR, comprobar aperturas 09:30/13:30 NY y la segunda más corta.
3. Revisar **Método y versión de la 4h** en las pestañas, y calidad del piloto.
4. Una foto antigua conserva números y marca 4h antigua. Una nueva muestra
   versiones por activo; abrir/cambiar selectores no crea fotos.
5. Las fuentes sin cambios conservan precios; las excepciones de metales están
   informadas, no se fabricó una división de sus horas.

```bash
python test_four_hour.py
python test_four_hour_app.py
python test_c2.py
python test_c1.py
python test_c0.py
python test_c3.py
python test_synthetic.py
```

No se replicó el diseño del piloto a otras pestañas. Esperar confirmación.

### Resultado del cierre (7 de octubre de 2026)

- Integridad de la base anterior y de la activa: **ok**.
- **34 series originales** conservadas íntegramente como `4h_legacy`, incluyendo
  precios, volumen, fuente, timestamps y recepción; **21 series 4h sin cambios**.
- **48 activos**: el último régimen, ADX, percentil de ATR, z-ATR, z-estándar,
  percentil de z, fecha y versión guardados coinciden con el cálculo de la 4h activa.
- Salud de los **613 resultados** guardados: versiones de precios y parámetros
  comprobados; incluye **106 resultados de 4h**.
- DAX y los cuatro metales se recalcularon tras corregir la lectura de las velas
  UTC que empiezan antes de la apertura. Sus precios no fueron reconstruidos.
- La base anterior no contenía fotos reales. La conservación de JSON antiguo se
  comprobó con una foto de prueba; no se afirma haber comparado fotos inexistentes.
- La prueba de interfaz usa una copia SQLite: selecciona 4h en las seis pestañas,
  Nasdaq vía futuro, Apple, IWM y un ADR; abre una foto versionada y cambia Nasdaq
  a QQQ. Cambiar selectores no agrega fotos ni modifica la foto de prueba.
- La programación diaria se probó sin instalarla: evita duplicar una hora vencida
  y marca tardía una foto si la propia actualización tarda más de 30 minutos.
- **76 comprobaciones correctas**: 16 de corrección 4h/programación/fotos,
  1 de integración de interfaz e historial, 22 de C0, 7 de C1, 20 de C2,
  5 de C3 y 5 sintéticas. `git diff --check` también pasó.

Para repetir la comprobación de conservación y cálculos sin escribir datos:

```bash
python verify_four_hours.py --before "ruta/base_anterior_restaurada.db"
```

## Antes/después medido (10 activos)

| Activo | Velas antes → ahora | Última dirección antes → ahora | Dirección histórica cambia | Régimen completo cambia |
|---|---:|---|---:|---:|
| Nasdaq vía NQ | 1159 → 3051 | Alcista débil → alcista | 48,24% | 76,51% |
| S&P vía ES | 1159 → 3051 | Lateral → alcista | 49,53% | 74,40% |
| Dow vía YM | 1159 → 3051 | Bajista → lateral | 49,98% | 74,97% |
| Russell vía RTY | 1159 → 3056 | Bajista → alcista | 48,16% | 72,69% |
| Tecnología XLK | 1159 → 991 | Alcista débil → alcista débil | 20,30% | 39,78% |
| Apple AAPL | 1159 → 991 | Lateral → lateral | 13,44% | 38,82% |
| Microsoft MSFT | 1159 → 991 | Alcista débil → alcista débil | 12,21% | 35,12% |
| Amazon AMZN | 1159 → 991 | Lateral → bajista | 15,91% | 41,29% |
| Pequeñas empresas IWM | 1159 → 991 | Bajista → bajista | 14,81% | 41,56% |
| Crecimiento IWO | 1159 → 991 | Bajista → bajista | 17,56% | 46,36% |

Los métodos producen distinto número de barras y aperturas. El porcentaje no
compara filas por posición: en cada cierre nuevo del período común se toma
la última etiqueta antigua disponible, sin información futura; se excluye el
calentamiento de 250 ATR válidos. “Dirección” cuenta alcista/bajista/débil/lateral;
“régimen completo” incluye además baja/normal/alta volatilidad.
En índices también cambia el instrumento y se agrega negociación nocturna:
el porcentaje no se atribuye solo a corregir 30 minutos. El cierre más reciente
antiguo es 2-oct-2026 y el del futuro usado ahora llega a 5-oct-2026; por eso se
muestran períodos y fechas en el informe del comando, en vez de fingir misma
vela final. Los porcentajes históricos usan solo la cobertura común.

```bash
python compare_four_hours.py --before "ruta/base_anterior_restaurada.db"
```

Los activos cuya serie no cambió (DAX, Nikkei, metales, cripto y acciones locales
argentinas) dieron 0% de cambio histórico en esta comparación de métodos.
