# NormalizedPlan v2 Design

## Context

El catálogo curado ya dejó de ser solo un visor técnico. Hoy `SEMINOLE2000` ya exporta:

- rooms con `mutability`, mínimos y `constraint_reasons`
- walls con `movable / movable_with_rehost / protected / locked`
- boundaries con clasificación canónica y mutability
- openings con `rehost_required` / `rehostable`

Verificación actual del fixture real:

- `room_mutability = { protected: 9, flexible: 5, locked: 2 }`
- `wall_mutability = { protected: 96, locked: 46, movable: 37, movable_with_rehost: 15 }`
- `boundary_mutability = { derived_only: 550, protected: 93, locked: 59, movable: 39, movable_with_rehost: 15 }`
- `opening_confidence = { hosted: 70, opening_artifact: 47, unhosted: 4 }`

Pero `site_fit` todavía recibe un `NormalizedPlan` demasiado pobre:

- `room_count`
- `wall_count`
- `opening_count`
- `footprint_bbox`

Y el solver sigue devolviendo solo baseline.

## Problem

El bounded context `site_fit` todavía razona sobre un resumen geométrico muy chico.
Eso alcanza para decir:

- entra / no entra por bbox

pero NO alcanza para decir:

- qué boundary invade
- qué room dueña está afectada
- qué opening exigiría rehost
- qué piezas están `protected` o `locked`
- qué cambios son legal/técnicamente elegibles

## Goal

Expandir `NormalizedPlan` para que `site_fit` reciba un **assembly mutable reducido**, no solo counts + bbox.

Ese assembly tiene que ser lo suficientemente rico para:

1. detectar overflow por pieza
2. decidir elegibilidad de mutación
3. preparar el primer mutator real

Sin todavía implementar el executor completo.

## Non-goals

Este slice NO implementa todavía:

- mutadores reales
- geometry executor
- DXF recompilation
- site-aware optimization multi-candidate

Es la capa puente entre el catálogo curado y el primer mutator real.

## Approaches

### Option A — Enriquecer `NormalizedPlan` con un assembly reducido (**recommended**)

Mantener `NormalizedPlan` como contrato central de `site_fit`, pero expandirlo para incluir solo las piezas necesarias:

- footprint/bbox
- rooms resumidas con mutability
- boundaries candidatas
- walls candidatas
- openings hosteadas/rehostables

#### Pros
- reutiliza el contrato actual
- mantiene `site_fit` desacoplado del catálogo bruto
- permite crecer hacia constraint evaluation v2 sin romper todo

#### Cons
- obliga a rediseñar `normalize_plan(...)`
- toca contratos backend de `site_fit`

### Option B — Pasar el catálogo entero a `site_fit`

Mandar topology + wall graph + opening graph + boundary graph completos como payload.

#### Pros
- máxima fidelidad

#### Cons
- demasiado acoplamiento
- `site_fit` quedaría pegado a detalles internos del catálogo
- mete más ruido que valor para el primer mutator

### Option C — Seguir con bbox hasta tener executor completo

#### Pros
- no toca contratos ahora

#### Cons
- mala dirección
- deja bloqueado el primer mutator real
- prolonga un `site_fit` ciego a piezas

## Decision

Elegir **Option A**.

`site_fit` no necesita todo el catálogo; necesita un **assembly mutable reducido, explícito y estable**.

## Design

### 1. Expandir `NormalizedPlan`

`backend/site_fit/models.py`

Agregar campos como:

- `room_summaries: list[dict]`
- `boundary_segments: list[dict]`
- `wall_segments: list[dict]`
- `openings: list[dict]`
- `movable_boundary_count`
- `protected_boundary_count`
- `locked_boundary_count`
- `rehostable_opening_count`

### 2. Contract shape

#### Room summary

Solo lo que `site_fit` necesita:

- `room_id`
- `name`
- `category`
- `mutability`
- `min_width`
- `min_height`
- `min_area`
- `bbox`
- `owner_boundary_ids`

#### Boundary segment

- `boundary_id`
- `boundary_kind`
- `owner_room_ids`
- `mutability`
- `movable`
- `constraint_reasons`
- `start`
- `end`
- `length`
- `opening_ids`

#### Wall segment

- `wall_id`
- `boundary_kind`
- `owner_room_ids`
- `mutability`
- `movable`
- `hosted_opening_ids`
- `start`
- `end`
- `length`

#### Opening summary

- `opening_id`
- `opening_kind`
- `host_wall_id`
- `owner_room_ids`
- `confidence`
- `rehost_required`
- `rehostable`
- `constraint_reasons`
- `offset`
- `span`

### 3. Source of truth for normalization

Para `source_kind == "catalog_floor_plan"` o equivalente, `normalize_plan(...)` debería construir `NormalizedPlan v2` desde el modelo curado ya enriquecido.

La regla importante es esta:

- `site_fit` NO recibe raw traces
- `site_fit` SÍ recibe piezas canónicas/operables

### 4. Constraint Evaluation v2 prep

Aunque este slice no implementa la evaluación nueva completa, tiene que dejar listo el contrato para que el paso siguiente pueda decir:

- qué boundaries son elegibles para tocar
- qué overflow cae sobre qué boundary
- qué boundaries con openings pasan a `movable_with_rehost`

### 5. Backward compatibility

Para no romper todo de golpe, `NormalizedPlan` puede mantener temporalmente:

- `room_count`
- `wall_count`
- `opening_count`
- `footprint_bbox`

pero ya derivados del assembly nuevo.

### 6. Validation rules for the slice

`NormalizedPlan v2` cuenta como bueno si:

- toda boundary canónica relevante tiene `mutability`
- toda opening exportada a `site_fit` expone `rehost_required` / `rehostable`
- `site_fit` deja de depender solo de bbox + counts para razonar sobre elegibilidad
- el payload no arrastra raw CAD noise innecesario

## Files in Scope

### Backend
- `backend/site_fit/models.py`
- `backend/site_fit/normalizer.py`
- probablemente `backend/site_fit/contracts.py` si hace falta separar shape
- tests de `site_fit`

### Inputs to read/adapt
- `backend/floor_plan_catalog/contracts.py`
- `backend/floor_plan_catalog/mutability.py`
- payloads actuales usados por `site_fit`

## Testing Strategy

### RED tests first

1. `normalize_plan(...)` para floor plan curado debe exportar room summaries con mutability
2. debe exportar boundaries/walls/openings operables
3. debe preservar counts legacy coherentes
4. no debe exportar raw CAD traces
5. regresión real con `SEMINOLE2000`

### Guardrails

Este slice NO cuenta como mejora si:

- `NormalizedPlan` sigue sin boundaries/walls/openings utilizables
- el payload crece con ruido innecesario
- se pierde mutability/rehostability al cruzar de catálogo a `site_fit`

## Success Criteria

- `site_fit` recibe por primera vez un modelo rico en piezas mutables
- el próximo slice (`Constraint Evaluation v2`) puede trabajar por boundary en vez de bbox sola
- queda preparado el primer mutator real sin volver a tocar el catálogo

## Why this is the smart next step

Hoy el bloqueo ya no está en detectar el plano.

El bloqueo está en que el bounded context que debería adaptarlo sigue viendo una sombra muy pobre del modelo real.

`NormalizedPlan v2` es el puente correcto entre:

- catálogo curado executor-grade
- primer site-fit mutator real
