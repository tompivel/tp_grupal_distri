# Referencias seriales con el notebook

Esta herramienta prepara resultados esperados (sin utilizar paquetes Go del sistema distribuido). Se ejecuta
manualmente cuando se define o modifica un escenario. Las pruebas del sistema
deberán leer estos archivos y nunca regenerarlos como parte de su corrida.

El notebook de entrada es `wikipedia-article-analysis.ipynb`, en la raíz. Se adaptó
para leer datos locales y ejecutar las cinco consultas separadamente para cada
cliente. El generador `reference.py` contiene su cálculo serial y el soporte de archivos; es
independiente de cualquier implementación Go.

## Instalación

El proyecto está en `tests/oracle/pyproject.toml`; `uv.lock` fija también las
dependencias transitivas y `.python-version` selecciona Python 3.14.8. Instalar
[uv](https://docs.astral.sh/uv/getting-started/installation/) si no está disponible
y sincronizar desde la raíz del repositorio:

```sh
uv sync --project tests/oracle --locked
```

El entorno se crea en `tests/oracle/.venv/`, excluido de Git. Los comandos con
`--locked` rechazan cambios pendientes del lockfile; no lo actualizan durante la
prueba. Para cambiar dependencias, modificar `pyproject.toml`, ejecutar
`uv lock --project tests/oracle` y revisar/versionar ambos archivos juntos.

Para las descargas nuevas, configurar en el `.env` de la raíz (ignorado por Git):

```dotenv
WIKIMEDIA_OPERATOR_NAME="Nombre del operador"
WIKIMEDIA_OPERATOR_EMAIL="contacto@example.org"
```

El descargador construye el User-Agent con esos valores; las variables del entorno
prevalecen sobre el archivo local. El contacto se envía a Wikimedia en esa cabecera,
pero no se copia al código ni a los manifiestos de resultados. Sin contacto válido
la captura falla antes de solicitar imágenes. Reutilizar bytes ya capturados no
necesita contacto ni conexión de red.

Los comandos siguientes se ejecutan desde la raíz del repositorio. Las stopwords
inglesas y francesas de NLTK ya están guardadas en `resources/`: no se descarga
ningún corpus al calcular las consultas. Su procedencia, fecha y hashes están en
`stopwords-provenance.json`. `stopwords-union.txt` contiene las 346 palabras únicas
ordenadas que debe adoptar el sistema para comparar contra estas referencias.
Conservar también el aviso de procedencia original `stopwords-source.txt`.

## Piloto y muestra completa

Primero, un piloto con 100 filas de cada uno de los diez archivos: 1.000 registros
totales, 200 por cliente. El destino debe ser nuevo.

```sh
uv run --project tests/oracle --locked python tests/oracle/run_notebook.py --output /tmp/wiki-oracle-pilot --rows-per-file 100
uv run --project tests/oracle --locked python tests/oracle/reference.py verify /tmp/wiki-oracle-pilot --dataset dataset --allow-incomplete-q2
```

Ese piloto comprueba la lectura y exportación; no garantiza resultados positivos
en todas las consultas. Los casos pequeños de `test_reference.py` verifican las
reglas de conteo con expectativas escritas a mano.

Para los diez archivos completos, cinco clientes y **250.000 filas / 467.363.817
bytes de Parquet**, ejecutar una vez:

```sh
uv run --project tests/oracle --locked python tests/oracle/run_notebook.py --output tests/expected/full-5clients-v1
```

El comando ejecuta el notebook real, guarda sus salidas y conserva una copia
ejecutada en el destino. También puede abrirse el notebook en Jupyter y ejecutarse
manualmente: revisar `CLIENTS`, `ROWS_PER_FILE`, `OUTPUT` y `DOWNLOAD_IMAGES` en
la primera celda de código. `run_notebook.py` configura esos valores mediante
variables de entorno para poder realizar un piloto sin editar el notebook.

No se sobrescriben carpetas existentes. Para generar otra referencia, usar un
nombre nuevo, por ejemplo `full-5clients-v2`. El cálculo es serial, un cliente a
la vez; lee lotes de campos analíticos, no concatena todo el corpus en RAM. La
memoria utilizada por vocabularios y candidatos de un cliente sí crece con su
entrada: esta herramienta de referencia no representa al sistema distribuido.

## Partición exacta de la entrada

`manifest.json` lista archivos con ruta relativa a `dataset/`, SHA-256, esquema,
filas totales y seleccionadas, y posición global inicial. El orden es:

```text
en/00000, fr/00000, en/00001, fr/00001, ..., en/00004, fr/00004
```

Para un archivo con `global_offset = O`, la fila física `r`, empezando en cero,
pertenece al cliente `(O + r) % clients`. Sólo se incluyen filas
`0 <= r < selected_rows`. `global_offset` acumula las filas seleccionadas de los
archivos anteriores. La selección no depende de los grupos de filas ni del lote
de lectura. Las filas originales repetidas se conservan como ocurrencias distintas.

En el escenario completo, cada cliente recibe 50.000 filas: 25.000 por idioma.
No se crean copias de las entradas. Cuando exista el cliente Go, podrá consumir
esa selección o materializarla automáticamente en archivos temporales, conservando
sus 19 columnas y los esquemas por idioma. El oráculo puede proyectar columnas;
el cliente del sistema debe transmitir registros íntegros.

## Completar Q2 con bytes de imágenes

El cálculo local deja las referencias de imagen en estado `pending`. Las filas
sin referencia tienen `image: null`, como ausencia explícita. Una referencia que
no pudo descargarse nunca se convierte en ausencia ni en una salida exitosa.

Ejecutar explícitamente la captura de red:

```sh
uv run --project tests/oracle --locked python tests/oracle/reference.py capture-images tests/expected/full-5clients-v1
uv run --project tests/oracle --locked python tests/oracle/reference.py verify tests/expected/full-5clients-v1 --dataset dataset
```

La captura descarga el contenido original de cada URL `image.content_url` por
HTTPS, en serie y una sola vez por URL; no sustituye imágenes por miniaturas.
El notebook original dejaba pendiente esta descarga. El oráculo usa la referencia
del Parquet directamente; el fetcher del sistema puede obtener sus metadatos por
la API de Wikimedia. Para una regresión reproducible deberá entregar los mismos
bytes congelados en este paquete.

Cada imagen disponible registra ruta, SHA-256, longitud, URL de origen/resuelta,
fecha y cabeceras HTTP. Se conserva en la carpeta común
`tests/expected/images/<sha256>.bin`; cada escenario hermano la referencia con
`../images/<sha256>.bin`. Para salidas fuera de `tests/expected/`, la carpeta común
también se crea junto al escenario, en `<padre-del-escenario>/images/`.

`images/index.json` asocia cada URL descargada con su descriptor. `capture-images`
consulta ese índice para las referencias pendientes: verifica los bytes y los
reutiliza antes de acceder a la red. Una descarga nueva agrega la URL al índice;
URLs distintas con los mismos bytes comparten un archivo por SHA-256. El índice
sólo contiene descargas exitosas; los 404 permanecen en cada escenario. No editar
el índice para modificar expectativas: cada escenario fija su propio hash, y
`verify` comprueba esa referencia sin depender del índice. Una imagen ausente o
corrupta produce error; no se reemplaza automáticamente descargándola de nuevo.

Ejecutar una sola captura a la vez, incluso entre escenarios, para mantener simple
la escritura del índice común. El contador `reused_from_store` de cada sesión
informa cuántas URLs pendientes se reutilizaron desde esa carpeta.

El límite por archivo
es 64 MiB y el timeout de conexión/lectura es de 30 segundos; se puede cambiar este
último mediante `--timeout 60`. No hay reintentos automáticos. Los HTTP 404 se
registran en `image-404-errors.jsonl` y en el manifiesto; la imagen queda como
`status: not_found`, con URL, fecha y diagnóstico, y se continúa con las siguientes.
Las filas afectadas se conservan y nunca se convierten en `image: null`. Si una
URL se repite, se reutiliza su diagnóstico sin volver a solicitarla; las URLs ya
marcadas como `not_found` tampoco se reintentan en invocaciones posteriores.

Los demás errores, incluidos HTTP 429, fallos de red y timeouts, detienen la
captura y conservan el progreso. Se utiliza una sola descarga a la vez,
con una pausa mínima de tres segundos después de cada descarga antes de iniciar
la siguiente. `--interval 5` permite aumentar esa pausa. El timeout limita la
espera de red, mientras que el intervalo limita la frecuencia de solicitudes.

Ante un error HTTP se registran el código y `Retry-After`. Si el servidor indica
un plazo en segundos o una fecha HTTP, una nueva captura rechaza solicitudes antes
de ese plazo. Cada intento registra cuántas URLs intentó y descargó, sus tiempos,
el intervalo y el hash del lockfile, sin incluir los datos de contacto.
Una invocación manual posterior verifica
y reutiliza los bytes ya capturados antes de solicitar los pendientes.

Si esta máquina no tiene acceso a Wikimedia, copiar **el escenario, su carpeta
hermana `images/` y `tests/oracle/` con sus recursos** a una máquina con acceso,
conservando las rutas relativas, y sincronizar el mismo
lockfile con uv y ejecutar `capture-images` allí. Si el servidor responde HTTP 429,
respetar `Retry-After` si lo informa o esperar antes de una nueva invocación manual;
no ejecutar reintentos continuos. La captura no necesita los Parquet; para verificar también la entrada,
añadir después `--dataset dataset` en una máquina que los conserve. Retornar el
escenario con el manifiesto actualizado y la carpeta común de imágenes, incluido
su índice. Las URLs con 404
permanecen identificadas para revisión del equipo; no se sustituyen por otra imagen
ni se borran sus filas. Haber agotado las URLs pendientes no completa Q2 si siguen
faltando esos bytes.

## Artefactos y estado de validez

```text
tests/expected/
├── images/                 # Compartida por los escenarios hermanos
│   ├── index.json          # URL → descriptor de una captura exitosa
│   └── <sha256>.bin
└── full-5clients-v1/
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

Cada línea JSONL es un resultado, sin truncamiento de presentación:

| Consulta | Campos y comparación futura                                                                                     |
| -------- | --------------------------------------------------------------------------------------------------------------- |
| Q1       | `url`, `date_modified` ISO 8601 con milisegundos; multiconjunto                                                 |
| Q2       | `name`, `url`, `image` nula o descriptor de bytes; multiconjunto, comparando los bytes y no la fecha de captura |
| Q3       | `word`; vocabulario único ordenado                                                                              |
| Q4       | `word`, `count`; lista exacta ordenada por cantidad descendente y palabra ascendente                            |
| Q5       | `url`, `count`; multiconjunto, con conteo de ocurrencias                                                        |

El manifiesto contiene versión semántica, hashes de stopwords, fuentes del
generador, versiones del entorno y estadísticas por cliente. Q5 guarda la suma
histórica `S`, cantidad computable `N` y estado `no_historical_base` si `N == 0`.
Se excluyen abstracts históricos nulos; uno vacío no nulo aporta cero y sí integra
`N`. Un candidato se emite sólo si `count * N > S`, sin redondear el promedio.

`executed.ipynb` conserva el estado observado durante la ejecución del notebook.
Si las imágenes se capturan después mediante el comando separado, el estado
vigente es el del manifiesto, que se actualiza junto a Q2.

`verify` comprueba integridad y rechaza por defecto cualquier paquete con imágenes
pendientes o con 404. La auditoría informa `q2_pending_records` y
`q2_not_found_records` por separado, y comprueba la integridad del registro de
404. `--allow-incomplete-q2` sirve únicamente para auditar los archivos ya
generados: su salida mantiene explícitamente `status: incomplete_images` y no
autoriza a validar Q2. Sólo `manifest.status == complete` habilita la referencia
entera Q1–Q5. `capture-images` puede terminar normalmente con estado incompleto
si revisó todas las URLs y sólo quedaron 404; la verificación estricta sigue
rechazando esa referencia. Los hashes no reemplazan una revisión semántica del oráculo.

Las otras cuatro consultas pueden utilizarse mientras se completa Q2, siempre
declarando ese alcance. Guardar el paquete y los recursos de stopwords juntos en
el repositorio/proyecto, junto con la carpeta común `images/`; una Q2 capturada no
es recuperable sólo a partir de su hash. La verificación también admite las rutas
antiguas `images/...` internas de un escenario.

Para revisar el oráculo antes de generar referencias:

```sh
uv run --project tests/oracle --locked python -m unittest discover -s tests/oracle -p 'test_*.py' -v
```

Si cambia la entrada de un cliente, la lista de stopwords o alguna regla, preparar
una referencia nueva manualmente. Cambiar sólo concurrencia, réplicas o el orden
de envío permite reutilizar las respuestas. La equivalencia con Go queda pendiente
de usar el mismo contrato Unicode, stopwords y reglas; no se asume validada por
haber ejecutado este notebook.

Fuentes de las dependencias y captura: [datos NLTK](https://www.nltk.org/data.html),
[ejecución de notebooks con NBClient](https://nbclient.readthedocs.io/en/latest/),
[metadatos de imágenes Wikimedia](https://www.mediawiki.org/wiki/API:Imageinfo).

Gestión del entorno: [proyectos uv](https://docs.astral.sh/uv/guides/projects/),
[lockfiles](https://docs.astral.sh/uv/concepts/projects/sync/) y
[lectura de .env](https://bbc2.github.io/python-dotenv/).
