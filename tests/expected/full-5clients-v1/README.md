# Referencias de la muestra local — cinco clientes

- Preparadas el 22 de octubre de 2026 mediante el notebook serial. 
- Entrada: **250.000 filas, 467.363.817 bytes de Parquet**. 
Cada cliente recibió 50.000 filas: 25.000 inglesas y 25.000 francesas.

**Estado de esta captura: Q1, Q3, Q4 y Q5 completas; Q2 incompleta.**
Hay **218 referencias con bytes guardados, una con HTTP 404 y ninguna pendiente
de procesar**. Se conservaron todas las filas esperadas.

| Cliente | Q1 | Q2 (candidatos) | Q3 | Q4 | Q5 |
|---|---:|---:|---:|---:|---:|
| client-0 | 1634 | 143 | 16672 | 20 | 16851 |
| client-1 | 1582 | 116 | 17020 | 20 | 17106 |
| client-2 | 1618 | 140 | 16615 | 20 | 16798 |
| client-3 | 1602 | 145 | 16615 | 20 | 17580 |
| client-4 | 1559 | 143 | 16815 | 20 | 16978 |

Q2 tiene 687 candidatos: 468 sin referencia de imagen y 219 con URL.
Los 219 corresponden a URLs distintas.

| Cliente | Sin referencia | Imagen disponible | HTTP 404 | Pendientes |
|---|---:|---:|---:|---:|
| client-0 | 95 | 48 | 0 | 0 |
| client-1 | 79 | 37 | 0 | 0 |
| client-2 | 95 | 44 | 1 | 0 |
| client-3 | 95 | 50 | 0 | 0 |
| client-4 | 104 | 39 | 0 | 0 |

| Cliente | Suma histórica de ocurrencias (S) | Abstracts históricos computables (N) |
|---|---:|---:|
| client-0 | 100315 | 4248 |
| client-1 | 95779 | 4052 |
| client-2 | 96805 | 4195 |
| client-3 | 93513 | 4168 |
| client-4 | 92267 | 3966 |

La suma de denominadores históricos es 20.629: se excluyeron 118 abstracts
históricos nulos.

## Indisponibilidad pendiente

La referencia que respondió HTTP 404 pertenece a `client-2`; su fila sigue en Q2.
El diagnóstico está en [image-404-errors.jsonl](image-404-errors.jsonl):

```text
https://upload.wikimedia.org/wikipedia/commons/8/8a/Amelie_Rivat%2C_Giro_Rosa_2016.jpg
```

Queda por resolver cómo obtener esos bytes o tratar su indisponibilidad antes de
considerar completa la referencia. La consulta ya está hecha en el campus.

## Artefactos y auditoría

El [manifiesto](manifest.json) registra la entrada, el contrato, la integridad y
el estado vigente; `image_capture_sessions` conserva el historial detallado de
intentos. La [guía de artefactos](../README.md) describe los formatos y las
imágenes compartidas. Para auditar este escenario o realizar futuras capturas,
seguir la [guía del oráculo](../../oracle/README.md#verificar-referencias).
