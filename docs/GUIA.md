# Guía de uso (para mí, sin tecnicismos)

Esta guía explica cómo usar el dashboard en el día a día. No hace falta
saber programar: casi todo es copiar y pegar comandos en una ventana de
terminal.

---

## 1. Cómo abrir la app

### En la Mac

1. Abrí la app **Terminal** (buscala con el buscador Spotlight).
2. Copiá y pegá esta línea entera y presioná Enter:

```bash
cd "$HOME/Documents/productos ia/Dashboard Financiero" && source .venv/bin/activate && OPENBLAS_NUM_THREADS=1 caffeinate -is .venv/bin/streamlit run app/main.py
```

3. La app se abre sola en el navegador (dirección `http://localhost:8501`).
   Si no se abre sola, copiá esa dirección en el navegador.
4. Para cerrar la app: volvé a la ventana de Terminal y presioná
   **Control + C**. También podés cerrar la ventana de Terminal.

La parte `caffeinate -is` evita que la Mac se duerma a la mitad de la
carga. Si preferís que la Mac se duerma normalmente, borrá esas dos
palabras de la línea.

### En la PC con Windows

1. Abrí **PowerShell** (botón de Inicio, escribí "powershell").
2. Copiá y pegá:

```powershell
cd "$env:USERPROFILE\Documents\productos ia\Dashboard Financiero"
.venv\Scripts\Activate.ps1
streamlit run app/main.py
```

3. Se abre en el navegador en `http://localhost:8501`. Para cerrar:
   **Control + C** en la ventana.

La instalación inicial de la PC está explicada paso a paso en
[INSTALACION_WINDOWS.md](INSTALACION_WINDOWS.md).

### Cuánto tarda abrir la app

La primera vez que abrís una pestaña, carga la base de datos y puede
tardar **un par de minutos**. Después queda en caché y cada pestaña abre
en segundos. Al reabrir la app después de una actualización, la caché se
vacía y vuelve a tardar un par de minutos la primera vez por pestaña.

---

## 2. Cómo actualizar los datos

Hay tres maneras. Las tres hacen lo esencial: descargar los precios
nuevos y recalcular los indicadores. La diferencia es el alcance.

### Opción A — la corrida diaria programada (la recomendada)

Dejá esto preparado una vez y la Mac lo hace sola **todos los días a las
21:15 de Buenos Aires**: hace la copia de seguridad, descarga,
recalcula y toma la foto diaria.

En la última medición real (11 de octubre de 2026), la corrida diaria
completa tardó **alrededor de 15 minutos**. Con la Mac encendida y
despierta a esa hora no tiene nada que hacer: corre sola.

Cómo revisar la programación instalada:

```bash
launchctl list | grep dashboard
```

Si aparecen líneas con la palabra "dashboard", la tarea programada está
instalada. (El nombre exacto del servicio lo define
`install_daily_backup.py`; revisá ese archivo si cambiaste algo.)

Estado actual (20 de octubre de 2026): la tarea diaria NO está
instalada en esta Mac (no hay ningún "dashboard" en
`~/Library/LaunchAgents` ni en `launchctl list`; lo que aparece como
`com.apple.financed` es un servicio propio de macOS, sin relación).
Instalala con `install_daily_backup.py` cuando quieras que corra sola.

### Opción B — actualizar a mano desde la terminal

Si querés actualizar ahora mismo, pegá esta línea:

```bash
cd "$HOME/Documents/productos ia/Dashboard Financiero" && source .venv/bin/activate && python daily_run.py
```

Eso hace **todo**, en este orden: respaldo, descarga, cálculos y foto.
Tarda alrededor de **15 minutos** (ver medición arriba). La hora de esta
corrida queda registrada en la base como una "foto diaria".

### Opción C — actualizar desde dentro de la app

En la barra superior hay un botón para actualizar los precios. Es más
rápido (varios minutos) pero **no toma la foto diaria** si no está
seguida de una corrida completa, así que el historial puede no registrar
esa corrida. Útil para mirar algo fresco fuera de horario.

### Qué NO hacer

