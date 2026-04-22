# Exact Boundary Graph v1 Design

## Goal
Convertir el modelo actual de `SEMINOLE2000` desde walls “trace-supported pero bbox-inferred” a un **boundary graph exacto y operable**, preparado para el primer site-aware mutator y para el futuro executor geométrico.

## Why This Matters Now
Hoy el catálogo ya llegó a un punto fuerte para inspección:

- `topology_issues = []`
- `wall_graph_issues = []`
- `heuristic_adjacent_room_ids = []`
- openings separadas de walls
- wall ownership y opening ownership parciales

Pero el límite real sigue siendo este:

- las `shared walls` todavía tienen `provenance = bbox_inferred`
- la mayoría de las openings siguen `unhosted`
- `backend/site_fit/solver.py` todavía devuelve solo baseline

Eso significa que el sistema **entiende** bastante bien el plano, pero todavía no puede **operarlo** con precisión suficiente para “adaptar solo lo necesario”.

## Scope
Este slice construye la base geométrica que falta antes del executor:

1. derivación de **boundary graph exacto**
2. separación explícita entre **CAD trace cruda** y **boundary estructural canónica**
3. anclaje fuerte de rooms sobre boundaries exactas
4. integración visual en el inspector actual para comparar:
   - raw traces
   - exact boundaries
   - ownership
   - openings hosteadas / no hosteadas

## Non-Goals
Este slice NO implementa todavía:

- mutadores finales de site fit
- DXF recompilation final
- optimización multi-estrategia
- rehosting masivo perfecto de todas las openings
- surgery completa de wet core

## Problem Statement
La implementación actual de `wall_graph.py` deriva shared walls principalmente desde:

1. overlap exacto de segmentos de room, cuando existe
2. fallback por bbox
3. soporte posterior contra raw traces del CAD

Ese approach fue útil para llegar hasta acá, pero tiene un problema estructural:

> la pared canónica aparece como una inferencia entre rooms, no como una entidad primaria del plano.

Para reconstrucción geométrica futura necesitamos lo contrario:

> la pared canónica debe existir primero como boundary exacta del graph, y las rooms deben explicarse a partir de ese graph.

## Recommended Approach
Se evaluaron tres caminos:

### A. Seguir refinando bbox + snap heuristics
**Pros:** rápido, incremental.  
**Contras:** no cruza el puente al executor; mantiene paredes derivadas desde una abstracción débil.

### B. Construir Exact Boundary Graph v1 (**recomendado**)
**Pros:** transforma la pared en entidad estructural primaria; habilita mutability, ownership fuerte y openings hosteadas con mejor soporte.  
**Contras:** requiere más trabajo geométrico y más tests.

### C. Saltar directo a site-aware mutators
**Pros:** más cerca del objetivo final.  
**Contras:** sería una locura cósmica sobre una base todavía parcialmente inferida.

Se elige **B**.

## Design Summary
El subproyecto se divide en cuatro entregables:

1. **Raw Trace Normalization**
   - normalizar traces wall/door/window en segmentos comparables
   - detectar intersecciones y cortes relevantes

2. **Exact Boundary Graph Derivation**
   - generar boundaries canónicas a partir de traces reales
   - introducir nodos, segmentos y relación con openings

3. **Room Reprojection**
   - re-explicar rooms sobre el boundary graph
   - reemplazar gradualmente la dependencia de bbox-inferred shared walls

4. **Inspector Upgrade**
   - visualizar boundary graph exacto
   - marcar delta entre graph anterior y exact graph nuevo
   - medir calidad geométrica antes de pasar al mutator

## Architecture

### Current Inputs
El catálogo ya dispone de:

- `FloorPlanCatalogSeed`
- `cad_traces` clasificadas en `wall`, `door`, `window`
- `FloorPlanTopologyV1`
- `FloorPlanWallGraphV1`
- `FloorPlanOpeningGraphV1`

### New Model: `FloorPlanBoundaryGraphV1`
Se agregará una nueva capa entre `cad_traces` y `wall_graph`.

#### Global fields
- `floor_plan_id`
- `name`
- `canonical_unit`
- `nodes[]`
- `boundaries[]`
- `boundary_graph_readiness`
- `boundary_graph_issues[]`

#### Nodes
Cada nodo representa una intersección o quiebre estructural.

Campos mínimos:
- `node_id`
- `point`
- `node_kind` (`corner`, `tee`, `cross`, `opening_cut`, `dangling`)
- `incident_boundary_ids[]`

#### Boundaries
Cada boundary representa una pared canónica o un tramo canónico utilizable por el executor.

