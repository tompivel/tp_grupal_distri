# Muestra local de Wikipedia

Inventario verificado el 20 de octubre de 2026 mediante metadatos de los diez
Parquet y lectura por lotes de sus campos relevantes para las consultas.
Se utilizó PyArrow 26.0.0 en un entorno temporal, sin modificar los datos.
Los números siguientes describen **la captura `test-data-v1`**, no el dataset
completo ni necesariamente una captura futura fijada en el manifiesto activo.

El notebook del repositorio identifica como origen
`wikimedia-foundation/wikipedia-structured-contents` en Kaggle. No hay un
identificador de versión de descarga en esta carpeta: no inferirlo a partir de
las fechas de los artículos ni del campo `version` de `schema.json`. Para
reproducir exactamente la entrada, conservar estos archivos y verificar sus hashes.

## Obtener y publicar los archivos exactos

La captura se distribuye como asset de una GitHub Release. El pin de versión y
los hashes de todos los archivos están en [manifest.json](manifest.json),
versionado en Git. Una vez publicada la release correspondiente:

```sh
python3 scripts/dataset.py fetch
python3 scripts/dataset.py verify
```

Para seleccionar otra release sin modificar el manifiesto del checkout:

```sh
python3 scripts/dataset.py fetch --release test-data-v2
python3 scripts/dataset.py verify --manifest dist/dataset/test-data-v2/manifest.json
```

Se obtiene primero el manifiesto pequeño de esa release y se comprueban los datos
locales; el paquete sólo se descarga si faltan archivos y no está en caché. Si hay
archivos locales distintos o sobrantes, se conserva el rechazo a sobrescribirlos;
usar otro destino con `--dataset` para una captura incompatible.

Para añadir Parquet y preparar una nueva captura completa:

```sh
python3 scripts/dataset.py pack --version test-data-v2
```

La [guía de distribución](../scripts/README.md) detalla requisitos, instalación
desde un tar local, actualización de expectativas y publicación de la release.
Los Parquet se excluyen de Git; README, esquemas y manifiesto se versionan.

## Organización y volumen

```text
dataset/
├── README.md
├── manifest.json
├── enwiki/
│   ├── schema.json
│   └── data/
│       └── enwiki_namespace_0_00000.parquet ... 00004.parquet
└── frwiki/
    ├── schema.json
    └── data/
        └── frwiki_namespace_0_00000.parquet ... 00004.parquet
```

Hay cinco archivos por idioma, todos con **25.000 filas**. En total son
**250.000 registros**, mitad ingleses y mitad franceses. Cada archivo tiene 13
grupos de filas: doce de 2.048 y uno de 424. La compresión observada es ZSTD.
Cada fila representa un registro de artículo; no debe asumirse que un artículo
o URL aparece una sola vez, ni eliminar registros repetidos al preparar tests.

| Idioma / índice de archivo | Bytes de Parquet | Filas |
|---|---:|---:|
| en / 00000 | 59.780.794 | 25.000 |
| en / 00001 | 60.235.879 | 25.000 |
| en / 00002 | 56.790.159 | 25.000 |
| en / 00003 | 49.985.194 | 25.000 |
| en / 00004 | 47.252.556 | 25.000 |
| fr / 00000 | 19.837.597 | 25.000 |
| fr / 00001 | 38.286.596 | 25.000 |
| fr / 00002 | 45.650.619 | 25.000 |
| fr / 00003 | 44.439.429 | 25.000 |
| fr / 00004 | 45.104.994 | 25.000 |
| **Total** | **467.363.817** | **250.000** |

Inglés ocupa 274.044.582 bytes y francés 193.319.235 bytes.
El total equivale a **467,36 MB decimales / 445,71 MiB**, sin contar
`schema.json`, este README ni futuras imágenes descargadas.
No representa memoria descomprimida ni un balance de carga entre idiomas.

## Esquema real

Los dos idiomas tienen las mismas **19 columnas principales**, todas declaradas
nullable. Eso permite valores ausentes aunque algunos campos estén completos en
esta muestra. Hay 65 columnas hoja físicas en inglés y 62 en francés debido a
una diferencia anidada en `version`.

