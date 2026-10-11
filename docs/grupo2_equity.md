# Grupo 2: ajustes de Cripto y piloto Equity

## Primera etapa: ajustes de Cripto verificados

- Bloque de 1h: 1000 velas.
- Bloque de 4h y 1D: 500 velas.
- Ventanas principal y contraste conservadas: 500 y 1000 cierres; no se confundió tamaño de bloque con ventana del test.
- Se evaluaron todos los bloques completos sin solape y se informa cantidad evaluada, confirmada y porcentaje del total.
- El estado reciente conserva el tramo de los últimos 5 bloques; la evidencia antigua no cambia ese estado.
- Solana se evalúa desde 4 bloques solo cuando tiene menos de 5, exige 4 confirmados para el estado máximo «Estable (provisional)» y siempre muestra historia limitada.
- Una prueba inválida no se cuenta como «sin relación»: se informa la cantidad inválida y no se fabrica un porcentaje completo.
- Pruebas aprobadas en esta etapa: 97; sin omisiones.
- Índices: 4328 elementos comparados; 0 diferencias.
- Metales: 3631 elementos comparados; 0 diferencias.
- Cripto: 3872 elementos comparados; 141 diferencias intencionales. Fuera de cointegración y de sus parámetros/textos explícitamente modificados: 3601 elementos; 0 diferencias.
- BTC/ETH 1h: «sin relación», 2 confirmados de 79 bloques; 2,5%, todos evaluados; últimos 5: 0 confirmados.
- ETH/SOL 1h: «intermitente», 2 confirmados de 53 bloques; 3,8%, todos evaluados; últimos 5: 1 confirmado.
- BTC/SOL 1h: «intermitente», 2 confirmados de 53 bloques; 3,8%, todos evaluados; últimos 5: 0 confirmados.
- BTC/ETH diario: «intermitente», 1 confirmado de 6 bloques; 16,7%, todos evaluados.
- ETH/SOL diario: «intermitente», 0 confirmados de 4 bloques; historia limitada visible.
- BTC/SOL diario: «sin relación», 0 confirmados de 4 bloques; historia limitada visible.

La primera carga de C1 agotó su timeout. La repetición con el límite original
pasó y la corrida completa posterior pasó también; no se omitió AppTest ni se
relajaron sus comprobaciones. La consulta `daily_run.py --dry-run` pasó, sin
instalar ni activar ninguna tarea.

## Comando de instalación manual — no ejecutado por el agente

Ejecutar desde la carpeta raíz del proyecto, con las dependencias instaladas
en el entorno virtual. El instalador detecta Mac o Windows y programa
`daily_run.py`, que hace respaldo, descarga, cálculos y foto.

Mac:

```bash
.venv/bin/python install_daily_backup.py --hora 21:15 --zona America/Argentina/Buenos_Aires --instalar
```

Windows, PowerShell:

```powershell
.\.venv\Scripts\python.exe .\install_daily_backup.py --hora 21:15 --zona America/Argentina/Buenos_Aires --instalar
```

Comprobación Mac:

```bash
launchctl print "gui/$(id -u)/com.dashboard-finance.backup"
plutil -p "$HOME/Library/LaunchAgents/com.dashboard-finance.backup.plist"
```

Comprobación Windows, PowerShell:

```powershell
Get-ScheduledTask -TaskName "DashboardFinanceRespaldoDiario" | Select-Object TaskName,State
Get-ScheduledTaskInfo -TaskName "DashboardFinanceRespaldoDiario" | Format-List LastRunTime,LastTaskResult,NextRunTime
schtasks /Query /TN "DashboardFinanceRespaldoDiario" /V /FO LIST
```

Qué comprobar:

- La tarea debe existir y estar cargada/habilitada, usando el Python del entorno virtual y `daily_run.py` del proyecto correcto.
- Los argumentos deben contener `--scheduled`, `--hora 21:15`, `--zona America/Argentina/Buenos_Aires` y `--activated-at` con la fecha de instalación.
- El intervalo de comprobación es de 60 segundos. No significa que descargue cada minuto: `daily_run.py` atiende una sola vez cada horario diario vencido.
- La zona elegida define las 21:15; no depende de la zona horaria del equipo.
- En Mac el servicio puede quedar esperando entre comprobaciones. En Windows debe quedar listo/habilitado; la sesión de usuario debe estar iniciada y el equipo encendido.
- Un último resultado 0 demuestra que la comprobación terminó sin error, pero antes del horario puede ser solo una comprobación sin descarga.
- Después del horario debe aparecer una nueva copia en `backups` y una foto con activador `daily` en Historial, con hora real y estado. Si hubo recuperación tardía, se rotula tardía.
- En Mac revisar `backups/logs/backup-daily.log` y `backup-daily-errors.log`.
- En Windows revisar el historial del Programador de tareas y la foto registrada; el XML no redirige stdout a un archivo de log.

Consulta sin descargar ni instalar:

```bash
.venv/bin/python daily_run.py --hora 21:15 --zona America/Argentina/Buenos_Aires --dry-run
```

En Windows sustituir el intérprete por `.\.venv\Scripts\python.exe`.

## Segunda etapa: Equity

La pestaña usa `render_section_pilot`, sin copiar la pantalla. Los sectores se
comparan con el S&P 500 sobre el mismo período común; las tecnológicas se cuentan
por separado. El mapa se ordena por distancia porcentual diaria a la EMA; el
indicador de mayor separación usa esa distancia normalizada por desvío. Sus
ayudas explican ambas unidades.

