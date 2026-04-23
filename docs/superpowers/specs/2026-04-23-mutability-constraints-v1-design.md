# Mutability / Constraints v1 Design

## Context

`SEMINOLE2000` ya está mucho más cerca de un plano operable que de un dibujo crudo:

- `topology_issues = []`
- `wall_graph_issues = []`
- `boundary kinds = { duplicate: 404, exterior: 182, artifact: 106, support: 40, unknown: 14, shared: 10 }`
- `opening confidence = { hosted: 70, opening_artifact: 47, unhosted: 4 }`

Eso significa que el cuello de botella principal ya no es “entender qué hay”, sino “saber qué se puede tocar sin romper el plano”.

Hoy el código todavía no tiene una capa executor-grade de restricciones:

- `CatalogRoomTopology` no expone `is_wet_zone`, `is_core`, `mutability`, `min_width`, `min_height`, `min_area`
- `CatalogWallBoundary` no expone `movable` ni razones de protección
- `CatalogBoundarySegment` no expone operabilidad estructural para el executor
- `backend/site_fit/solver.py` sigue devolviendo solo baseline

## Problem

El sistema ya entiende rooms, walls, boundaries y openings bastante bien, pero todavía no sabe distinguir entre:

1. piezas que **se pueden mover**
2. piezas que **solo se pueden mover si se rehostean openings**
3. piezas que conviene **proteger**
4. piezas que deben quedar **bloqueadas**

Sin esta capa, el futuro executor no tiene una gramática segura para adaptar “solo lo necesario”.

## Goal

Agregar una primera capa conservadora de **mutability / constraints** sobre el modelo curado para que el sistema pueda:

- clasificar rooms como `flexible | protected | locked`
- clasificar boundaries/walls como `movable | movable_with_rehost | protected | locked | derived_only`
- derivar mínimos geométricos conservadores (`min_width`, `min_height`, `min_area`)
- exponer estas decisiones en el inspector técnico

## Code Baseline

Esta capa NO intenta codificar “todo ICC”.

La base correcta para v1 es:

- tratar **ICC/IRC como model code**, no como ley universal
- asumir como baseline técnica el **IRC 2021** para vivienda low-rise
- dejar explícito que la adopción final depende de jurisdicción/local amendments

Para nuestro motor, lo que importa no es copiar el libro entero sino traducir a operabilidad el subset que decide:

1. qué pieza **no se puede tocar**
2. qué pieza queda **protegida**
3. qué pieza podría moverse **solo con rehost**
4. qué pieza es realmente **flexible**

## Code-informed scope for v1

### Hard locks

Estas restricciones no deberían violarse automáticamente:

- **egress door principal**
  - side-hinged
  - `32 in` clear width
  - `78 in` clear height
  - camino continuo al exterior sin pasar por garage
- **stairs**
  - se tratan como `locked` por ahora si aparecen como categoría/área crítica
- **structural_unknown**
  - cualquier boundary/wall con incertidumbre estructural queda `locked`

### Protected

Estas se pueden modelar, pero no mutar libremente en v1:

- **wet core**
  - `kitchen`, `bath`, `powder_room`, `utility`
- **garage separation**
  - boundaries entre `garage` y dwelling quedan `protected`
- **critical circulation**
  - `entry`, `hall`
- **required sleeping-room egress openings**
  - si una opening exterior de dormitorio parece cumplir rol de rescate/egress, su host boundary queda al menos `protected`

### Flexible

Primera zona candidata a ajuste:

- `living_room`
- `dining`
- porciones de `garage`
- perímetro exterior sin openings críticas
- shared boundaries entre rooms flexibles

## Non-goals

Este slice **no** implementa todavía:

- mutadores reales de site-fit
- geometry executor
- rehosting activo de openings
- DXF recompilation

Es una capa de preparación para todo eso.

## Approaches

### Option A — Enriquecer el modelo actual con un derivador dedicado (**recommended**)

Crear un módulo `backend/floor_plan_catalog/mutability.py` que derive restricciones desde:

- topology fortalecida
- wall graph
- opening graph
- boundary graph

y escriba esos campos directamente en los contratos existentes para rooms, walls y boundaries.

#### Pros
- deja un payload único y fácil de inspeccionar
- prepara directamente al inspector y al futuro `site_fit`
- no duplica una “verdad paralela” de constraints

#### Cons
- requiere extender contratos existentes
- toca más archivos ahora

