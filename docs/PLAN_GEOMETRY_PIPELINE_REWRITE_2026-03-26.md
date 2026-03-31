# Plan Tecnico: Geometry Pipeline Rewrite

Fecha: 2026-03-26

## Objetivo

Reescribir la pipeline geométrica alrededor de `backend/structure_postprocess.py` para que la IA proponga estructura y el postproceso la convierta en un `wall_graph` consistente antes de anclar openings o renderizar DXF.

La prioridad no es reentrenar. El cuello de botella actual está en:

- vectorización y snapping
- topología de muros y junctions
- anclaje de puertas/ventanas
- render DXF desde geometría inconsistente

## Estado Actual del Repo

Observaciones sobre el código actual:

- `backend/structure_postprocess.py` concentra normalización, snapping, merge, junctions, clasificación, filtros y anchoring en un solo archivo.
- `backend/structure_postprocess.py` usa thresholds globales mutables. Eso es deuda técnica y además es mala base para concurrencia en FastAPI.
- `backend/plan_parser.py` espera un resultado monolítico de `postprocess_structure()` y sólo preserva `walls`, `openings`, `junctions`, `metrics` y `review_flags`.
- `backend/structural_generator.py` renderiza desde centerlines con extensiones heurísticas de endpoints en `_apply_junction_extensions()`.
- `backend/components/walls.py` dibuja paredes como doble línea simple con gaps, sin resolver trims, miters ni caras consistentes en uniones complejas.
- `backend/quality_gate.py` todavía valida con heurística de bbox shell. Es útil como smoke check, pero es demasiado simple para aceptar o rechazar estructura.
- `backend/benchmark.py` hoy mide IoU de wall footprint y matching básico de openings. No mide shell exterior, junction precision/recall ni opening anchor precision.
- `backend/artifacts.py` guarda `structure.json`, `quality.json` y previews, pero no persiste estados intermedios de la pipeline.
- No existe hoy un `data/benchmark/` estable dentro del repo con casos reales listos para correr.

## Contrato Interno Objetivo

Mantener el contrato público actual hacia API y tests, pero introducir un contrato geométrico interno explícito:

```json
{
  "raw_segments": [],
  "snapped_segments": [],
  "merged_segments": [],
  "junctions": [],
  "wall_graph": {
    "nodes": [],
    "edges": [],
    "components": [],
    "shell_edge_ids": []
  },
  "anchored_openings": [],
  "render_structure": {
    "wall_faces": [],
    "opening_cuts": [],
    "joins": []
  }
}
```

Regla de migración:

- `postprocess_structure()` se mantiene como fachada estable.
- Hacia afuera seguimos devolviendo `walls`, `openings`, `junctions`, `structure_meta`, `metrics` y `review_flags`.
- Internamente agregamos `pipeline_debug` y `wall_graph` de forma compatible.

## Fase 1: Medicion Real + Refactor Deterministico

### Objetivo

Dejar de iterar a ojo y convertir la pipeline actual en etapas auditables, sin cambiar todavía la semántica principal del renderer.

### Entregables

- dataset `data/benchmark/` con 10 a 20 planos reales
- benchmark con métricas estructurales reales
- `postprocess_structure()` convertido en orquestador de etapas puras
- persistencia de artefactos intermedios por corrida

### Tareas por archivo

`data/benchmark/<case>/input.png`

- crear el input por caso

`data/benchmark/<case>/expected.json`

- definir ground truth canónico de `walls`, `openings`, `junctions` y, cuando aplique, `wall_graph`

`data/benchmark/<case>/notes.md`

- documentar supuestos del caso y por qué debe pasar o quedar en review

`backend/benchmark.py`

- extender `BenchmarkResult.comparison` con:
  - `exterior_shell_recall`
  - `junction_precision`
  - `junction_recall`
  - `opening_anchor_precision`
  - `review_rate` o señal equivalente por caso
- guardar también `pipeline_debug.json` en output
- separar comparación geométrica de comparación de openings en helpers dedicados
- agregar thresholds por métrica estructural, no sólo conteos

`backend/artifacts.py`

- guardar `pipeline_debug.json`
- opcional: generar previews por etapa (`snapped_preview.png`, `graph_preview.png`)

`backend/plan_parser.py`

- preservar `pipeline_debug` dentro del parse result
- agregar versión explícita de parser/postprocess, por ejemplo `parser_version = v2-phase-graph-prep`

`backend/structure_postprocess.py`