- No corras `update_data.py` a mano para "ahorrar tiempo": no hace la
  copia de seguridad antes de tocar la base. La opción B ya hace todo en
  orden y respaldada.
- Si vas a restaurar una copia de seguridad (§ 5), cerrá primero la app
  y cualquier terminal con la base abierta.

---

## 3. Cómo leer cada pestaña (tres líneas por pestaña)

### Índices

1. Los cuatro indicadores grandes de arriba resumen la rueda:
   dirección, distancia a la media, z-score y régimen.
2. «Cómo leer esto» (al final) explica lo mismo sin tecnicismos y con
   más detalles en desplegables azules (ATR, volatilidad, bandas).
3. La pestaña no predice ni compra: describe dónde está el precio
   respecto de sus propios promedios y qué tan volátil es la rueda.

### Metales

1. Igual que Índices, pero con pares relativos (por ejemplo, oro sobre
   plata): el número del ratio se compara con su promedio histórico.
2. La señal está en la distancia al promedio: separación chica es
   normal, separación muy grande es lo que conviene mirar.
3. La sección «Relaciones entre pares» calcula la evidencia de que el
   par volvió a su media; al evaluar muchos pares, algunos aparecen
   «intermitentes» por azar: eso es una pista débil, no una señal.

### Cripto

1. Cripto opera las 24 horas: la vela del día arranca a la hora UTC, no
   en la apertura de un mercado.
2. El VWAP de sesión usa la fuente con mayor cobertura (bybit u otra);
   si la cobertura es baja, el desplegable lo aclara.
3. El panel «Cobertura de pares» indica si el par tiene historia
   suficiente para un dato estable.

### Equity (futuro NQ y acciones grandes)

1. La 4h del futuro NQ se calcula sobre la sesión de Nueva York
   (09:30–16:00), no la 4h que trae la plataforma.
2. La dirección del régimen usa la sesión regular de acciones; el
   premercado no cuenta como sesión.
3. Cuando el VWAP de un futuro se compara con el índice, la ventana se
   ajusta al horario de cada mercado y así los dos precios son de la
   misma franja horaria.

### Small caps (IWM, IWO, IWN frente al S&P 500)

1. El punto central es el ratio IWM/S&P 500 y su distancia a la media:
   mide si las empresas chicas van mejor frente al mercado grande.
2. Los cuatro activos comparten una rueda común de 20 días para las
   comparaciones; los cierres atrasados se avisan en pantalla.
3. Al evaluar varios ratios, algunos aparecen «intermitentes» por azar;
   tomalo como pista débil.

### Argentina (CCL implícito de cinco empresas)

1. El número grande es el **dólar implícito (CCL)**: precio local en
   pesos multiplicado por las acciones por ADR, dividido por el precio
   del ADR, ambos de la misma fecha.
2. La referencia es la **mediana** de las cinco empresas; cada empresa
   se resalta amarillo si se aleja más del 1% y naranja si supera el
   2%.
3. La columna **Estado** marca «Dispersión persistente» cuando la
   empresa superó el 2% en 3 de las últimas 5 ruedas: suele indicar un
   evento corporativo (por ejemplo un dividendo pagado en un solo
   mercado, como el de Central Puerto de septiembre de 2026) o poca
   negociación; mientras persista, su CCL no es comparable con el de
   las demás.
4. La columna **Liquidez** marca «poco líquida» cuando el cierre queda
   sin cambios varias ruedas o el volumen cae por debajo de la parte
   configurable de su mediana de veinte ruedas.
5. El CCL intradía solo existe dentro de la ventana común
   BYMA–NYSE; fuera de esa ventana la pestaña muestra el cierre del
   día.

Si la base tiene datos atrasados, cada pestaña lo avisa con una marca
claro en lugar de mostrar un número viejo como si fuera fresco.

---

## 4. Cómo ver el historial (fotos)

La app guarda una «foto» en cada corrida diaria: cómo se veían las seis
secciones a esa hora. Para verlas:

1. En la app, bajá hasta la sección **Historial**, en la parte inferior.
2. Elegí una fecha del desplegable; la app muestra los números de esa
   foto, organizados por pestaña.
