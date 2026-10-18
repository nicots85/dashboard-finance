# Instalación en Windows (paso a paso)

Este documento explica, paso a paso, cómo dejar la app funcionando en tu
PC con Windows, **trayendo los datos de la Mac** con la copia de
seguridad comprimida y la herramienta de restauración. Importante: no se
vuelven a descargar los datos desde cero, porque el historial intradía
acumulado no se puede volver a pedir al proveedor.

---

## Qué vas a necesitar

| Elemento | De dónde | Peso aprox. |
|---|---|---|
| La última copia de seguridad | Mac: carpeta del proyecto → `backups/daily/` | ~100 MB |
| La carpeta del proyecto completa | Mac: `Documents/productos ia/Dashboard Financiero` (sin `data/`) | ~50 MB (texto) |
| Python 3.13 para Windows | python.org/downloads | ~30 MB |
| Internet | — | para instalar paquetes |

Todo lo demás (historial de velas, fotos, avisos, versiones) viaja
**dentro** del archivo de copia de seguridad.

---

## Paso 1 — En la Mac: preparar lo que viaja

1. Copiá la carpeta del proyecto a un pendrive o disco externo,
   **excluyendo la carpeta `data/`** y la carpeta `backups/` (viajan por
   separado en el paso 2). La forma sencilla: en Finder, copiá la
   carpeta; después borrá de la copia las carpetas `data`, `backups` y
   `.venv` (esa última es específica de Mac y no funciona en Windows:
   en Windows se vuelve a crear).
2. Copiá también **el archivo más nuevo** de `backups/daily/`
   (empieza con `finance_2026…zip`). Ese archivo es la base completa.
3. Sacá el pendrive con eso: la carpeta del proyecto (sin `data`,
   `backups`, `.venv`) y el archivo zip al lado.

## Paso 2 — En la PC: instalar Python y preparar la carpeta

1. Conectá el pendrive y copiá la **carpeta del proyecto** a
   `C:\Users\TuUsuario\Documents\productos ia\Dashboard Financiero`
   (misma ruta relativa que en la Mac para que los comandos encajen).
2. Dentro de esa carpeta, creá la carpeta `backups` y, dentro de ella,
   otra llamada `daily`. Copiá ahí el archivo zip que trajiste.
3. Instalá Python desde python.org/downloads (versión 3.13). Durante la
   instalación, marcá la casilla **"Add python.exe to PATH"** (es la
   única casilla que importa).
4. Abrí **PowerShell** y verificá que Python quedó instalado:

```powershell
python --version
```

   Debe responder algo como `Python 3.13.x`.

## Paso 3 — En la PC: crear el entorno e instalar la app

En PowerShell, una línea por vez, dentro de la carpeta del proyecto:

```powershell
cd "$env:USERPROFILE\Documents\productos ia\Dashboard Financiero"
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

La tercera línea (pip) tarda **entre 3 y 10 minutos** porque baja las
librerías. Si PowerShell frena la segunda línea con "scripts
deshabilitados", corré antes:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

y volvé a intentarlo. (Es una política del propio PowerShell, no de la
app.)

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

   `--ultimo` elige automáticamente la copia más nueva de `backups/daily`.
   Cuando termina muestra un detalle con el tamaño y la fecha del último
   dato. Si algo falla, verifica primero que el zip esté en
   `backups\daily\`.

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
   que la última foto que tomó la Mac sigue ahí, con su fecha.

Si todo eso coincide, la instalación en Windows quedó lista.

## Cómo actualizar de ahora en más en la PC (opcional)

Si querés que la PC siga actualizando los precios por sí misma (como la
Mac), corré de vez en cuando:

```powershell
.venv\Scripts\Activate.ps1
python daily_run.py --hora 21:15
```

Igual que en la Mac, eso hace respaldo, descarga, cálculos y foto. La
computadora conecta las notas internas para que después puedas decidir
si te resulta cómoda la programación.

---

## Problemas comunes en Windows

1. **"Script deshabilitado" al activar el entorno:** la solución del
   paso 3 (Set-ExecutionPolicy RemoteSigned en CurrentUser).
2. **"python no se reconoce":** Python quedó sin la casilla "Add to
   PATH". Reinstalá marcando esa casilla.
3. **La app abre pero dice "no database file":** la restauración del
   paso 5 no corrió o el zip está en otra carpeta; revisá la ruta
   exacta de `backups\daily\`.
4. **El archivo zip no abre:** la herramienta de restauración verifica
   la integridad y avisa el motivo; no lo renombres a mano: usa el
   comando del paso 5 con el nombre original y ruta con comillas.
