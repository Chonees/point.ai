# Seminole Topology Inspector Design

## Goal
Construir una screen temporal de validación para `SEMINOLE2000` que permita inspeccionar visualmente, pieza por pieza, si el floor plan está bien curado antes de avanzar al executor geométrico.

## Scope
Este diseño NO es producto final. No vive todavía en el flujo final del chat-first product. Es una superficie de laboratorio/removible para validar si la data curada del floor plan es suficientemente fuerte como para soportar reconstrucción geométrica futura.

## Problem Statement
El `FloorPlanCatalogSeed` actual ya permite ver geometría básica por room (`polygon`, `bbox`, `centroid`, medidas), pero no alcanza todavía para reconstrucción precisa. Sin topología básica no se puede pedir con seguridad: “recortá este cuarto”, “mové esta boundary”, “recalculá cotas” o “regenerá el DXF”.

Antes de invertir en el executor geométrico, necesitamos una prueba visual fuerte de que cada pieza del floor plan está:
- identificada correctamente
- relacionada correctamente con las demás
- clasificada de forma útil
- marcada con issues cuando el curado todavía no alcanza

## Design Summary
La solución se divide en dos entregables del mismo subproyecto:

1. **Topology V1 derivation for `SEMINOLE2000`**
   - deriva topología mínima desde el seed curado actual
   - agrega identidad estable por room y relaciones útiles para reconstrucción futura

2. **Temporary Topology Inspector UI**
   - screen visual temporal que renderiza el plano real de `SEMINOLE2000`
   - superpone semántica y relaciones topológicas
   - permite validar visualmente room IDs, categorías, exterior-touch, adjacency e issues

## Why This Slice First
Hay tres caminos posibles:

### A. Hacer solo una UI visual sobre el seed actual
**Pros:** rápido.
**Contras:** valida dibujo, no modelo. No protege el executor futuro.

### B. Derivar Topology V1 y mostrarla en una screen temporal (**recomendado**)
**Pros:** valida el modelo que después alimentará reconstrucción; permite detectar errores de curado antes de mover geometría.
**Contras:** requiere una capa de derivación nueva antes de la UI.

### C. Ir directo a walls/openings/executor
**Pros:** más cerca del objetivo final.
**Contras:** mezcla demasiada complejidad sin prueba previa de calidad del modelo.

Se elige **B** porque maximiza aprendizaje y reduce riesgo estructural.

## Architecture

### Existing Inputs
`SEMINOLE2000` ya aporta:
- `footprint_bbox`
- `rooms[]` con `name`, `polygon`, `bbox`, `centroid`, `width`, `height`, `area`, `measurement_source`
- `source_layers`
- `block_refs`
- `readiness`

Además, el extractor CAD actual tiene acceso a `floor_plan.entities`, layers como `WALLS`, `DOORS`, `WINS`, `FIXTURES`, `DIMS`, y al `bbox` global del floor plan.

### New Derived Model: `FloorPlanTopologyV1`
Se agregará una derivación nueva, separada del seed, con foco en topología mínima.

#### Global fields
- `floor_plan_id`
- `name`
- `canonical_unit`
- `footprint_bbox`
- `topology_readiness`
- `topology_issues[]`

#### Per-room fields
- `room_id` — estable y determinístico
- `name`
- `category` — bedroom, bath, kitchen, garage, closet, patio, etc.
- `polygon`
- `bbox`
- `centroid`
- `width`
- `height`
- `area`
- `measurement_source`
- `adjacent_room_ids[]`
- `is_exterior_touching`
- `issues[]`

### Deliberate Non-Goals for V1
Topology V1 NO incluye todavía:
- `wall_id`
- shared wall ownership completo
- openings hosteados por wall
- mutaciones geométricas
- regeneración DXF

Eso queda para slices posteriores.

## Topology Derivation Rules

### 1. Stable `room_id`
`room_id` debe ser determinístico entre corridas del mismo floor plan. La estrategia inicial será derivarlo desde nombre normalizado + posición espacial estable (centroid/bbox ordenado), evitando IDs aleatorios.

### 2. Category inference
La categoría del room se infiere desde el nombre normalizado:
- `BEDROOM`, `MASTER BEDROOM` -> `bedroom`
- `BATH`, `MASTER BATH` -> `bath`
- `KITCHEN` -> `kitchen`
- `PATIO` -> `patio`
- etc.