### Option B — Crear un `constraint_graph` separado

Derivar constraints en un artefacto aparte, sin tocar los modelos actuales.

#### Pros
- más aislamiento conceptual

#### Cons
- duplica referencias por `room_id`, `wall_id`, `boundary_id`
- hace más pesada la exportación y la UI
- retrasa la adopción en `site_fit`

### Option C — Saltar directo al mutation contract

#### Pros
- parece acercarnos más rápido al objetivo final

#### Cons
- prematuro
- metería operaciones sobre piezas sin reglas claras de protección

## Decision

Elegir **Option A**.

La forma más sana de avanzar es enriquecer el modelo actual con restricciones conservadoras y auditables, no abrir otra capa paralela ni saltar al executor prematuramente.

## Design

### 1. Room constraints

Cada `CatalogRoomTopology` debería exponer:

- `is_wet_zone: bool`
- `is_core: bool`
- `mutability: flexible | protected | locked`
- `min_width: float | None`
- `min_height: float | None`
- `min_area: float | None`
- `constraint_reasons: string[]`

#### Reglas base conservadoras

- `bath`, `powder_room`, `kitchen`, `utility` → `is_wet_zone = True`, `is_core = True`, `mutability = protected`
- `entry`, `hall`, `closet` → `is_core = True`, `mutability = protected`
- `patio`, `porch` → `mutability = locked`
- `bedroom`, `living_room`, `dining`, `garage` → `mutability = flexible`

#### Reglas code-informed adicionales

- si una room está pegada a mínimos geométricos conservadores, escala a `protected`
- si una room participa del camino de egreso principal, escala a `protected`
- si una room depende de una opening exterior requerida para sleeping-room egress, la boundary host de esa opening no se trata como libremente movible

#### Mínimos geométricos

Los mínimos no buscan ser compliance legal perfecta; buscan impedir que el mutator destruya el plano mientras seguimos una baseline IRC-informed.

#### Mínimos habitables que sí conviene traducir ya

- habitable rooms:
  - `70 sq ft` mínimo
  - `7 ft` mínimo en dimensión horizontal

#### Lo que NO podemos derivar bien todavía

- ceiling-height compliance
- full fixture clearances
- full structural spans

Eso queda documentado como **deferred**, no como constraint falsa.

- `locked` / `protected` rooms arrancan con mínimos iguales a su geometría actual
- `flexible` rooms arrancan con mínimos derivados de:
  - un piso por categoría
  - la baseline habitable IRC-informed
  - y un porcentaje conservador de la geometría actual

### 2. Boundary constraints

Cada `CatalogBoundarySegment` debería exponer:

- `mutability: movable | movable_with_rehost | protected | locked | derived_only`
- `movable: bool`
- `constraint_reasons: string[]`

#### Reglas base

- `duplicate`, `artifact`, `support` → `derived_only`, `movable = False`
- `shared` / `exterior` canónicas:
  - si pertenecen a room `locked` → `locked`
  - si tocan room `protected` → `protected`
  - si hostean openings `hosted` → `movable_with_rehost`
  - si pertenecen a rooms `flexible` y no hostean openings → `movable`

#### Reglas code-informed adicionales

- boundary host de **required egress door** → `locked`
- boundary host de **sleeping-room egress opening** → `protected`
- boundary entre `garage` y `dwelling` → `protected`
- boundary marcada `structural_unknown` → `locked`

### 3. Wall constraints

Las walls seguirán siendo la vista semántica del boundary graph, así que cada `CatalogWallBoundary` debería reflejar:

- `mutability`
- `movable`
- `constraint_reasons`

La mutabilidad de la wall nace de la boundary/wall canónica más fuerte que la respalda.

### 4. Opening constraints

Para este slice alcanza con agregar a `CatalogOpening`:

- `rehost_required: bool`
- `rehostable: bool`
- `constraint_reasons: string[]`

#### Regla

- `hosted` sobre boundary movible → `rehost_required = True`, `rehostable = True`
- `opening_artifact` / `unhosted` → `rehostable = False`
- opening identificada como **required egress** → `rehost_required = False`, `rehostable = False`, `constraint_reasons += ['required_egress_opening']`

### 5. Derivation module

Agregar `backend/floor_plan_catalog/mutability.py` con una función principal tipo:

