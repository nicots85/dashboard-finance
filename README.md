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
