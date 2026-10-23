# Resultados esperados

Cada escenario conserva su manifiesto y las salidas Q1–Q5 por cliente. La
[guía del oráculo](../oracle/README.md) explica cómo generarlos, capturar imágenes,
verificarlos y actualizar las referencias. El estado de la primera muestra completa está
en [full-5clients-v1](full-5clients-v1/README.md).

## Organización

```text
tests/expected/
├── images/                     # Compartida por los escenarios hermanos
│   ├── index.json              # URL → descriptor de una captura exitosa
│   └── <sha256>.bin
└── full-5clients-v1/            # Un directorio por escenario
    ├── manifest.json
    ├── executed.ipynb
    ├── image-404-errors.jsonl   # Se crea si se encuentran HTTP 404
    ├── generator/reference.py  # Fuente original archivada, sin modificar
    └── client-0/ ... client-4/
        ├── q1.jsonl
        ├── q2.jsonl
        ├── q3.jsonl
        ├── q4.jsonl
        └── q5.jsonl
```

El manifiesto registra la selección de entrada, versión semántica, hashes de
stopwords y del generador, versiones del entorno y estadísticas por cliente,
incluidos `S`, `N` y el estado de Q5 definidos en el
[contrato serial](../oracle/README.md#contrato-serial). `image_capture_sessions`
conserva el historial de captura con tiempos, solicitudes, descargas e identidad
del entorno.

`executed.ipynb` conserva el estado observado al ejecutar el notebook. Si se
capturan imágenes después, el manifiesto se actualiza junto a Q2 y registra su
estado vigente. Los criterios para utilizar una referencia completa o parcial
están en [verificación de referencias](../oracle/README.md#verificar-referencias).

## Formatos de salida

Cada línea JSONL es un resultado, sin truncamiento de presentación:

| Consulta | Campos | Comparación |
|---|---|---|
| Q1 | `url`, `date_modified` ISO 8601 con milisegundos | Multiconjunto |
| Q2 | `name`, `url`, `image` nula o descriptor | Multiconjunto; comparar bytes, no fecha de captura |
| Q3 | `word` | Vocabulario único ordenado; rechazar duplicados |
| Q4 | `word`, `count` | Lista exacta por cantidad descendente y palabra ascendente |
| Q5 | `url`, `count` | Multiconjunto |

Q1, Q2 y Q5 se comparan como multiconjuntos: el orden de los resultados no importa,
pero cada resultado debe aparecer exactamente tantas veces como en la referencia.

En Q2, `image: null` indica ausencia en la entrada; `status: pending`, una URL
pendiente de procesar; `status: available`, bytes capturados, y `status: not_found`,
una referencia que respondió HTTP 404. Los fallos no se convierten en ausencia ni
se eliminan sus filas.

## Imágenes compartidas

Los bytes están en `images/<sha256>.bin`. Cada escenario hermano los referencia
con `../images/<sha256>.bin`, relativo a su directorio, y fija ruta, SHA-256,
longitud, URL de origen/resuelta, fecha y cabeceras HTTP. Para salidas fuera de
`tests/expected/`, la carpeta común también se crea junto al escenario, en
`<padre-del-escenario>/images/`.

`images/index.json` asocia cada URL descargada con el descriptor de una captura
exitosa; URLs distintas con los mismos bytes comparten un archivo. Los errores
HTTP 404 permanecen en el escenario que los observó y no se incorporan al índice.
No se debe editar el índice para modificar expectativas: cada escenario fija su propio
hash, y la verificación comprueba esa referencia sin depender del índice.

Es importante versionar en git juntos los escenarios, el índice, los binarios y los
[recursos de stopwords](../oracle/resources/). No borrar imágenes referenciadas
por otros escenarios: una captura no es recuperable sólo a partir de su hash.
Para trasladar las referencias a otra máquina, conservar las carpetas hermanas;
el procedimiento de captura remota está en la [guía del oráculo](../oracle/README.md#completar-q2-con-bytes-de-imágenes).
