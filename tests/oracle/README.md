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

Los comandos siguientes se ejecutan desde la raíz del repositorio.

## Contrato serial

Las consultas responden a los [requisitos funcionales](../../docs/requisitos.md#requerimientos-funcionales).
El contrato usado por estas referencias se llama **`wiki-serial-v1`**. Lo registra
`contract()` en [reference.py](reference.py) y queda congelado en `semantics` del
manifiesto de cada escenario, incluida la versión Unicode del generador.

La tokenización usa `str.lower()` de Python y la expresión `\b\w+\b`, sin
quitar acentos ni aplicar stemming. Excluye los tokens que coinciden por completo
con `[+-]?((\d+\.?\d*)|(\.\d+))` y las stopwords. Para Q2, compara el nombre
completo de la sección en minúsculas con `biography` o `biographie`, sin búsqueda
de subcadenas.

Las stopwords inglesas y francesas de NLTK están guardadas en [resources/](resources/):
no se descarga ningún corpus al calcular las consultas. Su procedencia, fecha y
hashes están en [stopwords-provenance.json](resources/stopwords-provenance.json).
[stopwords-union.txt](resources/stopwords-union.txt) contiene las 346 palabras
únicas ordenadas usadas por el oráculo. Conservar también el aviso original
[stopwords-source.txt](resources/stopwords-source.txt).

Q5 calcula por cliente la suma histórica `S` y la cantidad de abstracts históricos
computables `N`. Excluye los nulos; uno vacío no nulo aporta cero y sí integra `N`.
Emite un candidato sólo si `count * N > S`, sin redondear el promedio. Si `N == 0`,
produce un resultado vacío con estado `no_historical_base`.

La equivalencia con Go queda pendiente de adoptar y verificar el mismo contrato
Unicode, stopwords y reglas. Ejecutar el notebook no valida el sistema distribuido.

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

Para la [muestra completa](../../dataset/README.md#organización-y-volumen), con
cinco clientes, ejecutar, por ejemplo:

```sh
uv run --project tests/oracle --locked python tests/oracle/run_notebook.py --output tests/expected/full-5clients-v2
```

El notebook puede ejecutarse varias veces contra el mismo dataset. En cada
ejecución, `--output` debe señalar un directorio que todavía no exista, para
evitar sobrescribir resultados esperados anteriores. 
El comando ejecuta el notebook real, guarda sus salidas y conserva una copia
ejecutada en el destino. También puede abrirse el notebook en Jupyter y ejecutarse
manualmente: revisar `CLIENTS`, `ROWS_PER_FILE`, `OUTPUT` y `DOWNLOAD_IMAGES` en
la primera celda de código. `run_notebook.py` configura esos valores mediante
variables de entorno para poder realizar un piloto sin editar el notebook.

El cálculo es serial, un cliente a la vez; lee lotes de campos analíticos,
no concatena todo el corpus en RAM. La
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

No se crean copias de las entradas. Cuando exista el cliente Go, podrá consumir
esa selección o materializarla automáticamente en archivos temporales, respetando
el [esquema y las condiciones de ingesta](../../dataset/README.md#esquema-real).

## Completar Q2 con bytes de imágenes

El cálculo local deja las referencias de imagen en estado `pending`. Los
[formatos de salida](../expected/README.md#formatos-de-salida) distinguen ausencia,
referencia pendiente, imagen disponible y HTTP 404.

Ejecutar explícitamente la captura de red:

```sh
uv run --project tests/oracle --locked python tests/oracle/reference.py capture-images tests/expected/full-5clients-v2
uv run --project tests/oracle --locked python tests/oracle/reference.py verify tests/expected/full-5clients-v2 --dataset dataset
```

La captura descarga el contenido original de cada URL `image.content_url` por
HTTPS, en serie y una sola vez por URL; no sustituye imágenes por miniaturas.
El notebook original dejaba pendiente esta descarga. El oráculo usa la referencia
del Parquet directamente; el fetcher del sistema puede obtener sus metadatos por
la API de Wikimedia. Para una regresión reproducible deberá entregar los mismos
bytes congelados en este paquete.

`capture-images` consulta el [índice común de imágenes](../expected/README.md#imágenes-compartidas)
para las referencias pendientes: verifica los bytes y los reutiliza antes de
acceder a la red. Una descarga exitosa agrega la URL al índice. Una imagen ausente
o corrupta produce error; no se reemplaza automáticamente descargándola de nuevo.

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
lockfile con uv y ejecutar `capture-images` allí. La captura no necesita los
Parquet; para verificar también la entrada,
añadir después `--dataset dataset` en una máquina que los conserve. Retornar el
escenario con el manifiesto actualizado y la carpeta común de imágenes, incluido
su índice. Para determinar si la captura está completa, aplicar los criterios
de la sección siguiente.

## Verificar referencias

La [guía de artefactos](../expected/README.md) describe los archivos generados y
sus formatos. Para auditar los archivos de un escenario sin exigir que Q2 esté
completa:

```sh
uv run --project tests/oracle --locked python tests/oracle/reference.py verify tests/expected/full-5clients-v1 --dataset dataset --allow-incomplete-q2
```

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
declarando ese alcance. La verificación también admite las rutas antiguas
`images/...` internas de un escenario.

## Actualizar referencias

Si cambia la entrada de un cliente, la lista de stopwords o alguna regla, preparar
una referencia nueva manualmente, conservando las anteriores. Cambiar sólo
concurrencia, réplicas o el orden de envío posterior a la asignación permite
reutilizar las respuestas. Las pruebas del sistema consumen las referencias
preparadas; nunca las regeneran durante su corrida.

Para revisar el oráculo antes de generar referencias:

```sh
uv run --project tests/oracle --locked python -m unittest discover -s tests/oracle -p 'test_*.py' -v
```

Fuentes de las dependencias y captura: [datos NLTK](https://www.nltk.org/data.html),
[ejecución de notebooks con NBClient](https://nbclient.readthedocs.io/en/latest/),
[metadatos de imágenes Wikimedia](https://www.mediawiki.org/wiki/API:Imageinfo).

Gestión del entorno: [proyectos uv](https://docs.astral.sh/uv/guides/projects/),
[lockfiles](https://docs.astral.sh/uv/concepts/projects/sync/) y
[lectura de .env](https://bbc2.github.io/python-dotenv/).