3. El botón de **diferencia con la foto anterior** marca qué cambió
   entre dos corridas seguidas.

Al abrir el Historial, arriba muestra **«Última foto: fecha y hora · hoy
hay/no hay foto»**. Queda en rojo cuando pasaron más de 36 horas sin
foto: es la señal para revisar si la copia diaria se está corriendo.

Las fotos se guardan dentro de la base (`data/finance.db`), así que se
incluyen en las copias de seguridad y viajan a la PC con el respaldo.

---

## 5. Qué hacer si la app muestra un error

1. **Primero, anotá el error**: captura de pantalla y en qué pestaña
   estaba.
2. **Recargá la página** (F5 o Cmd+R). Muchos errores de pantalla se
   corrigen solos, porque la caché se vacía.
3. Si persiste, **cerrá la app** (Control + C en la terminal) y volvé a
   abrirla con el comando de apertura (§ 1).
4. Si el error habla de la base («database is locked», «base en uso» o
   parecido): cerrá ventanas de la app sobrantes y volvé a abrir.
5. Si la app abre pero los números se ven mal (una pestaña vacía,
   fechas raras): el causante más común es que la última actualización
   quedó a mitad. Corré la opción B (§ 2) y recargá.

### Cómo volver atrás si la base quedó rota

La última copia de seguridad está en `backups/daily/`. Para devolver la
app a esa copia (con la app y las terminales cerradas), en la carpeta
del proyecto:

```bash
python restore_data.py --ultimo --destino data/finance.db --reemplazar
```

Antes de reemplazar, el sistema guarda la base dañada en
`backups/before_restore/`, así que la «vuelta atrás» también tiene su
propia vuelta atrás.

---

## 6. Cómo saber si la foto diaria programada funcionó

Tres maneras, de la más simple a la más completa:

1. **Mirando la app:** si el Historial muestra una foto de hoy tomada
   cerca de las 21:15 de Buenos Aires, la corrida de hoy funcionó.
2. **Desde la terminal (una línea):**

```bash
python -c "import sqlite3; [print(r) for r in sqlite3.connect('data/finance.db').execute('SELECT due_utc,status,photo_id FROM daily_due_runs ORDER BY due_utc DESC LIMIT 3').fetchall()]"
```

   La última línea es la corrida más reciente. Si la fecha es de hoy, el
   estado es `ok` y hay un valor en `photo_id`, la foto se tomó. Si
   `photo_id` aparece `None`, la corrida empezó pero falló a mitad.

3. **Viendo las últimas fotos registradas:**

```bash
python -c "import sqlite3; [print(r) for r in sqlite3.connect('data/finance.db').execute('SELECT created_at,trigger,status,late FROM snapshot_photos ORDER BY created_at DESC LIMIT 3').fetchall()]"
```

   La última fila es la última foto. Los estados posibles son tres:
   `ok` (todo sin avisos), `completa (con notas)` (la corrida terminó,
   pero hay datos con avisos conocidos, por ejemplo historias cortas;
   se muestran separadas en el detalle del Historial) y `partial`
   (fallo real de un paso, con la lista de qué falló). `daily` con
   `ok` o `completa (con notas)` es el estado esperado. `late=1`
   significa que se tomó después de la hora prevista (por ejemplo
   porque la Mac estaba dormida).

---

## 7. Cuánto tarda cada cosa (resumen)

| Acción | Cuánto | Cifra medida |
|---|---|---|
| Abrir la app (pestaña ya en caché) | segundos | — |
| Abrir la app (primera carga del día) | 1–2 min por pestaña | estimado |
| Corrida diaria completa (opción A o B) | ~15 min | sí, el 11 de octubre de 2026 |
| Suite completa de pruebas | más de 8 h | `pruebas.md` |
| Regresión de las seis pestañas | 75 min | `pruebas.md` |

Los tiempos estimados pueden variar con el ancho de banda y la cantidad
de horas nuevas a descargar. Las terminales muestran cuándo empezó y
terminó cada paso, así que cualquier cifra se puede medir con el
cronómetro del reloj.
