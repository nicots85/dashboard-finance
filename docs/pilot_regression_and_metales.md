# Piloto genérico: regresión real de Índices y Metales

## Resultado de la corrida final

- Código anterior: `63c8401`, ejecutado en un git worktree.
- Primer refactor: `26e1a77`, ejecutado en otro git worktree.
- Todas las versiones leyeron la misma copia consistente de `finance.db`, creada mediante el respaldo SQLite. No se actualizó la base productiva.
- Comparación `63c8401` contra `26e1a77`: 654 elementos renderizados comparados; 67 diferencias.
- Vista inicial: 26 diferencias. Faltaba el desplegable de alineación de la vista anterior con sus textos y captions; también cambiaba el JSON de parámetros visible.
- Vista con el primer par cargado: 41 diferencias. Además de lo anterior, el par pasó a «no calculable» por el parámetro faltante `johansen_diff_lags`, desapareciendo indicadores, gráficos y ayudas de la relación.
- Campos faltantes del primer refactor: `stable_blocks`, `p_threshold`, `johansen_diff_lags`, `rolling_step` y `cfdfuture_comparison`.
- Comparación `63c8401` contra el código corregido: 2319 elementos renderizados comparados; 0 diferencias.
- Estados de interfaz comparados con el código corregido: 7. Vista inicial, cada uno de los 3 pares diarios cargados, detalle de una hora, detalle de cuatro horas con futuro y detalle de cuatro horas con ETF.
- Pruebas sintéticas: 5 aprobadas.
- C0: 22 aprobadas.
- C1: 7 aprobadas.
- C2: 20 aprobadas.
- C3: 5 aprobadas.
- Cuatro horas: 16 aprobadas.
- Integración AppTest de cuatro horas e historial: 1 aprobada.
- Metales: 3 aprobadas.
- Regresión AppTest completa: 1 aprobada.
- Total: 80 pruebas aprobadas, sin pruebas omitidas.

La comparación incluye todos los desplegables, las tablas y sus valores
formateados, ayudas de columnas y métricas, selectores, textos y especificaciones
completas de los gráficos. Las matrices numéricas binarias de Plotly se
decodifican antes de comparar. Solo se normalizan edad del dato y hora de
cálculo; los IDs internos de transporte de Streamlit/Styler no son contenido
visible. Un error de extracción o un timeout hace fallar la prueba.

La diferencia inicial **no era una carrera de AppTest**: se había eliminado un
desplegable real dentro de «Vista anterior». Se conserva únicamente allí para
Índices. No repite la lectura vigente del piloto: la vista anterior usa los
semáforos guardados y el piloto excluye escalas atrasadas. Las otras pestañas no
recuperan el desplegable no solicitado.

## Reproducción automática

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  .venv/bin/python -B test_regression.py
```

La prueba crea y elimina sus worktrees automáticamente y usa procesos separados
para aislar módulos y cachés. Los volcados se ejecutan secuencialmente para evitar
presión de memoria. No se reduce el conjunto de tablas o gráficos para acelerar
la prueba. Definir `REGRESSION_OUTPUT_DIR` conserva `old.json`, `refactor.json`,
`current.json` y `report.json` en el directorio elegido.

## Configuración única

`config/sections.yaml` es la fuente de configuración del piloto. El catálogo de
nombres, la descarga de referencias y la firma de parámetros de las fotos usan
este archivo. `config/indices_pilot.yaml` fue eliminado después de migrar todos
sus lectores. Las fotos históricas conservan su JSON y su firma original; las
nuevas firmas incluyen la configuración realmente vigente.

`render_section_pilot` se usa para Índices y Metales. Se preservan las claves
originales de los widgets de Índices y las de Metales tienen su propio prefijo.
Los campos de diagnóstico de Índices mantienen el contenido visible anterior;
los metadatos nuevos de sección no cambian sus valores ni sus ayudas.

## Metales

- Oro, Plata, Cobre y Platino comparten el renderer; no hay una pantalla copiada.
- Contexto acordado: tasa nominal del Tesoro, tasa real estadounidense y dólar
  amplio de FRED (`DGS10`, `DFII10`, `DTWEXBGS`).
- Fuerza relativa contra el dólar: diferencia de rendimientos porcentuales sobre
  las mismas sesiones comunes. Se muestra la fecha del benchmark y se avisa que
  el corte puede preceder al último cierre del metal. No se usan datos posteriores
  a la hora de lectura.
- Oro/Plata: ratio de cierres comunes, distancia porcentual frente a su media
  simple y distancia por desvío muestral. No se fabrica un ATR a partir del ratio.
- VWAP de Oro, Plata y Cobre: precio típico y volumen del mismo contrato continuo;
  calendario específico de cada metal y sesión completa provisional de Nueva York,
  con ajuste por horario de verano.
- Platino: solo diario y medias de cierres; sin VWAP ni etiquetas intradía. La
  trazabilidad informa las velas guardadas aun cuando su lectura esté deshabilitada.
- Aviso de futuros continuos de Yahoo y cambios de contrato visible.
- Cointegración: solo diario, con los pares Oro/Plata y Oro/Cobre y las mismas
  reglas de estabilidad del piloto.
- El AppTest de Metales verifica el ratio, el contexto acordado, las opciones de
  Platino, la ausencia de VWAP de Platino, la presencia de VWAP de Oro, ambos pares
  y la vista de cuatro horas. Abrir o cambiar selectores no crea fotos.

El trabajo se detiene en Metales. Cripto conserva su vista anterior.