- dejar de mutar globals
- introducir un `config` inmutable por corrida
- convertir el archivo actual en orquestador y wrapper de compatibilidad
- mover etapas puras a un subpaquete nuevo

`backend/geometry_pipeline/__init__.py`

- exponer `run_geometry_pipeline()`

`backend/geometry_pipeline/config.py`

- definir `GeometryConfig`
- resolver thresholds por unidad (`pixel` o `inch`) sin estado global

`backend/geometry_pipeline/contracts.py`

- definir tipos internos:
  - `Segment`
  - `JunctionNode`
  - `WallGraphNode`
  - `WallGraphEdge`
  - `AnchoredOpening`
  - `RenderStructure`

`backend/geometry_pipeline/stages/normalize.py`

- normalización y proyección de diagonales casi H/V

`backend/geometry_pipeline/stages/snap.py`

- snapping por clusters y snapping a intersecciones

`backend/geometry_pipeline/stages/merge.py`

- merge colineal y limpieza de spans

`backend/geometry_pipeline/stages/filtering.py`

- filtros de texto, ruido aislado, furniture y openings duplicados

`backend/geometry_pipeline/stages/junctions.py`

- detección de junctions desacoplada del resto

`tests/test_benchmark.py`

- agregar fixtures con métricas nuevas
- cubrir fallo por shell incompleto, junction recall bajo y anchor precision bajo

`tests/test_plan_parser.py`

- validar que `pipeline_debug` no rompe el contrato existente

`tests/test_junction_graph.py`

- conservar tests actuales y agregar casos de fragmentación con pequeños huecos

### Criterio de salida

- `data/benchmark/` ya existe y corre en local
- `postprocess_structure()` ya no depende de globals mutables
- cada corrida puede inspeccionarse por etapa
- no se rompe la API `/api/v2/parse-structure` ni `/api/v2/generate-dxf`

## Fase 2: Wall Graph + Opening Anchoring v2

### Objetivo

Dejar de tratar la estructura como lista de paredes y pasar a un grafo topológico robusto que sea el contrato interno serio.

### Entregables

- `wall_graph` completo con nodos, aristas, componentes y shell exterior
- reclustering de junctions por proximidad y espesor
- reconexión de fragmentos colineales con huecos pequeños
- anchoring de openings sobre edges del grafo

### Tareas por archivo

`backend/geometry_pipeline/stages/junctions.py`

- clusterizar junctions por proximidad y espesor
- distinguir `L`, `T`, `X` con reglas estables
- registrar soporte geométrico por junction y por edge

`backend/geometry_pipeline/stages/graph.py`

- construir `wall_graph`:
  - nodos = junction clusters
  - aristas = muros o spans estructurales entre nodos
- detectar componentes conectados
- reconectar fragmentos colineales con pequeños gaps si mantienen consistencia geométrica
- marcar edges soportados vs edges huérfanos

`backend/geometry_pipeline/stages/classify.py`

- detectar shell exterior por conectividad y continuidad
- dejar de depender principalmente del bbox coverage
- mantener interiores cortos si el grafo los soporta

`backend/geometry_pipeline/stages/openings.py`

- reemplazar `nearest wall` por `candidate graph edge`
- para cada opening:
  - proyectar sobre edge candidata
  - validar que entra en el span útil
  - validar coherencia con espesor, orientación y lado
  - si falla, marcar review en vez de inventar anclaje
- devolver score y motivo de anclaje o rechazo

`backend/structure_postprocess.py`

- publicar `wall_graph` y `anchored_openings` en `pipeline_debug`
- derivar `walls` públicos desde `wall_graph.edges`, no desde listas intermedias ad hoc

`backend/plan_parser.py`

- incorporar métricas nuevas:
  - `wall_graph_node_count`
  - `wall_graph_edge_count`
  - `connected_component_count`
  - `shell_edge_count`
  - `opening_review_count`

`backend/benchmark.py`

- comparar junctions predicted vs expected
- comparar openings anclados por edge, no sólo por cercanía de centro

`tests/test_junction_graph.py`

- casos con:
  - gap pequeño entre fragmentos colineales
  - shell exterior fragmentado
  - interior corto válido por soporte topológico

`tests/test_opening_anchoring_v2.py`

- nuevo archivo
- cubrir:
  - opening bien detectado en edge correcta
  - opening ambigua entre dos paredes cercanas
  - opening fuera de span útil
  - opening que debe ir a review

`tests/helpers.py`

