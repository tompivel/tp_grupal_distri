# Referencias de la muestra local — cinco clientes

Preparadas el 22 de octubre de 2026 mediante el notebook serial. Entrada:
**250.000 filas, 467.363.817 bytes de Parquet**. Cada cliente recibió
50.000 filas: 25.000 inglesas y 25.000 francesas.

**Estado de esta captura: Q1, Q3, Q4 y Q5 completas; Q2 incompleta.**
Hay **218 referencias con bytes guardados, una con HTTP 404 y ninguna pendiente
de procesar**. La última captura intentó 122 URLs: descargó 121 y registró el 404
conocido sin detener las demás descargas. No recibió HTTP 429. La captura inicial
había obtenido dos imágenes; el intento con contacto y pausas obtuvo otras 95.
Se conservaron todas las filas esperadas.

Los 218 binarios están en la [carpeta común de imágenes](../images/), compartida
con los demás escenarios mediante referencias `../images/<sha256>.bin` en Q2.
Su índice permite reutilizar las URLs ya descargadas. 

| Cliente | Q1 | Q2 (candidatos) | Q3 | Q4 | Q5 |
|---|---:|---:|---:|---:|---:|
| client-0 | 1634 | 143 | 16672 | 20 | 16851 |
| client-1 | 1582 | 116 | 17020 | 20 | 17106 |
| client-2 | 1618 | 140 | 16615 | 20 | 16798 |
| client-3 | 1602 | 145 | 16615 | 20 | 17580 |
| client-4 | 1559 | 143 | 16815 | 20 | 16978 |

Q2 tiene 687 candidatos: 468 sin referencia de imagen y 219 con URL.
Los 219 corresponden a URLs distintas. `image: null` representa únicamente
ausencia en la entrada; `status: pending` representa URLs pendientes de procesar
y `status: not_found` conserva una referencia que respondió HTTP 404.

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

Q5 se calculó por cliente mediante `count * N > S`, con repeticiones y sin
stopwords. La suma de denominadores es 20.629: se excluyeron 118 abstracts
históricos nulos. Los archivos de resultados conservan multiplicidades.

## Verificar el resultado de la captura

Desde la raíz del repositorio y con el entorno uv del oráculo activado:

```sh
uv run --project tests/oracle --locked python tests/oracle/reference.py verify tests/expected/full-5clients-v1 --dataset dataset --allow-incomplete-q2
```

Ese comando audita lo generado y muestra explícitamente que Q2 está
incompleta. La verificación sin ese permiso debe fallar mientras falten bytes.
El registro de la URL no disponible está en
[image-404-errors.jsonl](image-404-errors.jsonl), con fecha, código y diagnóstico:

```text
https://upload.wikimedia.org/wikipedia/commons/8/8a/Amelie_Rivat%2C_Giro_Rosa_2016.jpg
```

El descargador registra los 404 como `not_found`, continúa con las demás URLs y
no vuelve a pedir automáticamente las ya registradas. La imagen no se sustituyó
por otra ni se convirtió en ausencia; su fila sigue en Q2. Deberemos
revisar cómo obtener esos bytes o tratar esa indisponibilidad antes de considerar
la referencia completa. La consulta ya está hecha en el campus.

Para futuras capturas pendientes, usando el contacto configurado en `.env`:

```sh
uv run --project tests/oracle --locked python tests/oracle/reference.py capture-images tests/expected/full-5clients-v1
uv run --project tests/oracle --locked python tests/oracle/reference.py verify tests/expected/full-5clients-v1 --dataset dataset
```

Si un intento futuro recibe 429, respetar el `Retry-After` registrado; no hacer
reintentos continuos. También se puede
completar la captura en una máquina con acceso, según la
[guía del oráculo](../../oracle/README.md). La captura conserva las imágenes
ya guardadas y no vuelve a calcular las consultas.

`manifest.json` es el registro vigente de integridad y estado; sólo
`status: complete` habilita Q1–Q5 completas. `executed.ipynb` conserva la
ejecución del cálculo serial previa al paso separado de descarga de imágenes.

Las listas de stopwords congeladas y sus hashes están en
`tests/oracle/resources/`. El manifiesto fija la selección de filas y el
contrato semántico; el sistema Go deberá adoptar las mismas reglas.

El detalle del último intento está en `image_capture_sessions` del manifiesto:
solicitudes intentadas, descargas nuevas, tiempos, intervalo y hash de `uv.lock`.
Los datos de contacto permanecen únicamente en el `.env` local. La fuente del
generador original está archivada en `generator/reference.py` con su SHA-256.
