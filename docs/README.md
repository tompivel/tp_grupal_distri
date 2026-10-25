# Mapa de documentación

| Tema | Documento |
|---|---|
| Requisitos funcionales y no funcionales | [Requisitos del sistema](requisitos.md) |
| Propuesta de arquitectura vigente | [Informe](../Informe.pdf); fuentes en [tex/](tex/), entrada [main.tex](main.tex) y plantilla [estilo.cls](estilo.cls) |
| Particionado, aislamiento y estado | [Vista de procesos](tex/vista_procesos.tex) |
| Distribución física y despliegue | [Vista física](tex/vista_fisica.tex) |
| Sistema de archivos por nodo | [Explicación](./docs/build.md) |
| Muestra local, esquema verificado y cobertura | [Dataset](../dataset/README.md) |
| Descarga, verificación y publicación del dataset | [Guía de distribución](../scripts/README.md) |
| Estrategia de pruebas y trabajo pendiente | [Infraestructura de pruebas](../tests/README.md) |
| Cálculo serial, contrato y generación de referencias | [Guía del oráculo](../tests/oracle/README.md) |
| Organización y formatos de resultados esperados | [Guía de artefactos](../tests/expected/README.md) |
| Estado de las referencias de la muestra completa | [Escenario de cinco clientes](../tests/expected/full-5clients-v1/README.md) |

## Discrepancias pendientes de correción

- **Q5:** los [requisitos](requisitos.md#requerimientos-funcionales) exigen contar
  repeticiones. El informe todavía contiene textos que deduplican palabras por
  abstract, pendientes de corrección; no deben usarse para definir ese conteo.
- **DAG:** el rótulo `QUERY 5` después de `TopKReducer` es una errata confirmada:
  corresponde a Q4. Los nombres de roles se conservan.
