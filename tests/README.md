# Infraestructura de pruebas: propuesta mínima

Estado al 22 de octubre de 2026: el oráculo serial y su ejecución manual están en
[tests/oracle/README.md](oracle/README.md). El notebook ya permite preparar las
referencias de la muestra local por cliente, independientemente de Go. Todavía
no hay runner integral ni Compose de pruebas, y en este checkout tampoco están
los paquetes Go ni sus comandos de arranque. La primera integración debe permitir
una prueba pequeña de punta a punta apenas estén disponibles esos contratos.

El estado de las [referencias de la muestra completa](expected/full-5clients-v1/README.md)
y la [organización de los artefactos](expected/README.md) se documentan por separado.

## Alcance inicial

Para obtener la entrada completa, consultar la
[guía de distribución](../scripts/README.md#obtener-los-datos-como-developer).

El escenario por defecto será **`tiny`: dos clientes y entre 20 y 40 registros
sintéticos en total**, con el sistema y RabbitMQ reales. El volumen completo del
dataset queda para una ejecución explícita posterior.

La infraestructura no recupera ejecuciones. Ante un error o timeout, guarda las
salidas y logs disponibles, informa fallo y cierra sus recursos. Volver a ejecutar
la prueba crea un entorno limpio y nuevas identidades de ejecución, retransmitiendo
la entrada completa. No hay reanudación, checkpoints ni reintentos automáticos que
puedan ocultar una falla intermitente.

Esto simplifica el runner y respeta el alcance confirmado del sistema: aborto ante
caída abrupta y apagado coordinado ante SIGTERM. Las pruebas exhaustivas de fallos
se difieren; el cierre normal del entorno sigue siendo ordenado, con RabbitMQ al
final. No se agregan mecanismos de recuperación al producto para poder testearlo.

## Qué conservar, simplificar y diferir

| Parte de la propuesta anterior                           | Primera implementación                                                                                 |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Orquestador genérico y muchos escenarios                 | Un script que inicia, espera disponibilidad, ejecuta clientes, compara, guarda logs y detiene          |
| Despliegue en varios hosts y combinaciones de réplicas   | Un host local con Compose, un broker y una instancia por rol, con una partición por etapa particionada |
| Catálogo general, cachés y descarga reproducible         | Archivos pequeños versionados en el repositorio, listos para consumir                                  |
| Varios manifiestos y registro histórico de corridas      | Un archivo de escenario con entradas por cliente y referencias; un directorio para la última corrida   |
| Almacenamiento externo de artefactos                     | Entradas, imágenes pequeñas y referencias en Git; resultados y logs locales fuera de Git               |
| Comparador con ordenación externa                        | Comparación en memoria de la salida pequeña, conservando multiplicidades                               |
| Captura general de respuestas de Wikimedia               | Una imagen diminuta y respuestas de metadatos fijas de un servicio local de pruebas                    |
| Matriz de cantidades de workers, permutaciones y tamaños | Dos ejecuciones secuenciales y luego los mismos dos clientes concurrentes                              |
| Inyección de fallos, reentregas, cuotas y rendimiento    | Etapa posterior; ahora fallos explícitos, timeouts y diagnóstico suficiente                            |

Se conservan el cliente oficial, el protocolo real, el middleware real, el
aislamiento por ejecución, los cierres de las cinco consultas y un oráculo serial
independiente. No es necesario desarrollar un framework de plugins, un segundo
cliente de red ni un sistema de monitoreo para esta primera entrega.

La configuración de una instancia por rol es una propuesta de test local, no
una modificación del despliegue del producto ni una promesa sobre cuántos
contenedores exige cada rol. Se deben reutilizar los entrypoints y agrupaciones
que implemente el equipo. Este escenario no valida escalabilidad ni cierres con
varios productores por etapa; eso requiere una variante posterior con réplicas.

## Escenario `tiny`: pequeño y de punta a punta

### Recorrido y datos

El recorrido debe ser `Client → Gateway → RabbitMQ/middleware → workers →
ResultCollector → RabbitMQ/middleware → Gateway → Client`, incluyendo los
intercambios internos del DAG. El test no publica directamente resultados en
RabbitMQ ni reemplaza el middleware por una cola en memoria.

Preparar dos entradas pequeñas, A y B, cada una con artículos en inglés y francés
y con fechas a ambos lados de 2020/2021. Conservar las 19 columnas y los esquemas
Parquet reales por idioma, usando valores válidos en campos necesarios y nulos
permitidos en los restantes. Guardar archivos separados por cliente e idioma
evita forzar un esquema anidado único. El cliente envía filas completas; la
proyección sigue siendo responsabilidad de `Project`.

Las entradas serán sintéticas, declaradas como tales, para asegurar cobertura
con pocas filas. No modificar los Parquet originales ni elegir únicamente sus
primeras filas esperando encontrar todos los casos. El escenario puede prepararse
y versionarse una vez: ejecutarlo no necesita leer ni descargar los 467 MB.

Los registros cortos deben cubrir:

- Q1: un resultado positivo y exclusiones por idioma y fecha.
- Q2: biografía hasta 2020 con imagen, biografía sin imagen y una sección que no
  coincide. Verificar nombre, URL del artículo y bytes o ausencia explícita.
- Q3: una palabra compartida entre idiomas dentro del mismo cliente; otra presente
  sólo en inglés de A y sólo en francés de B, que no debe cruzar clientes.
- Q4: palabras repetidas dentro de un abstract, stopwords y más de 20 palabras
  válidas en total para verificar el recorte y el desempate lexicográfico.
- Q5: base histórica computable, un candidato por encima del promedio y otro
  igual o por debajo; palabras repetidas que distingan ocurrencias de palabras
  únicas. Calcular el promedio de A y B por separado.
- Al menos un registro de entrada repetido intencionalmente: debe conservar su
  aporte, aunque Q4 cuente cada palabra una sola vez dentro de cada abstract.

No hace falta introducir todos los casos límite en esta primera entrada. Casos
como cliente vacío, ausencia de base histórica y fallos de descarga pueden ser
fixtures adicionales pequeñas, reutilizando el mismo runner.

### Imágenes y referencias

Para que `tiny` sea repetible sin Internet, proponer un pequeño servidor local
que devuelva una respuesta de metadatos fija y una imagen fija, por ejemplo un
PNG de pocos píxeles. Se sustituye sólo el servicio externo: `ImageFetcher` y el
transporte de sus bytes por el sistema permanecen reales. No hace falta un proxy
de grabación, una caché persistente ni un catálogo de imágenes.

Esto requiere acordar con la implementación un endpoint de descarga configurable
para pruebas, incluyendo la resolución de metadatos y el contenido. El protocolo
de ese endpoint debe ser compatible con el fetcher; no se presupone que acepte
HTTP local ni se desactiva globalmente la verificación TLS. Si aún no existe ese
punto configurable, la prueba con imágenes reales depende de la red y debe
identificarse como tal. Un test de Q2 sólo con imágenes ausentes no cubre el envío
de bytes y no debe presentarse como el escenario `tiny` completo.

Preparar manualmente las referencias con el notebook serial adaptado, ejecutando
A y B por separado, y revisarlas también a mano por su pequeño tamaño. Versionar
las salidas completas Q1–Q5, las stopwords utilizadas y la imagen. El runner sólo
compara: nunca regenera expectativas a partir de la implementación bajo prueba.
Python/PyArrow y el notebook se necesitan para preparar fixtures y referencias;
la ejecución cotidiana utiliza los archivos ya preparados.

### Ejecución y criterio de éxito

1. Verificar que existan las entradas y referencias del escenario. Rechazar una
   configuración incompatible con su versión semántica y stopwords.
2. Crear un entorno de pruebas limpio y esperar disponibilidad de RabbitMQ y del
   sistema, con timeout. Un puerto abierto o un `sleep` fijo no basta para probar
   que todos los participantes estén listos.
3. Ejecutar A y después B contra esa misma instancia, con IDs nuevos. Comparar
   cada salida con su referencia y abortar la prueba ante una diferencia.
4. Guardar resultados fuera del estado temporal del sistema, cerrar esa instancia
   y crear otra limpia con la misma configuración.
5. Ejecutar A y B concurrentemente, coordinando su inicio. Registrar evidencia
   de solapamiento de sesiones: con entradas tan cortas, iniciar dos procesos no
   garantiza por sí solo haber ejercitado concurrencia. Si no se solapan, no
   declarar validada esa propiedad.
6. Comparar cada salida concurrente con su referencia y con su salida secuencial.
   Exigir los cinco cierres exitosos y la finalización completa de cada ejecución.
7. Conservar un resumen, resultados y logs de la corrida; cerrar los recursos
   propios del test, también cuando falla. Devolver un código de salida no cero
   ante diferencias, error de proceso, cierre faltante o timeout.

No comprobar únicamente que el comando termine o que las colas estén vacías.
Comparar según los [formatos de salida](expected/README.md#formatos-de-salida),
reconstruyendo los fragmentos de imagen antes de comparar sus bytes. Se ignoran
IDs e instantes propios de la ejecución, no registros repetidos ni estados de fallo.

Un nombre fijo y exclusivo de proyecto Compose es suficiente si el runner admite
una sola corrida a la vez y rechaza otra activa. El broker (RabbitMQ) y los archivos temporales deben
pertenecer exclusivamente a ese proyecto; limpiar sólo esos recursos. No purgar
un RabbitMQ compartido ni ejecutar limpiezas globales de Docker. No hacen falta
namespaces dinámicos complejos para paralelizar suites en esta etapa.

## Tres tamaños sobre la misma infraestructura

| Escenario                     | Entrada                                                                      | Uso                                                            |
| ----------------------------- | ---------------------------------------------------------------------------- | -------------------------------------------------------------- |
| `tiny` — predeterminado       | 20–40 registros sintéticos en total, dos clientes y una imagen pequeña       | Corrección funcional e integración diaria, middleware incluido |
| `sample` — opcional posterior | Primeras 1.000 filas de cada archivo local: 10.000 registros, cinco clientes | Compatibilidad con datos reales y diversidad del esquema       |
| `full` — opcional posterior   | Diez Parquet locales completos: 250.000 registros, cinco clientes            | Validación con volumen: 467.363.817 bytes comprimidos          |

`sample` y `full` reutilizan arranque, cliente, captura y comparación. Incorporar
comparación incremental (leer y comparar los resultados por partes) o externa (usar archivos temporales en disco para organizar la comparación) cuando el volumen de resultados lo requiera;
no implementarla como prerrequisito de `tiny`. La integración contra Wikimedia
real y las mediciones de recursos se ejecutan aparte y de forma explícita, en lugar de ejecutarse automáticamente en cada corrida habitual.

Los tres escenarios usan el [reparto determinista del oráculo](oracle/README.md#partición-exacta-de-la-entrada),
registrado en su manifiesto. En `tiny`, organizar los registros sintéticos para
garantizar la cobertura requerida por cliente. Para cambiar un escenario,
seguir las [reglas de actualización de referencias](oracle/README.md#actualizar-referencias).

## Orden de entrega y dependencias

1. Preparar los fixtures `tiny`, stopwords y referencias seriales, y un comparador
   pequeño. Verificarlo con una salida correcta y alteraciones deliberadas.
2. Conectar cuanto antes el cliente oficial y el despliegue real mediante un
   Compose de test y un script. No esperar al catálogo del dataset ni a `full`.
3. Completar Q2 con el endpoint local acordado y comprobar el recorrido de bytes.
4. Agregar después `sample`, `full`, orden de entrada invertido y dos o más
   workers/particiones para ejercitar ruteo, agregaciones y cierres distribuidos.
5. Por último, agregar casos de fallos, SIGTERM durante procesamiento, clientes
   lentos, cuotas y mediciones. Mantener el mismo principio de aborto y corrida
   nueva; no implementar recuperación automática en el runner.

Las únicas interfaces del sistema necesarias para la primera integración son:
comandos de arranque/configuración, disponibilidad, endpoint de Gateway, entrada
del cliente, captura de resultados y cierres, códigos de error y apagado ordenado.
Para la concurrencia pequeña se necesita coordinar el inicio de las sesiones, y
para Q2 reproducible, el endpoint externo configurable. El adaptador debe invocar
el cliente oficial; no importar lógica de consultas en el oráculo.

Si sólo está implementado el middleware, puede ejecutarse una prueba de
integración productor–RabbitMQ–consumidor para validar esa parte. Debe reportarse
con ese alcance; el éxito de `tiny` exige el recorrido real completo y Q1–Q5.

## Documentación relacionada

- [Requisitos funcionales](../docs/requisitos.md#requerimientos-funcionales).
- [Esquema e inventario de la muestra](../dataset/README.md#esquema-real).
- [Contrato del oráculo serial](oracle/README.md#contrato-serial).
- [Mapa de arquitectura y documentación](../docs/README.md).
