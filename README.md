# Dashboard Finance 📊

Dashboard para trading con regímenes de mercado, tendencias multi-temporalidad,
z-score ajustado por volatilidad y cointegración.

**Secciones:** Índices · Metales · Equity · Small caps · Cripto · Acciones argentinas

---

## Requisitos previos

- **Python 3.11 o superior** — [Descargar](https://www.python.org/downloads/)
- **Git** — [Descargar](https://git-scm.com/downloads)
- **Clave de FRED** (gratuita) — [Obtener aquí](https://fred.stlouisfed.org/docs/api/api_key.html)

---

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/nicots85/dashboard-finance.git
cd dashboard-finance
```

### 2. Crear el entorno virtual

**Mac / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

```bash
cp .env.example .env        # Mac / Linux
copy .env.example .env      # Windows
```

Abrí el archivo `.env` con cualquier editor de texto y pegá tu clave de FRED:
```
FRED_API_KEY=tu_clave_aquí
```

### 5. Verificar que todo funciona

```bash
python check_setup.py
```

Deberías ver 3 líneas con **OK** (FRED, yfinance, ccxt/Binance).

---

## Uso diario

Cada vez que abras una terminal nueva, activá el entorno virtual antes de trabajar:

**Mac / Linux:** `source .venv/bin/activate`

**Windows (PowerShell):** `.venv\Scripts\Activate.ps1`

---

## Estructura del proyecto

```
dashboard-finance/
├── app/           ← Interfaz (Streamlit)
├── config/        ← Listas de activos por sección
├── data/          ← Base SQLite local (no va a Git)
├── src/
│   ├── data/      ← Adaptadores de datos (yfinance, ccxt, FRED)
│   └── calc/      ← Cálculos (z-score, cointegración, regímenes)
├── check_setup.py ← Script de verificación
├── requirements.txt
├── .env.example   ← Plantilla de variables de entorno
└── README.md
```

---

## Cómo correr el dashboard (Streamlit)

**Mac / Linux:**
```bash
source .venv/bin/activate
streamlit run app/main.py
```

**Windows (PowerShell):**
```powershell
.venv\Scripts\Activate.ps1
streamlit run app/main.py
```

Se abre solo en tu navegador (http://localhost:8501). Las seis pestañas están activas. Desde la app podés actualizar las seis temporalidades o usar la actualización rápida de 1h/1D.

### Actualizar datos manualmente (sin abrir la app)

```bash
python update_data.py --tf 1m,5m,15m,1h,4h,1D   # descarga todas las temporalidades
python run_calc.py --tf 1m,5m,15m,1h,4h,1D       # recalcula régimen, z-score, cointegración
```

### Pruebas sintéticas

```bash
python test_synthetic.py
python test_c0.py          # Protección, restauración y trazabilidad (bases de prueba)
```

## Copias de seguridad y restauración (C0)

```bash
python backup_data.py
python restore_data.py --ultimo --destino data/restauracion_prueba.db
python check_data.py
python check_cointegration_history.py
```

Las copias ZIP usan el respaldo de SQLite, se comprueban y quedan en `backups/`
fuera de Git. Se conservan 7 días, 4 semanas y 3 meses. `update_data.py` crea
una copia antes de la primera descarga del día si falta. Para que también se
haga sin abrir la app, programarla **solo en la máquina principal que elijas**:

```bash
python install_daily_backup.py --hora 21:15             # Preparar, NO activar
python install_daily_backup.py --hora 21:15 --instalar  # Activar en esta máquina
```

La hora es local a la máquina y requiere equipo encendido/usuario conectado.
Todavía no se activó una tarea en esta entrega.

**[Instrucciones paso a paso para Mac, Windows y restauración](docs/C0.md)**
· **[Referencias académicas verificadas y pendientes](docs/references.md)**

## Nombres y glosario (C1)

Las seis pestañas muestran nombres completos y ayudas. Los nombres se editan
en `config/assets.yaml` y las definiciones en `config/glossary.yaml`.
Cada pestaña tiene un desplegable **Glosario** y textos **Cómo leer esto**.

```bash
python test_c1.py
```

**[Qué comparar visualmente y aclaraciones sobre C0/iCloud](docs/C1.md)**
· **[Pendientes para C2, incluido el caso Solana](docs/pending.md)**

## Piloto de Índices (C2)

```bash
pip install -r requirements.txt
python update_indices_references.py
streamlit run app/main.py
```

Índices tiene lectura resumida, alineación, fuerza relativa, VWAP de instrumentos
de referencia y comparación de pares diaria. La sesión predeterminada elegida
es completa (18:00 Nueva York), las velas 4h siguen en UTC provisional y la
comparación con el CFD está pendiente. Las otras cinco pestañas conservan su
pantalla anterior. Dentro de Índices está **Vista anterior (para comparar)**.

**[Cálculos, limitaciones y guía de comparación con tu plataforma](docs/C2.md)**.

## Historial del tablero (C3)

El desplegable **Historial** recuerda lo que decía el tablero en cada momento:
KPIs, dirección, distancia, cointegración, CCL y macro. Se guarda una foto en
cada actualización manual y otra programada a las 21:15 (`daily_run.py`).
Abrir la app o cambiar un selector **no** crea fotos. Se puede exportar/importar
entre máquinas sin duplicar.

```bash
python test_c3.py
```

**[Formato, cuándo se guarda, tamaño y guía](docs/C3.md)**.
Las fotos del historial no se implementan hasta C3.

---

## Git: guardar y sincronizar cambios

### Guardar cambios (commit + push)

```bash
git add .
git commit -m "descripción de lo que cambiaste"
git push origin main
```

### Traer cambios en otra máquina (pull)

```bash
cd dashboard-finance
source .venv/bin/activate        # o .venv\Scripts\Activate.ps1 en Windows
git pull origin main
pip install -r requirements.txt  # por si se agregaron dependencias nuevas
```
