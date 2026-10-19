# Instalación en Windows (paso a paso)

Este documento explica, paso a paso, cómo dejar la app funcionando en tu
PC con Windows, **trayendo los datos de la Mac** con la copia de
seguridad comprimida y la herramienta de restauración. Importante: no se
vuelven a descargar los datos desde cero, porque el historial intradía
acumulado no se puede volver a pedir al proveedor.

---

## Qué vas a necesitar

| Elemento | De dónde | Peso |
|---|---|---|
| La última copia de seguridad (`backups/daily/finance_…zip`) | Mac | **~123 MB** (el 19/10/2026: 123.359.815 bytes; crece con los datos) |
| La carpeta del proyecto completa | Mac: `Documents/productos ia/Dashboard Financiero` (sin `data/`) | ~7 MB |
| Python 3.13 para Windows | python.org/downloads | ~30 MB |
| Git para Windows (solo si vas a correr las pruebas) | git-scm.com | ~60 MB |
| Internet | — | para instalar paquetes |

Todo lo demás (historial de velas, fotos, avisos, versiones) viaja
**dentro** del archivo zip. El pendrive o la carpeta en la nube
necesitan ~200 MB libres.

## Cómo llevás el ZIP de la Mac a la PC (dos caminos)

**Camino A — pendrive o disco externo:** en Finder, copiá el archivo
`backups/daily/finance_…zip` (el de fecha más nueva) al pendrive.
Con ~123 MB no hace falta formatear: cualquier pendrive sirve. Al
terminar de copiar, expulsá con seguridad.

**Camino B — carpeta en la nube:** arrastrá el zip a tu carpeta de
Google Drive, Dropbox o OneDrive en la Mac, esperá a que suba del todo
(con 123 MB son unos minutos), y en la PC descargalo desde la misma
carpeta en la nube. Descargalo **a la PC**, no lo abras desde la nube.

En ambos casos el zip queda como archivo suelto; después lo pondrás en
su lugar dentro del proyecto.

---

## Paso 1 — En la Mac: preparar lo que viaja

1. Copiá la carpeta del proyecto a un pendrive o disco externo,
   **excluyendo la carpeta `data/`** y la carpeta `backups/` (viajan por
   separado). La forma sencilla: en Finder, copiá la carpeta; después
   borrá de la copia las carpetas `data`, `backups`, `test_fixtures` y
   `.venv` (esa última es específica de Mac y no funciona en Windows:
   en Windows se vuelve a crear).
2. Copiá también **el archivo más nuevo** de `backups/daily/`
   (empieza con `finance_2026…zip`).
3. Sacá el pendrive con eso: la carpeta del proyecto (sin `data`,
   `backups`, `test_fixtures`, `.venv`) y el archivo zip al lado.

> Si preferís la nube para todo: comprimí la carpeta del proyecto en un
> zip (clic derecho → Comprimir) y subí **los dos zips**: el del
> proyecto y el de la base. En la PC los descargás y descomprimís el
> del proyecto.

## Paso 2 — En la PC: instalar Python y (opcional) Git

1. Conectá el pendrive o descargá de la nube y copiá la **carpeta del
   proyecto** a
   `C:\Users\TuUsuario\Documents\productos ia\Dashboard Financiero`
   (misma ruta relativa que en la Mac para que los comandos encajen).
2. Dentro de esa carpeta, creá la carpeta `backups` y, dentro de ella,
   otra llamada `daily`. Copiá ahí el archivo zip que trajiste.
3. Instalá Python desde python.org/downloads (versión **3.13**). Durante
   la instalación, marcá la casilla **"Add python.exe to PATH"** (es la
   única casilla que importa).
4. (Solo si vas a correr las pruebas) Instalá Git desde git-scm.com:
   "Download for Windows". Las opciones por defecto están bien; marcá
   "Add Git to PATH".
5. Abrí **PowerShell** y verificá los dos:

```powershell
python --version
git --version
```

   Python debe responder algo como `Python 3.13.x`. Git, `git version
   2.x.y`. Si uno de los dos dice "no se reconoce", leé "Si algo falla"
   del paso 2 más abajo.

## Paso 3 — En la PC: crear el entorno e instalar la app

En PowerShell, una línea por vez, dentro de la carpeta del proyecto:

```powershell
cd "$env:USERPROFILE\Documents\productos ia\Dashboard Financiero"
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

La cuarta línea (pip) tarda **entre 3 y 10 minutos** porque baja las
librerías. Cuando termina, el texto de la línea empieza con
`(.venv)`, señal de que el entorno está activo.

## Paso 4 — En la PC: configurar la clave de datos

La app usa tu clave de FRED para algunos indicadores. Si la tenés,
copiá el archivo `.env.example` a `.env` y pegá tu clave:

```powershell
copy .env.example .env
notepad .env
```

En el Bloc de notas, reemplazá `tu_clave_aquí` por tu clave FRED real y
guardá. Si no tenés la clave a mano, el paso 5 te va a avisar y podés
sacarla después.

## Paso 5 — En la PC: restaurar los datos (la parte importante)

1. Con el entorno activado (Paso 3), restaurá la base completa desde el
   archivo zip que trajiste:

```powershell
python restore_data.py --ultimo --destino data\finance.db
```

   `--ultimo` elige automáticamente la copia más nueva de `backups\daily`.
   Cuando termina muestra un detalle con el tamaño y la fecha del último
   dato. Si algo falla, revisá que el zip esté en `backups\daily\` con su
   **nombre original** (no lo renombres a mano).

2. Verificá que la base quedó bien:

```powershell
python check_data.py
```

   Debe terminar **sin errores graves** y listar los últimos precios de
   control. La fecha de los cierres debe ser la misma que ves en la app
   de la Mac.

## Paso 6 — En la PC: comprobar que quedó bien

Tres comprobaciones, en orden:

1. **La base tiene los mismos datos:** en la app de la Mac, anotá el
   último precio y la fecha de cierre de cualquier pestaña; acá abrí la
   app y mirá la misma. Los dos deben coincidir hasta la última vela.

```powershell
.venv\Scripts\Activate.ps1
streamlit run app/main.py
```

2. **La app abre todas las pestañas** (Índices, Metales, Cripto,
   Equity, Small caps, Argentina) sin mensajes de error.
3. **La foto se puede leer:** en la app, bajá al Historial y confirmá
   que la última foto que tomó la Mac sigue ahí, con su fecha (el
   historial muestra «Última foto: …»; la fecha debe ser la misma que
   en la Mac).

Si todo eso coincide, la instalación en Windows quedó lista.

## Cómo actualizar de ahora en más en la PC (opcional)

Si querés que la PC siga actualizando los precios por sí misma (como la
Mac), corré de vez en cuando:

```powershell
.venv\Scripts\Activate.ps1
python daily_run.py --hora 21:15
```

Igual que en la Mac, eso hace respaldo, descarga, cálculos y foto. La
tarea programada se puede activar después, cuando decidas si te resulta
cómoda la programación.

---

## Si algo falla (paso por paso)

**Paso 2 — `python --version` no responde ("no se reconoce"):**
Python quedó sin la casilla "Add python.exe to PATH". Reinstalá
marcándola, o agregá a mano el directorio de Python al PATH. Cerrá
PowerShell y abrí uno nuevo para que tome el cambio.

**Paso 2 — `git --version` no responde:** si no pensás correr las
pruebas, ignoralo (Git no es necesario para usar la app). Si pensás
correrlas: reinstalá Git marcando "Add Git to PATH" y reabrí PowerShell.

**Paso 3 — "el script está deshabilitado" al activar el entorno:**

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

y volvé a intentar. Es una política del propio PowerShell, no de la app.

**Paso 3 — `pip install` se corta a la mitad:** casi siempre red
inestable. Corré de nuevo la misma línea; pip retoma lo que falta. Si
sigue fallando, probá con cable o más cerca del router.

**Paso 3 — "no such file: requirements.txt":** no estás en la carpeta del
proyecto. Corré primero `cd` con la ruta exacta, con comillas porque la
ruta tiene espacios.

**Paso 5 — "no se encontró la copia":** el zip no está en
`backups\daily\`, o está renombrado. Tiene que llamarse
`finance_…zip` tal como viene de la Mac.

**Paso 5 — el zip no abre / "dañado":** la herramienta de restauración
verifica la integridad y avisa el motivo. Volvé a copiar el zip desde el
pendrive o re-descargalo de la nube (una transferencia interrumpida deja
el archivo incompleto). No lo descomprimí ni lo renombres a mano.

**Paso 5 — la base quedó con menos datos que la Mac:** comprobá que en
la Mac hayas usado el zip más nuevo; si la PC quedó con una copia vieja,
corré de nuevo `python restore_data.py --ultimo --destino
data\finance.db` con el zip correcto.

**Paso 6 — "streamlit no se reconoce":** el entorno no está activado;
corré `.venv\Scripts\Activate.ps1` y volvé a intentar.

**Paso 6 — el navegador no abre solo:** Streamlit imprime una dirección
local (típicamente `http://localhost:8501`); abrila a mano en el
navegador. La primera vez Windows puede preguntar por el cortafuegos:
aceptá para redes privadas.

**Paso 6 — la app abre pero dice "no database file":** la restauración
del paso 5 no corrió; revisá la ruta exacta de `backups\daily\` y
repetí el paso 5.

**Paso 6 — las pestañas abren pero algún gráfico dice "Historia
insuficiente":** anotá qué activo y qué temporalidad; compará con la
Mac. Si solo pasa en la PC, volvé a restaurar (paso 5) y reportá la
diferencia antes de seguir.

## Verificación final en una sola mirada

| Comprobación | ¿Cómo se ve bien? |
|---|---|
| `python --version` | `Python 3.13.x` |
| `git --version` | `git version 2.x` (opcional) |
| `check_data.py` | termina sin errores graves, últimos precios de control con fecha igual a la Mac |
| App (seis pestañas) | ninguna pestaña muestra error; los precios coinciden con la Mac |
| Historial | «Última foto: …» con la fecha de la última foto tomada en la Mac |
