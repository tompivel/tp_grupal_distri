# Distribución del dataset de pruebas

`dataset.py` usa Python **3.10 o posterior**, sin paquetes adicionales. Para
descargar desde GitHub se necesita además [GitHub CLI](https://cli.github.com/).
Los ejemplos se ejecutan desde la raíz del repositorio; los destinos por defecto
se resuelven respecto del repositorio incluso al invocar el script desde otra carpeta.

Cada manifiesto fija el repositorio, el tag de la release, el nombre/tamaño/SHA-256
del paquete y la lista exacta de archivos con sus tamaños y hashes. El de
`dataset/manifest.json`, versionado en Git, selecciona la captura por defecto del
checkout; no registra qué datos están instalados localmente. También se puede
elegir una release explícita con `fetch --release`. No se usa `latest`.

## Obtener los datos como developer

Después de clonar el repositorio, y una vez publicada la release fijada:

```sh
gh auth login
python3 scripts/dataset.py fetch
```

La autenticación de `gh` se prepara una sola vez; también puede usarse un
`GH_TOKEN` ya configurado. Para un repositorio privado la cuenta debe tener
acceso. Si la captura local ya coincide, `fetch` verifica sus hashes y termina
sin acceder a la red ni necesitar `gh`.

La descarga se guarda en `dist/dataset/`, se valida contra el manifiesto de Git
y se desempaqueta en un directorio temporal. Se comprueban todos los archivos
antes de instalar los faltantes en `dataset/`. Un archivo parcial descargado no
queda en la caché. El paquete y los Parquet están excluidos de Git.

Para elegir otra release sin editar el manifiesto versionado:

```sh
python3 scripts/dataset.py fetch --release test-data-v2
python3 scripts/dataset.py verify --manifest dist/dataset/test-data-v2/manifest.json
```

En la primera invocación se descarga **sólo el asset `manifest.json`** de esa
release. Se valida su formato y que el tag y el repositorio coincidan con lo
solicitado, y se guarda en `dist/dataset/<release>/manifest.json`. Luego se
verifican los archivos locales contra ese manifiesto. Si ya coinciden, no se
descarga el tar; si faltan archivos, se usa el paquete en caché o se descarga.
Si ya está el manifiesto en caché, se reutiliza y la comprobación puede hacerse
sin conexión. El tar sigue guardándose en `dist/dataset/dataset-<release>.tar`.

Con `--release`, los hashes esperados provienen del manifiesto adjunto a la
release elegida. `fetch` sin opciones conserva la selección fijada en el checkout;
también acepta `--manifest` para un manifiesto local alternativo. `--release` y
`--manifest` son excluyentes. Ninguna descarga modifica `dataset/manifest.json`.
`verify` siempre comprueba el manifiesto local indicado y nunca accede a la red;
sin `--manifest`, usa el del checkout, aunque se haya descargado otra release.

Para otro repositorio, usar `fetch --release TAG --repo OWNER/REPO`. Si se usan
tags iguales en distintos forks, elegir otro `--cache-dir`; se rechaza reutilizar
un manifiesto cacheado que pertenezca a otro repositorio.

Para comprobar la instalación más tarde, sin descargar:

```sh
python3 scripts/dataset.py verify
```

Si se recibió el `.tar` por otro medio, usar igualmente el manifiesto del commit
correspondiente:

```sh
python3 scripts/dataset.py unpack dist/dataset/dataset-test-data-v1.tar
```

También se puede seleccionar otro destino, otra caché u otro manifiesto:

```sh
python3 scripts/dataset.py fetch --dataset /tmp/wiki-test-data --cache-dir /tmp/wiki-cache
python3 scripts/dataset.py fetch --release test-data-v2 --dataset /tmp/wiki-test-data-v2
python3 scripts/dataset.py verify --dataset /tmp/wiki-test-data-v2 --manifest dist/dataset/test-data-v2/manifest.json
python3 scripts/dataset.py unpack /ruta/dataset-test-data-v1.tar --dataset /tmp/wiki-test-data --manifest dataset/manifest.json
```

**No se sobrescriben datos locales distintos ni se borran archivos sobrantes.**
Si hay Parquet o esquemas ajenos al manifiesto, el script falla para evitar mezclar
capturas. Para cambiar a una captura incompatible, usar un destino nuevo o guardar
los directorios de datos anteriores fuera de `dataset/` antes de descargar.
Los archivos iguales se conservan y los faltantes se pueden completar.
También con `--release`, estos conflictos se detectan antes de descargar el tar.
README y otros archivos que no sean Parquet o `schema.json` quedan intactos.

Conservar espacio para el paquete y para el contenido desempaquetado. La caché
puede borrarse manualmente cuando ya no se necesite. Si un paquete en caché está
corrupto, el script falla: apartar ese `.tar` y repetir la descarga.
No ejecutar tests ni modificar los datos mientras se están instalando.

## Crear o actualizar la captura como developer

El paquete es una captura **completa**, no un delta. El script descubre
recursivamente todos los `*.parquet` y `schema.json` bajo `--dataset`; no tiene
fijada la cantidad de archivos ni de idiomas. No lee ni transforma las filas.
Conserva los bytes, los esquemas distintos por idioma y los registros repetidos.
Rechaza enlaces simbólicos y no incluye `.env`, documentación ni imágenes externas.
Esto valida transporte e integridad; la validez del formato y la semántica se
comprueban por separado con el oráculo y los tests.

Para añadir, por ejemplo, `enwiki_namespace_0_00005.parquet`, copiarlo a
`dataset/enwiki/data/` y mantener los esquemas de cada idioma correctos. El
oráculo actual sólo selecciona rutas `*wiki/data/*_namespace_0_*.parquet`; mantener
esa convención para que los archivos añadidos también participen de las consultas.
Si se añaden idiomas distintos de inglés y francés, primero se debe adaptar el
contrato del oráculo, que actualmente sólo acepta esos dos.

Después, elegir una versión nueva:

```sh
python3 scripts/dataset.py pack --version test-data-v2
python3 scripts/dataset.py verify
```

Se generan:

```text
dist/dataset/dataset-test-data-v2.tar  # Asset a subir; ignorado por Git.
dataset/manifest.json                 # Pin de la nueva captura; versionar en Git.
```

`pack` actualiza el manifiesto activo sólo si cambia el tag; no reemplaza un
paquete existente. Con el mismo tag permite reconstruir un tar faltante sólo si
todo, incluido su hash, coincide con el pin existente; el manifiesto queda intacto.
Las capturas anteriores se conservan en sus releases y sus
manifiestos en el historial de Git. Es posible usar `--manifest` para guardar
otra referencia sin cambiar el pin activo, y `--repo OWNER/REPO` para otro fork.
No modificar los datos durante el empaquetado.

El tar tiene rutas relativas y metadatos normalizados, sin compresión adicional:
los Parquet actuales ya usan ZSTD. Con los mismos archivos, el paquete se puede
reconstruir con los mismos bytes usando este generador. Se rechazan paquetes de
2 GiB o más por el límite de tamaño de assets; si se llega a ese volumen habrá que
dividir la captura y extender el formato del manifiesto y el descargador.

**Cambiar la entrada requiere generar nuevas expectativas**, manteniendo las
anteriores. Para una nueva captura de los mismos idiomas y consultas:

```sh
uv run --project tests/oracle --locked python tests/oracle/run_notebook.py --output tests/expected/full-5clients-v2
```

Seguir la [guía del oráculo](../tests/oracle/README.md) para revisar las salidas,
capturar las imágenes de Q2 y auditar el paquete de referencias. Esto se hace
manualmente al preparar el escenario; los tests no regeneran sus expectativas.
`dataset/manifest.json` describe la distribución de la entrada; los manifiestos
en `tests/expected/` describen las referencias y su entrada específica. No son
intercambiables.

## Publicar releases

Publicar es un paso separado; `pack` no hace
commits, pushes ni publicaciones. Para prepararlo desde cero, el comando es
`python3 scripts/dataset.py pack --version test-data-vx`.

1. Autenticarse, verificar la captura y crear el borrador con los dos assets:

   ```sh
   gh auth login
   python3 scripts/dataset.py verify
   gh release create test-data-vx \
     dist/dataset/dataset-test-data-vx.tar dataset/manifest.json \
     --repo tompivel/tp_grupal_distri \
     --target "$(git rev-parse HEAD)" \
     --title "Dataset de pruebas vx" \
     --notes "Captura fija: 250.000 filas en diez Parquet (en/fr), dos esquemas y hashes SHA-256. Obtener con python3 scripts/dataset.py fetch desde el commit de esta release." \
     --draft --latest=false
   ```

   El tag se crea sobre el commit ya subido. Adjuntar ambos assets es necesario
   para `fetch --release`: primero obtiene `manifest.json` y sólo descarga el tar
   si hace falta. `fetch` sin opciones sigue usando el manifiesto del checkout.

3. Revisar el borrador en GitHub y publicar:

   ```sh
   gh release view test-data-vx --repo tompivel/tp_grupal_distri --web
   gh release edit test-data-vx --repo tompivel/tp_grupal_distri --draft=false
   ```

   Alternativamente: abrir **Releases → Draft a new release**, elegir el tag y el
   commit, adjuntar el `.tar` generado y `dataset/manifest.json`, completar la
   descripción y publicar. Adjuntar el tar propio; el archivo automático
   **Source code** de GitHub no contiene los Parquet ignorados.

Para siguientes releases, repetir con `test-data-v{x+1}`, su paquete, el manifiesto
actualizado y notas que describan los cambios y las nuevas referencias. No
reemplazar los assets ni mover el tag de una captura ya publicada.

Referencias: [crear releases con gh](https://cli.github.com/manual/gh_release_create),
[descargar assets](https://cli.github.com/manual/gh_release_download),
[publicar un borrador](https://cli.github.com/manual/gh_release_edit) y
[límites de Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).

## Verificación del generador

```sh
python3 -m unittest discover -s tests/dataset -v
```

Los casos usan bytes pequeños y una descarga simulada; no necesitan PyArrow ni
acceso a GitHub. Cubren capturas ampliadas, roundtrip exacto, integridad, caché,
descarga del manifiesto antes del tar, reutilización local sin red, selección de
release/repositorio, conflictos locales y rechazo de rutas peligrosas o miembros
inválidos del tar.