| Campo | Tipo Arrow observado | Interpretación para ingesta y consultas |
|---|---|---|
| `abstract` | `string` | Texto de Q3/Q4/Q5; puede ser nulo |
| `additional_entities` | `list<struct>` | Entidades adicionales: aspectos, identificador y URL |
| `date_created` | `timestamp[ms]` | Fecha de creación; mayormente ausente, no usar para los cortes de las consultas |
| `date_modified` | `timestamp[ms]` | Última modificación; corte hasta 2020 inclusive / desde 2021 |
| `description` | `string` | Descripción breve, distinta del abstract |
| `event` | `struct` | Metadatos del evento: fechas en string, contador/motivo de fallo, identificador y tipo |
| `identifier` | `int64` | ID del artículo; conservar como entero, no como identidad única de ocurrencia |
| `image` | `struct<content_url: string, height: int64, width: int64>` | Referencia de imagen principal, no sus bytes |
| `in_language` | `struct<identifier: string>` | Idioma en `in_language.identifier`: `en` o `fr` |
| `infoboxes` | `string` | Contenido serializado; no es un struct Arrow |
| `is_part_of` | `struct<identifier: string, url: string>` | Proyecto al que pertenece |
| `license` | `list<struct>` | Identificador, nombre y URL de licencia |
| `main_entity` | `struct<identifier: string, url: string>` | Entidad principal |
| `name` | `string` | Nombre/título del artículo |
| `references` | `list<struct>` | Referencias con identificador, metadatos, fuente, texto y enlaces |
| `sections` | `string` | JSON que debe decodificarse para obtener las secciones |
| `tables` | `string` | Contenido serializado; no es una lista Arrow |
| `url` | `string` | URL del artículo, distinta de `image.content_url` |
| `version` | `struct` | Revisión/editor/puntajes; **difiere entre idiomas** |

Los timestamps no tienen zona horaria en el esquema Arrow. Preservar su valor y
unidad; no aplicar conversiones a la zona local de la máquina al decidir el año.
El dataset usa `image`, singular. No sustituirlo por un supuesto campo `images`
ni elegir una imagen de una sección.

`sections` no es directamente una lista de diccionarios al leer el Parquet.
En los valores no nulos inspeccionados se pudo decodificar el texto con
`json.loads`; las secciones contienen el campo `name`. Q2 compara ese nombre
completo en minúsculas con `biography` o `biographie`, sin búsqueda de subcadenas.
La validez del resto de los campos serializados no se auditó exhaustivamente.

### Diferencias entre inglés y francés

Los cinco archivos ingleses comparten esquema entre sí, y lo mismo ocurre con
los cinco franceses. Sus columnas de las consultas son compatibles; la diferencia
está en `version`:

- Inglés incluye `version.is_breaking_news`, `version.is_flagged_stable` y
  `version.noindex` como booleanos; francés no incluye esos campos.
- `version.scores.referencerisk.reference_risk_score` es `double` en inglés e
  `int64` en francés.

`enwiki/schema.json` tiene `version: 1`, `num_fields: 19`, `field_names` y
`arrow_ipc_hex`, que codifica el esquema Arrow completo. Coincide con los cinco
archivos ingleses, ignorando metadatos adicionales. **No describe exactamente
los archivos franceses**. Se agregó `frwiki/schema.json`, que coincide con el esquema
francés verificado el 22 de octubre de 2026. Leer el footer de cada Parquet y el
esquema auxiliar de su idioma; no imponer el inglés a todos los archivos.

Para decodificar el esquema auxiliar con PyArrow:

```python
import json
import pyarrow as pa

with open("dataset/enwiki/schema.json") as source:
    metadata = json.load(source)
schema = pa.ipc.read_schema(
    pa.BufferReader(bytes.fromhex(metadata["arrow_ipc_hex"]))
)
```

Si se materializan particiones de clientes, conservar archivos separados por
esquema/origen. Unificar estructuras o convertir enteros a flotantes requiere
una decisión explícita y puede perder información. El cliente debe enviar
registros completos: la proyección de columnas corresponde al rol `Project`.
El notebook serial sí puede seleccionar las columnas que necesita para analizar.

## Cobertura observada

Conteos obtenidos leyendo `date_modified`, `in_language`, `abstract`, `sections`
e `image`, además de verificar nulos en campos identificatorios. Son métricas
de inventario: **no reemplazan los resultados esperados del notebook**.

| Propiedad | Inglés | Francés | Total |
|---|---:|---:|---:|
| Fecha de modificación hasta 2020 inclusive | 7.995 | 12.752 | 20.747 |
| Fecha de modificación desde 2021 | 117.005 | 112.248 | 229.253 |
| Abstract nulo | 470 | 1.373 | 1.843 |
| Abstract histórico no nulo | 7.985 | 12.644 | 20.629 |
| Imagen ausente / sin URL de contenido | 101.619 | 86.291 | 187.910 |
| Candidatos Q2: fecha histórica y sección de biografía | 6 | 681 | 687 |
| Candidatos Q2 con URL de imagen | 2 | 217 | 219 |
| Candidatos Q2 sin URL de imagen | 4 | 464 | 468 |

- No se observaron nulos en `identifier`, `name`, `url`, `date_modified` ni
  `in_language`; los idiomas de todas las filas coincidieron con sus carpetas.
- Hay 249.478 valores nulos en `date_created` y nueve en `sections`, estos últimos
  en inglés. No se observaron abstracts iguales a la cadena vacía `""`;
  esto no afirma ausencia de cadenas compuestas sólo por espacios.
