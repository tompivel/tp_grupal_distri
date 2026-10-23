# Requisitos del sistema
Diseñar sistema distribuido escalable capaz de procesar las siguientes solicitudes concurrentemente:
	
## Requerimientos funcionales

- Se solicita un sistema distribuido que analice un conjunto de artículos obtenidos de Wikipedia en los idiomas Francés e Inglés.
- Se debe obtener:
    1. Url y fecha de modificación para artículos escritos en inglés hasta 2020 inclusive.
    2. Nombre, url e imágen (bytes) de artículos escritos hasta 2020 inclusive que incluyan "biography" o "biographie" entre sus secciones.
    3. Listado de palabras únicas compartidas entre cualquier artículo escrito en inglés y cualquier artículo escrito en francés. Se excluyen stopwords.
    4. Pares (palabra, cantidad) del top 20 palabras más utilizadas entre todos los abstracts. Dentro de un mismo abstract las palabras se cuentan una sola vez y las palabras triviales (stopwords) se excluyen del top.
    5. Url y cantidad de palabras de abstract para los artículos escritos a partir del 2021 cuya cantidad de palabras en el abstract sea superior al promedio de palabras de abstract de todos los artículos escritos hasta el 2020 inclusive. Se excluyen stopwords, se cuentan palabras repetidas en un mismo abstract.

> Nota: 1,2 y 3 pueden ser enviados parcialmente. 4 y 5 requieren haber procesado todo el input del cliente.

	

## Requerimientos No Funcionales
- código desarrollado en Go.
- atender múltiples clientes concurrentemente, no necesariamente paralelamente (implicaría trackear información del cliente para no mezclar/contaminar). Se puede comparar contra al ejecución serial de varios clientes para comparar y validar esta propiedad. 
- respuesta determinística: si dos clientes te dan los mismos datos, la respuesta del sistema es la misma para ambos clientes.
- El cliente es bastante simple. Enviará linea por linea (en formato parquet) de artículos. Es el sistema el encargado de limpiar/depurar las columnas que no le sirvan, ingestar los datos en entidades internas, etc.

- Las respuestas pueden ser brindadas en lotes o en resultados "finales". Es decir:
	 - Para una solicitud concreta, se pueden ir devolviendo resultados parciales al cliente. Implicaría igualmente mantener estado del progreso de la solicitud tanto en el cliente como el sistema. Más mensajes enviados a través de la red pero habilita al cliente para usar los datos parciales entregados a medida que llegan.
	 -  Para una solicitud concreta, se puede devolver únicamente el resultado final al cliente. La lista completa. Serviría implícitamente como señal de EOF o procesamiento para esa solicitud en particular. El problema de este approach podría ser la incapacidad de escalar un gran volumen de datos si el sistema no crece a la par (e.g. 1 cliente, 1TB, y 3 nodos con 4GB de RAM cada uno)
	 
- Se requiere poder atender consultas aisladas de múltiples clientes. No es necesario permitir más de una única ejecución por cliente. Es decir, no es necesario resetear estado para un cliente específico después de finalizar su solicitud. Se puede asumir que el cliente no volverá a comunicarse. 
- El sistema debe estar optimizado para entornos multicomputadoras. Se debe soportar el incremento de los elementos de cómputo para escalar respecto a la cantidad de clientes atendidos y al volúmen de información a procesar por cliente. El sistema debe ser escalable. No es necesario que sea elástico.
- Se requiere del desarrollo de un Middleware (RabbitMQ) para abstraer la comunicación basada en grupos usando colas o exchanges.
- Se debe garantizar graceful quit frente a señales SIGTERM.
- No se puede usar una base de datos. Se pueden usar archivos escritos por el mismo sistema de forma temporal o un nodo que cumpla un rol de base de datos, pero en principio se debe intentar mantener el comportamiento cerca de los datos.
- El notebook utilizado debe ser serial y adaptado a las stopwords que el sistema termina usando.
## Pruebas Automáticas
Para garantizar procesamiento concurrente determinístico y correcto, se podría generar un entorno de pruebas con los datos de kaggle.

Adicionalmente, se podría incluir una prueba que valide determinismo contra el orden en que un cliente va ofreciendo cada línea. El resultado debería ser el mismo que el resultado esperado generado con el notebook de kaggle.
	
## Datasets, notebook patrón y librerías

- Se trabajará sobre los datos de un dataset de Kaggle.
- Para la descarga de las imágenes se recomienda el uso de la API de Wikimedia.
- Se provee un notebook de referencia para guiar la interpretación del enunciado. No obstante, debido a la naturaleza abierta del problema se espera que los requerimientos se perfeccionen con el docente asignado a lo largo del tiempo.