Si no hay categoría confiable, se marca issue.

### 3. Adjacency inference
Dos rooms son adyacentes si sus polígonos comparten una frontera significativa o una separación bajo tolerancia compatible con el ruido del curado actual. La tolerancia debe ser explícita y testeada.

Adjacency V1 apunta a responder:
- qué room toca cuál
- qué rooms aparecen aislados anómalamente
- si faltan relaciones obvias

### 4. Exterior-touch inference
Un room se marca como `is_exterior_touching` cuando su polígono toca el contorno exterior del floor plan o una frontera equivalente al footprint bajo tolerancia definida.

### 5. Issues per room
Ejemplos de issues V1:
- `missing_category`
- `isolated_room`
- `suspicious_polygon`
- `no_exterior_touch_on_perimeter_room`
- `unexpected_large_bbox`

## UI Design: Temporary Topology Inspector

### Placement
No forma parte todavía del shell de producto final. Será una screen/debug route temporal, fácil de borrar, destinada a validar curado.

### Main layout
La vista se divide en tres zonas:

#### A. Canvas central (source of truth visual)
Renderiza el plano real desde la data curada/topológica, no cajas abstractas.

Capas con toggles:
- raw room polygons
- room labels
- room IDs
- room categories
- adjacency links
- exterior-touch highlight
- room issues

#### B. Inspector lateral derecho
Muestra el room seleccionado:
- `room_id`
- `name`
- `category`
- medidas
- área
- `measurement_source`
- `adjacent_room_ids`
- `is_exterior_touching`
- issues

#### C. Global validation panel
Resumen del floor plan:
- cantidad de rooms
- cantidad con category válida
- cobertura de adjacency
- cantidad de rooms que tocan exterior
- topology issues globales
- readiness del topology model

### Interaction model
- click en room -> selección y focus en inspector lateral
- toggles de capas -> alternan lectura del mismo plano
- hover opcional -> resalta room y sus adyacencias
- no edición geométrica todavía

## Data Flow
1. Se toma `seminole-2000.json` como fuente curada actual.
2. Una nueva derivación crea `FloorPlanTopologyV1`.
3. La UI consume ese objeto topológico.
4. El canvas renderiza rooms y relaciones.
5. El panel lateral y el resumen global muestran estado de curado.

## Validation Strategy
La screen será considerada útil si permite verificar visualmente:
- que cada room tenga identidad coherente
- que las categorías no sean absurdas
- que las relaciones de adyacencia hagan sentido espacial
- que los rooms exteriores estén bien marcados
- que los issues se entiendan y se puedan corregir

## Testing Strategy

### Backend
Tests de derivación topológica:
- `room_id` estable entre corridas
- category inference correcta en rooms conocidas de Seminole
- adjacency razonable en casos conocidos
- exterior-touch correcto para rooms perimetrales
- issues cuando faltan señales confiables

### Frontend
Tests del inspector:
- renderiza rooms reales desde topology data
- alterna capas correctamente
- selección de room actualiza panel lateral
- muestra adjacency y issues del room seleccionado
- summary global refleja topology state

## Files Expected

### Backend
- `backend/floor_plan_catalog/topology.py`
- `backend/floor_plan_catalog/contracts.py` (extensión o nuevo contrato)
- `tests/test_floor_plan_catalog_topology.py`

### Frontend
- `frontend/src/features/catalogInspector/` (feature temporal y removible)
- componentes del inspector visual
- tests de rendering/interacción mínimos

## Risks
- La tolerancia espacial para inferir adjacency puede producir falsos positivos o negativos si se define mal.
- `room_id` puede volverse inestable si depende de señales demasiado débiles.
- Algunas categorías pueden requerir mapping manual si los labels no son uniformes.

## Follow-up Slices
Después de esta prueba visual/topológica:
1. `Boundary / Wall Graph V1`
2. openings / ownership
3. Reconstruction Plan textual
4. executor geométrico
5. regeneración DXF final

## Success Criteria
Este slice se considera exitoso cuando:
- `SEMINOLE2000` tiene Topology V1 derivada con fields mínimos confiables
- existe una screen visual temporal que usa geometría real del plano
- la screen permite validar room IDs, categorías, exterior-touch y adjacency
- los problemas de curado quedan visibles antes de avanzar al executor
