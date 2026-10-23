# Resultados esperados

Cada escenario conserva su manifiesto y las salidas Q1–Q5 por cliente. Los bytes
de imágenes se comparten en `images/<sha256>.bin`, dentro de este mismo repositorio.
Los descriptores de Q2 apuntan a `../images/<sha256>.bin`, relativo a la carpeta
del escenario, y fijan el hash y el tamaño de los bytes esperados.

`images/index.json` permite encontrar una captura exitosa por URL. Se usa al
completar referencias pendientes; las expectativas ya disponibles siguen fijadas
por cada escenario. Los errores HTTP 404 se conservan en el escenario que los
observó y no se incorporan al índice común.

Los comandos habituales no cambian:

```sh
uv run --project tests/oracle --locked python tests/oracle/reference.py capture-images tests/expected/full-5clients-v1
uv run --project tests/oracle --locked python tests/oracle/reference.py verify tests/expected/full-5clients-v1 --dataset dataset --allow-incomplete-q2
```

Ejecutar una sola captura a la vez. Versionar en git juntos los escenarios, el índice y
los binarios compartidos; no borrar imágenes referenciadas por otros escenarios.
Para trasladarlos a otra máquina, conservar la disposición de carpetas hermanas.

Ver la [guía del oráculo](../oracle/README.md) para generación, captura y límites.
