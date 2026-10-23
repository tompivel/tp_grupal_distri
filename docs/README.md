# Mapa de documentación

| Tema | Documento |
|---|---|
| Requisitos funcionales y no funcionales | [Requisitos del sistema](requisitos.md) |
| Propuesta de arquitectura vigente | [Informe](../Informe.pdf); fuentes en [tex/](tex/), entrada [main.tex](main.tex) y plantilla [estilo.cls](estilo.cls) |
| Particionado, aislamiento y estado | [Vista de procesos](tex/vista_procesos.tex) |
| Distribución física y despliegue | [Vista física](tex/vista_fisica.tex) |
| Muestra local, esquema verificado y cobertura | [Dataset](../dataset/README.md) |
| Descarga, verificación y publicación del dataset | [Guía de distribución](../scripts/README.md) |
| Estrategia de pruebas y trabajo pendiente | [Infraestructura de pruebas](../tests/README.md) |
| Cálculo serial y generación de referencias | [Oráculo](../tests/oracle/README.md) y [notebook](../wikipedia-article-analysis.ipynb) |
| Resultados esperados y estado de validez | [Organización](../tests/expected/README.md) y [escenario completo 500MB](../tests/expected/full-5clients-v1/README.md) |

## Precedencia de fuentes

- **Funcionalidad:** los [requisitos](requisitos.md) prevalecen sobre el informe,
  el notebook y las propuestas anteriores. Q2 devuelve nombre, URL del artículo
  y bytes de imagen. Q3–Q5 excluyen stopwords; Q4 cuenta cada palabra una vez por
  abstract y Q5 cuenta sus repeticiones. El texto del informe que deduplica
  palabras en Q5 está pendiente de corrección.
- **Diseño:** el informe y sus fuentes LaTeX describen la propuesta vigente.
  Conservar los nombres de roles del DAG. Su rótulo `QUERY 5` después de
  `TopKReducer` es una errata confirmada: corresponde a Q4.
- **Datos y validación:** el [esquema verificado](../dataset/README.md#esquema-real)
  describe la muestra local; los esquemas de inglés y francés difieren dentro
  de `version`. El oráculo documenta cómo producir y verificar referencias;
  haberlo ejecutado no valida por sí solo el sistema distribuido.
