# Paso 6 — Argentina

La pestaña Argentina pasó de una vista propia a la función genérica
`render_section_pilot`, con la misma configuración de `config/sections.yaml`
que las otras cinco. Conserva la vista anterior como «Vista anterior».

## Qué muestra

### CCL implícito por empresa

Fórmula, con la equivalencia de `config/assets.yaml`:

```
CCL de la empresa = precio local en pesos × acciones por ADR ÷ precio del ADR
```

Equivalencias usadas: GGAL 10, YPF 10, PAM 25, BMA 10, CEPU 10. La de YPF es
10 porque la serie local `YPFD.BA` de esta base viene ajustada tras el split
10:1, y el mismo ajuste se aplica a toda su historia.

- **En diario** usa el cierre de la misma fecha en los dos mercados.
- **En intradía** usa velas de quince minutos y solo dentro de la ventana
  común BYMA–NYSE, calculada con zonas horarias reales:
  - hoy, con horario de verano en Estados Unidos: **14:00–20:00 UTC**;
  - desde el cambio de hora de Estados Unidos: **14:30–20:00 UTC**.
  Fuera de esa ventana no hay CCL intradía y solo se muestra el cierre del día.
  Si el día más reciente no tiene datos de los dos mercados, se retrocede día
  por día hasta el último con ventana completa y se dice cuál se usó.

### Indicadores grandes

- **CCL implícito mediano** de las cinco empresas, con su cambio en cinco ruedas.
- **Distancia del CCL a su media**: cociente entre la mediana y su media simple
  de 50 sesiones, dividido por el desvío muestral de las mismas.
- **Acciones locales que suben**, sobre las cinco acciones en pesos.
- **Mayor separación de la media**: máxima separación absoluta frente a la EMA
  de 50 cierres, dividida por el desvío de 50 cierres.
- **Dispersión entre empresas**: desvío de cada empresa contra la mediana de
  ese mismo día, con la que supera el umbral destacada en la tabla.

El aviso pedido está siempre visible:

> El CCL es un tipo de cambio con tendencia: un z alto indica que subió rápido,
> no que vaya a revertir.

No se usa cointegración entre la acción local y su ADR. El bloque «Relaciones entre acciones argentinas» lo dice y no calcula estados de cointegración.

### Umbral de dispersión propuesto

Medido sobre las últimas **126 sesiones** con las cinco empresas completas:

| Medida | Valor |
| --- | ---: |
| mediana | 0,12% |
| percentil 90 | 0,51% |
| percentil 95 | 0,82% |
| percentil 99 | 6,09% |
| máximo | 6,28% |
| observaciones por encima de 2% | 6 de 126 (4,8%) |

Propuesta: **2%** (`dispersion_threshold_pct`). La dispersión habitual es
menor al 1%: el percentil 95 queda en 0,82%. Con 2% se resalta solo cuando una
empresa se despegó de forma extraordinaria, y según esta muestra eso ocurre en
algo menos del 5% de las sesiones. El 5% que se usaba antes era demasiado
permissivo: la distribución está concentrada muy por debajo. El umbral está en
la configuración y la pantalla muestra siempre los percentiles reales, para que
el número no sea una caja negra.

## Sesiones

| Mercado | Zona | Sesión | 4h de sesión |
| --- | --- | --- | --- |
| BYMA (acciones locales) | America/Argentina/Buenos_Aires | 11:00–17:00 | 11:00–15:00 y 15:00–17:00 |
| NYSE (ADR) | America/New_York | 09:30–16:00 | 09:30–13:30 y 13:30–16:00 |

La 4h de sesión se construye desde velas de quince minutos de la propia
sesión, en el momento de leer. Nunca se usa la 4h que trae el proveedor, que
no respeta la apertura ni el cierre de cada mercado. La segunda vela puede ser
más corta y así se rotula.

El VWAP de cada acción local usa precio y volumen del mismo instrumento y se
reinicia a las 11:00 de Buenos Aires.

Estas series son poco líquidas. La auditoría de la actualización
([auditoria_actualizacion.md](auditoria_actualizacion.md)) muestra que Argentina
concentra 2441 de los 2717 avisos de posible hueco. Se avisan y no se inventan
precios ni volumen.

## Fotos

El formato pasó a **11**. Cada foto guarda, además de lo que ya guardaba:

- CCL implícito de cada una de las cinco empresas.
- Mediana, cambio a cinco ruedas y separación por desvío.
- Dispersión: lista de empresas, desvío contra la mediana y cuál se resalta.
- Referencia de dispersión de las últimas 126 sesiones.
- Conteo de acciones locales que subían y la mayor separación de su media.
- Ventana común BYMA–NYSE usada y CCL intradía de cada empresa.
- Política de las dos sesiones, con horario y bloques de cuatro horas.

Las fotos anteriores conservan su JSON y no se completan a posteriori. El
historial muestra el CCL mediano y el detalle por empresa de la foto elegida.

## Brecha contra el CCL oficial del BCRA

**No implementada**, como pediste. Propuesta:

- **Fuente**: la API pública y gratuita de Estadísticas Cambiarias del BCRA,
  en `api.bcra.gob.ar/estadisticascambiarias/v1.0/`, documentada en
  `estadisticas-cambiarias.bcra.apidocs.ar`. Publica las cotizaciones de divisas
  vigentes a una fecha y la evolución de cada moneda ISO en un intervalo. El
  endpoint de cotizaciones devuelve, entre otras, el tipo de cambio del dólar
  con su `fecha`, que es la referencia A 3500 del mercado mayorista.
- **Cálculo propuesto**: para cada fecha de sesión argentina,
  `brecha = (CCL implícito mediano ÷ tipo de cambio A 3500 del BCRA − 1) × 100`,
  usando la mediana de las cinco empresas de esa misma fecha y la cotización del
  BCRA de esa misma fecha. Se mostraría la serie de la brecha, su media de 50
  sesiones y su percentil, con la misma lógica de percentil del resto.
- **Límites que hay que decir en pantalla**:
  1. El BCRA publica el A 3500, no el CCL. El CCL incluye dólares de bonos y
     MEP, así que la brecha contra A 3500 es indicativa, no la brecha oficial
     del CCL.
  2. La publicación tiene rezago: la cotización de un día aparece después del
     cierre, a veces uno o dos días hábiles después. La comparación se debe
     hacer contra la última fecha disponible del BCRA, mostrando ambas fechas.
  3. La fecha del BCRA es la fecha local del negocio; hay que alinearla con
     la sesión BYMA, no con la fecha UTC.
  4. Si la brecha contra el CCL real resulta importante, haría falta una fuente
     adicional para el MEP, que hoy no tiene una API pública estable.

Queda anotado en la configuración y visible en el bloque de relaciones de la
pestaña. Se implementa solo con tu confirmación.

## Pruebas

- `test_argentina.py`: seis pruebas de cálculo (fórmula del CCL, alineación de
  claves, ventana común antes y después del cambio de hora, bloques de cuatro
  horas de BYMA con el segundo más corto, umbral de dispersión, cambio a cinco
  ruedas) y una prueba de AppTest con las seis pestañas, la tabla de CCL, la
  ausencia de cointegración y la foto formato 11.
- `test_argentina_regression.py`: comprueba que las otras cinco pestañas no
  cambian, contra el commit `676a14a`, con la misma copia íntegra de la base y
  el mismo corte de evaluación.

Los comandos y las duraciones están en [pruebas.md](pruebas.md).