- Sectores: 11 ETF.
- Grandes tecnológicas: 7 acciones.
- Tabla resumen: 5 columnas, con alineación y antigüedad.
- Ranking relativo: 20 ruedas comunes de todos los sectores y el benchmark.
- Mapa de calor: distancia porcentual a la EMA de 50 cierres por temporalidad.
- Leyenda: verde por encima de la media, rojo por debajo y gris sin historia suficiente; no es una orden de compra o venta.
- Sesión: 09:30–16:00 Nueva York, sin premercado; respeta feriados, cierres anticipados y horario de verano.
- VWAP: precio típico y volumen del mismo ETF o acción, desde las 09:30 de su sesión.
- 1h: reconstruida desde la apertura con velas de cinco minutos.
- 4h de sesión: 09:30–13:30 y 13:30–16:00. La segunda vela puede ser más corta; se usa `session_4h_us`, no la 4h vieja ni premercado.
- Cointegración: solo 1D; en 1h/4h muestra «Historia insuficiente».
- Pares: XLK/XLY y XLF/XLI, tomados de `config/pairs.yaml`.
- Fotos: formato 8 por nuevos campos de Equity; guardan KPIs, ranking sectorial, mapa y política de sesión. Las anteriores no se reescriben.

Se conservan Fuentes y calidad, Glosario, Cómo leer esto y Vista anterior.

## Valores de la corrida final de Equity

Lectura de la base real disponible, **no cotización en vivo**. Los tests usan
copias SQLite y no descargan ni alteran la base productiva. La pantalla informa
la antigüedad y no inventa escalas vigentes para mostrar alineación.

- Captura: 2026-10-11 00:30:43 UTC, equivalente a 2026-10-10 21:30:43 de Buenos Aires.
- Último cierre disponible: 2026-10-02 20:00 UTC.
- Período común: 2026-09-03 a 2026-10-02.
- Sectores que suben: 1 de 11, Tecnología; bajan 7 y son laterales 3.
- Líder frente al S&P 500: Tecnología (XLK), +7,76 puntos porcentuales.
- Rezagado: Financiero (XLF), -8,34 puntos porcentuales.
- Tecnológicas que suben: 4 de 7; Apple, Microsoft, Nvidia y Meta. Las otras 3 están laterales.
- Mayor separación normalizada: Consumo básico (XLP), -1,75 desvíos y -3,68% frente a su media diaria.
- Mapa, distancia diaria: Tecnología +6,40%; Energía +1,48%; Salud -0,59%; Comunicaciones -1,33%; Industrial -2,47%; Consumo discrecional -2,99%; Consumo básico -3,68%; Materiales -4,10%; Financiero -4,26%; Servicios públicos -5,62%; Inmobiliario -5,73%.
- Tasa a diez años: 5,24, dato del 2026-10-01; cambio mensual +0,45.
- Curva diez menos dos años: 0,45, dato del 2026-10-02; cambio mensual +0,05.
- Spread high yield: 3,24, dato del 2026-10-01; cambio mensual +0,59.
- XLK/XLY diario: «sin relación»; confirmó 7,7% de 13 bloques, con 13 evaluados y 1 confirmado. Últimos 5: 0 confirmados.
- XLF/XLI diario: «sin relación»; confirmó 7,7% de 13 bloques, con 13 evaluados y 1 confirmado. Últimos 5: 0 confirmados.
- Historia común de cada par: 6987 cierres, hasta 2026-10-02.
- Alineación: los 18 activos informan falta de escalas vigentes por antigüedad.

El detalle inicial diario muestra precio y medias. En intradía muestra las
velas de sesión, VWAP y bandas del mismo instrumento. Se verificaron XLK y la
vista AAPL de sesión en AppTest; las barras anteriores a apertura y posteriores
al cierre quedan fuera de la vista principal y de su volumen.

## Regresión y pruebas finales

La base previa a Equity es `6769e9e`: ya incluye los ajustes pedidos de Cripto.
Se compara todo el contenido de las tres pestañas previas, con sus desplegables,
ayudas, tablas y trazas. Los cambios deliberados de Cripto se informaron aparte
en la primera etapa. Solo se normalizan antigüedad, hora de cálculo e IDs de
transporte.

- Índices: 4328 elementos comparados; 0 diferencias.
- Metales: 3631 elementos comparados; 0 diferencias.
- Cripto: 3872 elementos comparados; 0 diferencias.
- Sintéticas: 5 aprobadas.
- C0: 22 aprobadas.
- C1: 7 aprobadas.
- C2: 20 aprobadas.
- C3: 5 aprobadas.
- Cuatro horas: 16 aprobadas.
- AppTest de cuatro horas e historial: 1 aprobada.
- Metales: 3 aprobadas.
- Fotos de pilotos: 2 aprobadas.
- Estadísticas de bloques: 5 aprobadas.
- Cripto: 8 aprobadas.
- Equity: 4 aprobadas.
- Regresiones AppTest: 4 aprobadas.
- Total final: 102 aprobadas, sin omisiones.
- AppTest: 6 pestañas, sin excepciones.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  .venv/bin/python -B test_equity.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  .venv/bin/python -B test_equity_regression.py
```

`EQUITY_READING_OUTPUT` conserva la lectura completa de AppTest;
`EQUITY_REGRESSION_OUTPUT_DIR`, los volcados e informe. El trabajo se detiene en
Equity; Small caps requiere confirmación para la próxima etapa.