- agregar fixtures con `wall_graph` esperado y casos ambiguos de anchoring

### Criterio de salida

- el contrato interno principal pasa a ser `wall_graph`
- desaparecen la mayoría de los anclajes inventados por “pared más cercana”
- el shell exterior se detecta por conectividad real
- el benchmark mejora en shell recall y opening anchor precision

## Fase 3: DXF Renderer v2 + Quality Gate + Cleanup de Runtime

### Objetivo

Renderizar DXF desde geometría consistente y cerrar la pipeline con una compuerta de calidad seria y un backend runtime más explícito.

### Entregables

- renderer DXF desde caras de muro y trims consistentes
- quality gate con `accept / review / reject`
- fallback explícito por backend
- cleanup de caminos runtime viejos que hoy meten ruido

### Tareas por archivo

`backend/geometry_pipeline/stages/render_model.py`

- derivar `render_structure` desde `wall_graph`
- generar:
  - caras interior/exterior por wall edge
  - opening cuts
  - joins L/T/X
  - caps y miters antes de dibujar

`backend/structural_generator.py`

- dejar de depender de `_apply_junction_extensions()` como mecanismo principal
- consumir `render_structure`
- mantener fallback temporal a centerlines sólo mientras dure la migración

`backend/components/walls.py`

- agregar primitivas para dibujar desde caras ya resueltas, no sólo `draw_wall_h()` y `draw_wall_v()`
- soportar trims/miter/caps determinados aguas arriba

`backend/quality_gate.py`

- reemplazar gate minimal por score estructural compuesto
- checks nuevos:
  - componentes conectados
  - shell exterior cerrado
  - openings fuera de muro
  - muros muertos sin soporte
  - densidad anómala de junctions
- salida:
  - `quality_status = accept | review | reject`
  - `quality_score`
  - `quality_gate_reasons`

`backend/plan_parser.py`

- mapear `quality_status` a `needs_review`
- preservar razones estructurales y no sólo flags genéricos

`backend/app.py`

- exponer mejor `quality_status` y backend efectivo en respuestas
- si se agrega fallback por renderer o backend, dejarlo explícito en `quality_metrics`

`backend/worker_client.py`

- dejar explícito qué backend manda:
  - `mitunet_local`
  - `r2v_local`
  - `heuristic_local`
  - fallback definido y observable
- si CubiCasa ya no es parte del runtime deseado, sacarlo del flujo principal sin borrar tooling de training

`backend/worker_server.py`

- alinear selección de backend con el cleanup anterior

`backend/cubicasa_inference.py`

- sólo si se decide removerlo del runtime:
  - conservarlo como backend opcional o experimental
  - evitar que el startup y los defaults dependan de él

`tests/test_structural_generator.py`

- cubrir joins L/T/X desde geometría consistente
- cubrir trims y openings en esquinas

`tests/test_quality_gate.py`

- validar `accept / review / reject`
- validar razones específicas por shell roto, opening fuera de muro y muros huérfanos

`tests/test_v2_api.py`

- afirmar que la API devuelve `quality_status`, motivos y fallback efectivo

`tests/test_worker_client.py`

- validar backend explícito y fallback observable

### Criterio de salida

- el DXF sale de geometría consistente, no de parches heurísticos
- quality gate discrimina bien entre aceptar, revisar o rechazar
- backend activo y fallback quedan claros en runtime y en tests

## Orden de Ejecucion Recomendado

1. Fase 1 completa
2. Fase 2 completa
3. Fase 3 completa

No mezclar DXF v2 con wall graph incompleto. El renderer debe ser consumidor de un contrato estable, no parte de la exploración topológica.

## Riesgos y Contencion

Riesgos principales:

- romper el contrato actual de `parse_structure_payload()`
- mejorar el grafo pero degradar el renderer durante la transición
- introducir sobreingeniería antes de tener benchmark real

Mitigación:

- mantener `postprocess_structure()` como fachada estable
- agregar `render_structure` en paralelo antes de retirar el flujo viejo
- no eliminar backends viejos del runtime hasta que existan métricas de benchmark y tests equivalentes

## Decision de Implementacion

La decisión correcta es una rewrite controlada de la geometry pipeline, no reentrenado inmediato.

El orden de mayor retorno en este repo es:

1. benchmark real
2. refactor determinístico del postproceso
3. wall graph
4. opening anchoring v2
5. renderer DXF v2
6. quality gate serio
7. cleanup de runtime
