# Stronger Opening Hosting v2 Design

## Goal
Aumentar de forma material la cantidad y calidad de openings hosteadas sobre geometría canónica, reduciendo `unhosted_openings` sin reintroducir heurística floja en walls o boundaries.

## Why This Matters Now
Después de `Exact Boundary Dedup / Family Clustering v1`, el graph quedó mucho más canónico:

- `duplicate = 404`
- `exterior = 182`
- `shared = 10`
- `support = 29`
- `unknown = 131`

Y el cuello de botella real pasó a ser opening hosting:

- `openings_total = 162`
- `hosted = 51`
- `unhosted = 111`
- `hosted_doors = 33`
- `hosted_windows = 18`

Eso significa que ya entendemos bastante mejor el esqueleto del plano, pero todavía no podemos decir con suficiente confianza:
- qué opening cuelga de qué boundary/wall exacta
- qué apertura habría que mover si una boundary cambia
- qué puertas/ventanas son operables en un futuro executor

## Problem Statement
Hoy `opening_graph.py` hostea openings por una estrategia simple:

1. toma cada `door/window trace`
2. busca una `wall` candidata por orientación, overlap y axis gap
3. agrupa por `(trace_kind, host_wall_id, center bucket)`
4. construye una opening `hosted` o `unhosted`

Ese approach fue suficiente para arrancar, pero tiene límites claros:
- depende más de `walls` que del boundary graph canónico
- no aprovecha todavía `boundary_family_id` ni `family_role`
- no diferencia bien entre candidates canónicas y candidates duplicadas/secundarias
- deja demasiadas openings sin host aunque el graph hoy ya es bastante más limpio

## Recommended Approach
Se evaluaron tres caminos:

### A. Empujar thresholds del hoster actual
**Pros:** rápido.  
**Contras:** heurística berreta; puede subir hosting a costa de precisión.

### B. Boundary-first opening hosting (**recomendado**)
**Pros:** aprovecha el graph más canónico actual, mejora `host_wall_id` sin volver atrás arquitectónicamente.  
**Contras:** requiere tocar matching, grouping y ranking.

### C. Saltar a mutability/executor ya
**Pros:** parece avance rápido.  
**Contras:** locura cósmica; todavía faltan openings bien hosteadas.

Se elige **B**.

## Scope
Este slice hace solo esto:

1. fortalecer host selection de openings usando mejor señal estructural
2. privilegiar walls/boundaries canónicas frente a duplicadas/secundarias
3. mejorar grouping de fragmentos door/window cercanos
4. reducir `unhosted_openings` desde la baseline actual (`111`)
5. exponer mejor confidence/issues en el inspector técnico

## Non-Goals
Este slice NO hace todavía:
- mutability / constraints
- geometry executor
- rehosting dinámico post-mutación
- DXF recompilation
- solución perfecta del 100% de openings

## Design Summary
El salto correcto acá es pasar de un hoster principalmente wall-based a uno más **boundary-aware**.

La pregunta ya no es solo:
> “qué wall está cerca de esta traza”

Sino:
> “qué host canónico del graph explica mejor esta apertura y qué tan confiable es esa decisión”

## Proposed Model Behavior

### 1. Candidate ranking más fuerte
El matching de openings debe priorizar, en este orden:

1. walls derivadas de piezas **canónicas**, no duplicadas
2. boundaries/walls con mejor `boundary_kind`:
   - `shared` para doors interiores
   - `exterior` para windows y ciertas doors exteriores
3. menor `axis_gap`
4. mayor overlap/span support
5. mejor family/context confidence

### 2. Duplicate-aware hosting
Si una opening cae cerca de una wall/boundary duplicada, no debe hostearse ahí si existe una equivalente canónica mejor.

Regla:
- las piezas `duplicate` pueden servir como evidencia
- pero el `host_wall_id` final debe preferir la representante canónica cuando exista

### 3. Better grouping of fragmented traces
Hoy varias openings quedan partidas en trazas chicas.

Hay que agrupar mejor fragmentos que:
- comparten kind (`door` / `window`)
- caen sobre el mismo host canónico
- tienen intervalos contiguos o muy cercanos

Esto debería subir hosting sin inflar openings falsas.

### 4. Confidence policy for openings
La confidence debe distinguir mejor:
- `hosted_canonical`
- `hosted_supported`
- `unhosted`

Y issues más útiles como:
- `host_only_duplicate_candidate`
- `ambiguous_host_candidates`
- `insufficient_host_overlap`

## Architecture Impact

### Current pipeline
1. seed / cad_traces
2. boundary graph
3. wall graph
4. opening graph

### New intent
El `opening_graph` tiene que empezar a apoyarse en la semántica nueva del graph más limpio:
- family metadata
- canonical-vs-duplicate distinction
- better boundary/wall provenance

## Inspector Impact
El inspector técnico debe dejar más claro:
- cuántas openings están hosteadas
- cuántas siguen unhosted
- si una opening quedó hosteada sobre una pieza canónica o secundaria
- qué issue tiene una unhosted

### UI changes for this slice
- métricas más claras para hosted/unhosted
- si hace falta, badge de confidence más explícita
- selected opening panel con issues más informativas

## Success Criteria
Este slice se considera exitoso si logra:

1. bajar `unhosted_openings` por debajo de la baseline actual (`111`)
2. aumentar hosting sin degradar la honestidad del modelo
3. preferir hosts canónicos frente a duplicados cuando aplique
4. mantener sano:
   - `unsupported_exterior = 0`
   - `unsupported_shared = 0`
   - boundary graph actual
5. dejar la capa de openings mejor preparada para mutability/executor

## Testing Strategy
Strict TDD:

1. test sintético donde una opening compite entre candidate canónica y duplicate
2. test de grouping de fragmentos cercanos sobre mismo host
3. test de preference por shared/exterior según kind
4. test real de Seminole que pruebe baja de `unhosted`
5. test frontend para confidence/issues actualizadas si cambia la UI

## Risks

### Risk 1: subir hosting con baja precisión
**Mitigation:** ranking conservador y tests sintéticos claros.

### Risk 2: hostear sobre duplicados
**Mitigation:** canonical-first ranking explícito.

### Risk 3: mezclar puertas y ventanas de forma incorrecta en grouping
**Mitigation:** grouping siempre separado por `opening_kind`.

## Expected Next Step After This Slice
Si este slice sale bien, el siguiente puente fuerte sí pasa a ser:

1. `mutability / constraints`
2. `site-aware mutation contract`
3. después recién `geometry executor`

## Bottom Line
El boundary graph ya dio un salto fuerte.  
Ahora toca hacer que las openings realmente se apoyen sobre ese graph más canónico.

Ese es el siguiente paso senior de verdad antes del executor.