```python
def derive_floor_plan_mutability(
    topology: FloorPlanTopologyV1,
    wall_graph: FloorPlanWallGraphV1,
    opening_graph: FloorPlanOpeningGraphV1,
    boundary_graph: FloorPlanBoundaryGraphV1,
) -> tuple[FloorPlanTopologyV1, FloorPlanWallGraphV1, FloorPlanOpeningGraphV1, FloorPlanBoundaryGraphV1]:
    ...
```

La derivación debe ser:

- determinística
- conservadora
- basada en semántica actual, no en heurística nueva de detección

### 6. Heuristics we explicitly allow in v1

Como todavía no tenemos una capa legal/jurisdiction-aware completa, v1 solo permite estas heurísticas conservadoras:

- inferir `garage separation` por boundary compartida entre `garage` y room no-garage
- inferir `wet core` por categoría de room
- inferir `critical circulation` por categoría `entry/hall`
- inferir `required sleeping-room egress opening` cuando:
  - la opening es `window`
  - está hosteada en boundary `exterior`
  - owner room incluye categoría `bedroom`

Estas heurísticas NO pretenden certificar legalmente el plano; pretenden impedir mutaciones tontas en el executor v1.

### 7. Inspector surfacing

El inspector temporal debe mostrar:

- métricas:
  - flexible rooms
  - protected rooms
  - locked rooms
  - movable boundaries
  - movable-with-rehost boundaries
  - protected/locked boundaries
- sidebar:
  - room mutability + mínimos + razones
  - wall/boundary mutability + razones
  - opening rehost flags + razones

## Files in Scope

### Backend
- `backend/floor_plan_catalog/contracts.py`
- `backend/floor_plan_catalog/mutability.py`
- `backend/floor_plan_catalog/opening_graph.py` (only if opening flags are easiest to enrich there)
- `scripts/export_seminole_topology_fixture.py`

### Tests
- `tests/test_floor_plan_catalog_mutability.py`
- existing catalog tests only if contract propagation needs coverage

### Frontend
- `frontend/src/features/catalogInspector/types.ts`
- `frontend/src/features/catalogInspector/CatalogInspectorPage.tsx`
- `frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx`
- `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx`
- `frontend/src/features/catalogInspector/catalogInspector.fixture.json`

## Testing Strategy

### RED tests first

1. synthetic derivation test for room category → mutability mapping
2. synthetic derivation test for boundary/wall mutability:
   - movable
   - movable_with_rehost
   - protected
   - locked
   - derived_only
3. synthetic code-informed test:
   - garage separation stays `protected`
   - bedroom exterior window becomes `required_egress_opening`
   - main egress door host stays `locked`
4. real Seminole regression:
   - all rooms classified
   - all canonical shared/exterior boundaries classified
   - duplicates/artifacts/support remain non-movable
   - `opening_artifact` remains non-rehostable
5. inspector fixture/UI tests for new metrics and sidebar labels

### Guardrails

Este slice **no cuenta** como mejora si:

- rompe `shared = 10`, `exterior = 182`, `support = 40`, `unknown = 14`
- cambia counts estructurales sin necesidad
- marca como movible una boundary `duplicate/artifact/support`
- marca como rehostable una opening `opening_artifact`
- marca como movible una boundary protegida por `required_egress_opening` o `garage separation`

## Success Criteria

El slice es exitoso si:

- todas las rooms tienen `mutability` + mínimos + razones
- todas las boundaries canónicas relevantes tienen `mutability` explícita
- walls reflejan esa mutabilidad sin contradicciones
- openings hosteadas marcan correctamente si exigirían rehost
- el inspector muestra el estado nuevo honestamente

## Why this is the smart next step

Ya casi no estamos peleando contra detección.  
Ahora el sistema necesita aprender **qué puede tocar** y **qué no**.

Sin eso, cualquier mutation contract sería una locura cósmica.

## References

- ICC code adoption background: https://www.iccsafe.org/wp-content/uploads/adoption_ordinances/HowStatesAdopt_I-Codes.pdf
- IRC overview: https://www.iccsafe.org/products-and-services/i-codes/2018-i-codes/irc/
- 2021 IRC Plan Review (means of egress / egress door / emergency escape): https://www.iccsafe.org/wp-content/uploads/Session-41-and-67-2021-IRC-Plan-Review.pdf
- IRC Building references (garage separation / habitable room mins): https://www.iccsafe.org/wp-content/uploads/IRC-Building.pdf