Campos mínimos:
- `boundary_id`
- `start_node_id`
- `end_node_id`
- `start`
- `end`
- `orientation`
- `length`
- `source_trace_ids[]`
- `boundary_kind` (`shared`, `exterior`, `unknown`)
- `owner_room_ids[]`
- `opening_ids[]`
- `confidence`
- `issues[]`

## Raw Trace Normalization Rules

### 1. Segment extraction
Toda traza wall/door/window debe convertirse a segmentos lineales comparables:

- `LINE` -> un segmento
- `LWPOLYLINE` / `POLYLINE` -> múltiples segmentos
- se ignoran segmentos degenerados

### 2. Canonical wall traces
Se agrupan segmentos colineales y cercanos que representan la misma pared real, incluso si vienen:

- partidos por openings
- duplicados
- dibujados en varios tramos

La salida de esta fase NO es todavía ownership, sino una red de soporte geométrico estable.

### 3. Intersections and cuts
Se detectan:

- esquinas reales
- tees
- cruces
- cortes donde una opening interrumpe un tramo

Esos puntos pasan a ser nodos del graph.

## Boundary Graph Derivation

### 1. Boundaries first, rooms second
El boundary graph exacto debe derivarse primero desde las traces y recién después alimentar rooms/walls/openings.

### 2. Shared vs exterior
Una boundary se marca como:

- `shared` si separa dos rooms
- `exterior` si limita una room contra exterior / footprint
- `unknown` si todavía no puede clasificarse con confianza

### 3. Confidence policy
Se evitan nombres vagos. La confianza debe expresar la fuente real:

- `trace_exact`
- `trace_merged`
- `trace_partitioned`
- `trace_projected`
- `unsupported`

Esto reemplaza gradualmente el binomio actual `bbox_inferred + snapped_to_trace`.

## Room Reprojection

### Problem
Hoy las rooms ayudan a explicar paredes.  
El objetivo nuevo es que las paredes exactas expliquen las rooms.

### V1 Strategy
Sin rehacer todavía toda la segmentación del extractor, se proyectan los polígonos actuales de room al boundary graph exacto:

- snapping de edges a boundaries canónicas
- corrección de shared edges
- actualización de ownership por boundary

### Expected output
Las shared walls deberían dejar de vivir como `bbox_inferred`.

## Openings

### Goal for this slice
No hace falta hostear perfectamente las 167 openings todavía, pero sí:

- permitir que una boundary conozca qué openings la cortan o la usan
- preparar `host_wall_id` sobre boundaries exactas, no sobre walls aproximadas

### Constraint
Las openings no deben contaminar soporte estructural de walls.

## UX Impact
Esto sigue siendo interno/técnico por ahora y se valida en el inspector actual:

- nueva capa `Exact boundaries`
- toggle para comparar:
  - raw traces
  - wall graph actual
  - exact boundary graph
- highlight de boundary seleccionada
- highlight de nodos incidentes
- panel con:
  - source traces
  - owner rooms
  - opening cuts
  - confidence

La UX final de usuario no cambia todavía; esto fortalece la base interna del producto chat-first.

## Success Criteria
Este slice se considera exitoso si logra:

1. que las shared walls dejen de depender estructuralmente de `bbox_inferred`
2. que exista un boundary graph navegable por nodos y segmentos
3. que rooms puedan reproyectarse sobre ese graph sin reintroducir heurística floja
4. que el inspector muestre el delta entre wall graph anterior y exact boundary graph nuevo
5. que la base quede lista para el siguiente slice:
   - `Mutability / Constraints`
   - `Site-aware Mutation Contract`

## Testing Strategy
Strict TDD:

1. tests sintéticos de grafo:
   - esquina
   - tee
   - opening cut
   - merge de segmentos colineales

2. tests de integración sobre `SEMINOLE2000`:
   - boundary count razonable
   - boundaries shared con provenance exacta/merged, no bbox-inferred
   - reproyección de rooms sin pérdida de ownership

3. tests frontend del inspector:
   - nuevo toggle de exact boundaries
   - selección de boundary/nodo
   - render de métricas nuevas

## Risks

### 1. DXF ambiguity
El CAD puede traer dobles líneas, gaps chicos o fragmentación rara.

**Mitigación:** mantener raw traces visibles y confidence explícita.

### 2. Overfitting to Seminole
Se puede resolver solo para un plano.

**Mitigación:** tests sintéticos + reglas geométricas generales.

### 3. Scope creep to full executor
Es tentador meter mutators ya.

**Mitigación:** este slice termina en boundary graph exacto + reproyección + visualización.

## Next Step After This Slice
Si Exact Boundary Graph v1 queda fuerte, el siguiente slice recomendado es:

1. `Mutability / Constraints v1`
2. `Site-aware Mutation Contract v1`
3. `Geometry Executor v1`

Ese recién será el puente real hacia “adaptar solo lo necesario”.
