# Estado del proyecto dashboard-finance (octubre de 2026)

QUÉ ES
Tablero local en Streamlit (Mac y PC) para operar con contexto.
Datos gratuitos: Yahoo, Binance/Bybit, FRED. Base SQLite local en
data/finance.db (no está en Git).

QUÉ TIENE
- Seis pestañas: Índices, Metales, Cripto, Equity, Small caps y
  Argentina. Cada una: indicadores grandes, contexto macro, fuerza
  relativa, tabla resumen, alineación de temporalidades, detalle con
  VWAP, relaciones entre pares, fuentes y calidad, glosario y "Vista
  anterior".
- Dirección (Alcista/Bajista/Lateral, zona plana de 0,05 x ATR) y
  fuerza (débil/media/fuerte por ADX con histéresis). Detecta mejor
  las subas que las caídas.
- Pares: estados estable / intermitente / sin relación (compatible con
  azar) / no calculable, con regla binomial al 5%. Casi todos los pares
  quedan "sin relación".
- 4h: índices vía futuros (NQ=F, ES=F, YM=F, RTY=F); acciones, ETF y
  ADR con "4h de sesión"; Argentina con "4h de sesión" de BYMA armadas
  desde velas de 1h.
- Argentina: CCL implícito = (precio local x acciones por ADR) / precio
  ADR. Equivalencias: GGAL 10, YPF 10, PAM 25, BMA 10, CEPU 10. Ventana
  común BYMA-NYSE: 14:00-20:00 UTC hoy y 14:30-20:00 UTC desde el
  cambio de hora de EE.UU. (1 de noviembre de 2026). Alertas:
  dispersión persistente y posible evento corporativo.
- Historial: fotos versionadas de lo que decía el tablero, con estados
  ok / completa (con notas) / parcial.
- Copias de seguridad comprimidas de la base (restaurar con
  restore_data.py). Guías: docs/GUIA.md y docs/INSTALACION_WINDOWS.md.

LIMITACIONES
- Yahoo da poca historia intradía (1m ~7 días, 5m y 15m ~60 días, 1h
  ~2 años). La base acumula lo que ya se descargó; no se puede volver
  a bajar.
- Futuros continuos: no se verificó cómo Yahoo ajusta los cambios de
  contrato. El VWAP con velas es una aproximación. El platino diario no
  tiene VWAP. FRED tiene rezago.
- El CCL de acciones no es el CCL cotizado (que suele salir de bonos).
- Las pruebas completas tardan horas. La base congelada para pruebas
  rápidas está en pausa (paridad con 1.434 diferencias).

PENDIENTE DEL USUARIO
- Instalar la tarea diaria de las 21:15 (install_daily_backup.py).
- Probar la PC con Windows.
- Confirmar la sesión de VWAP, las horas de las velas de 4h de
  PrimeXBT y la comparación NQ=F contra USTEC.
- Validar las pestañas contra su plataforma y usarlas una semana.