- Las fechas de modificación van desde `2008-01-03T23:08:10` hasta
  `2025-03-23T15:58:04`, sin zona declarada. No identifican la versión de descarga.
- Las 219 referencias de imagen de candidatos Q2 son un conteo de registros,
  no de URLs distintas ni de descargas exitosas. No se descargaron imágenes en
  esta inspección. Una misma imagen puede corresponder a varios resultados.
- En Q5 hay 118 registros históricos con abstract nulo. El denominador computable
  del corpus completo sería 20.629 bajo la regla de excluir nulos; para las pruebas
  debe calcularse de nuevo con la entrada de cada cliente.

La muestra tiene cobertura muy desigual de Q2 entre idiomas. Complementarla con
casos pequeños de ambos idiomas, imágenes presentes/ausentes y descarga fallida.
No modificar fechas o registros originales para fabricar esos casos: mantener
los ejemplos sintéticos como escenarios independientes y explícitos.

## Contrato de las consultas

Los [requisitos funcionales](../docs/requisitos.md#requerimientos-funcionales)
definen las salidas y reglas de conteo de Q1–Q5. El
[mapa de documentación](../docs/README.md#precedencia-de-fuentes) indica qué
fuente prevalece ante diferencias con el informe o propuestas históricas.
El [oráculo serial](../tests/oracle/README.md) documenta la generación de
referencias, las stopwords versionadas y la comparación de resultados.

La tokenización del diseño excluye tokens numéricos y normaliza a minúsculas.
Antes de generar referencias, fijar el contrato de tokenización y la lista de
stopwords que compartirá el sistema con el oráculo.

La deduplicación de palabras de Q4 no autoriza deduplicar filas. Identificar cada
ocurrencia por snapshot, ruta relativa e índice de fila; no por título o URL.
No hay listas de stopwords, imágenes binarias ni resultados esperados en esta
muestra.

## Reproducción del inventario

Desde la raíz del repositorio, en un entorno con PyArrow, este código imprime
metadatos y hashes sin cargar el dataset completo en memoria:

```python
from pathlib import Path
import hashlib
import pyarrow.parquet as pq

for path in sorted(Path("dataset").glob("*wiki/data/*.parquet")):
    parquet = pq.ParquetFile(path)
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    print(path, path.stat().st_size, parquet.metadata.num_rows,
          parquet.metadata.num_row_groups, digest)
    print(parquet.schema_arrow)
```

`hashlib.file_digest` requiere Python 3.11 o posterior
([documentación de Python](https://docs.python.org/3/library/hashlib.html#hashlib.file_digest)).
Para inspeccionar contenido
usar `parquet.iter_batches(batch_size=256, columns=[...])`; no tratar Parquet como
un archivo de líneas ni depender del tamaño de lote para identificar las filas.
Un límite de filas por lote no es un límite estricto de memoria en bytes.

Hashes SHA-256 de la muestra inspeccionada; los índices corresponden a los nombres
completos de archivos del árbol anterior:

| Idioma / índice | SHA-256 |
|---|---|
| en / 00000 | `447bc19043362c033e6550c0d3cd3a1dd395b71c8b816efa6f83da4d1b854831` |
| en / 00001 | `a21c9eb62596018084dc55a800bbcaf10603a749623c9134ab0e343f210eb513` |
| en / 00002 | `3b125e332042fabd8f4774eb34e2465236154888e82c6cf122dc00b2b5db7820` |
| en / 00003 | `8fa80621cbdad2e1d5420a6d1ad450d59fb3ed6a9caa29404ca1e2a25844f519` |
| en / 00004 | `449b5a03576e5001a23920119daff091f31296f2e34c5a308612c6916c05c9c7` |
| fr / 00000 | `976b2b4fdfca8fee886365aac790ff4d23903b430be63191aec8f60a910307f9` |
| fr / 00001 | `dd97529a9a2bac592ee136f4cc8303727a357ac615f2aaa918995a017527b2ab` |
| fr / 00002 | `25b45cb57d3bfbae5d12124a4bb66e9f8f0f2fc2221f7183ed13950dfd84bd5b` |
| fr / 00003 | `905ffa4a5568e39542fb260989e9e24e291d52b64331d3cf37f81b8d7527fab9` |
| fr / 00004 | `ddc06cf7412e3465b056a068f0a7dcb8f37fac92ccd73f49461787de2529368a` |

El reparto propuesto para cinco clientes y la estrategia de validación están en
[tests/README.md](../tests/README.md). La receta de descarga está en la
[guía de distribución](../scripts/README.md). Esta captura se conserva en una
release propia; no se presupone que se pueda reconstruir el mismo snapshot
descargando nuevamente desde Kaggle.
