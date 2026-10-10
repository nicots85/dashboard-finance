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
