# Exact Boundary Dedup / Family Clustering v1 Design

## Goal
Reducir el ruido geométrico del boundary graph convirtiendo grupos de boundaries duplicadas o equivalentes en **familias canónicas**, de modo que el plano quede más cerca de un ensamblaje rearmable y menos cerca de un montón de fragmentos repetidos.

## Why This Matters Now
El estado actual del fixture real de `SEMINOLE2000` ya muestra que el cuello de botella cambió:

- `exterior = 388`
- `shared = 22`
- `support = 60`
- `unknown = 286`
- `unsupported_exterior = 0`
- `unsupported_shared = 0`

Pero el dato importante es este:

> las `286 unknown boundaries` actuales participan en grupos de geometría duplicada.

Además:
- `250` unknown miden `<= 8`
- `264` unknown miden `<= 12`
- `0` unknown tienen `owner_room_ids`
- `0` unknown tienen `opening_ids`

Eso sugiere que el problema principal ya no es “falta detectar paredes”, sino **canonicalizar mejor lo ya detectado**.

## Problem Statement
Hoy `boundary_graph.py` hace un buen trabajo en:
- partir traces en segmentos
- detectar intersecciones y opening cuts
- clasificar parte del graph como `shared`, `exterior` o `support`

Pero todavía emite muchas boundaries que:
- tienen la misma geometría que otras
- representan la misma evidencia estructural
- o son microfragmentos redundantes de una misma familia visual/constructiva

Eso mete tres problemas:

1. **infla el graph artificialmente**
2. **ensucia la lectura visual del inspector**
3. **debilita el modelo futuro del executor**, que necesita una pieza canónica por tramo, no muchas copias equivalentes

## Recommended Approach
Se evaluaron tres caminos:

### A. Ocultar las unknown chicas en la UI
**Pros:** mejora visual rápida.  
**Contras:** maquillaje; el pipeline sigue sucio.

### B. Deduplicar families en `boundary_graph.py` (**recomendado**)
**Pros:** arregla el modelo real, baja ruido y fortalece la base del executor.  
**Contras:** requiere tocar el corazón de la derivación.

### C. Seguir agregando heurísticas de room/wall ownership
**Pros:** puede reclasificar algunos casos.  
**Contras:** ataca el síntoma, no la causa principal actual.

Se elige **B**.

## Scope
Este slice hace solo esto:

1. detectar **familias de boundaries equivalentes**
2. elegir una **boundary canónica** por familia
3. marcar miembros secundarios / duplicados sin perder trazabilidad
4. bajar la cantidad de `unknown` redundantes del graph exportado
5. exponer la nueva capa en el inspector para entender:
   - qué boundary es canónica
   - cuáles son duplicadas/miembros de familia

## Non-Goals
Este slice NO hace todavía:
- mutability / constraints
- site-aware mutation contract
- geometry executor
- DXF recompilation
- solución final del 100% de unknown boundaries
- perfeccionamiento completo de opening hosting

## Design Summary
La solución introduce una idea nueva entre `boundary derivation` y `graph export`:

# `boundary family`

Una family agrupa boundaries que representan el mismo tramo estructural canónico o una variación redundante del mismo.

### Resultado esperado
En vez de exportar muchas `unknown` casi iguales, el graph debe poder decir:
- esta es la **boundary canónica**
- estas otras son **miembros duplicados / companions / secundarios**

## Proposed Model Changes

### `CatalogBoundarySegment`
Agregar campos mínimos para trazabilidad de familia:

- `boundary_family_id: str | None`
- `family_role: canonical | duplicate | support | unknown`
- `duplicate_of_boundary_id: str | None`

### Semantics
- **canonical**: boundary que queda como representante operable de la familia
- **duplicate**: boundary redundante con misma geometría canónica, no operable por sí sola
- **support**: boundary paralela/companion ya detectada como shell secundaria
- **unknown**: sigue sin familia ni clasificación útil

## Family Detection Rules

### 1. Exact geometry duplicates
Si dos o más boundaries tienen:
- misma orientación
- mismos endpoints normalizados

entonces forman una familia de duplicados exactos.

#### Policy
- elegir una boundary canónica determinística
- el resto pasa a `family_role = duplicate`
- heredan `boundary_family_id`
- apuntan a `duplicate_of_boundary_id`

### 2. Near-identical fragments
Si los tramos:
- son ortogonales
- comparten eje
- tienen overlap casi total
- difieren solo en microfragmentación o corte redundante

pueden entrar en la misma familia si la evidencia lo justifica.

### 3. Support remains explicit
Las `support` ya introducidas no desaparecen.
Se mantienen visibles porque siguen aportando lectura de shell/espesor.
Pero también deben poder participar de una family cuando corresponda.

## Canonical Selection Policy
La boundary canónica de una familia debe elegirse de forma determinística usando esta prioridad:

1. boundary con mejor `boundary_kind`:
   - `shared`
   - `exterior`
   - `support`
   - `unknown`
2. mayor confianza:
   - `trace_projected`
   - `trace_exact`
   - `trace_partitioned`
   - `trace_companion`
   - `unverified`
3. mayor longitud
4. `boundary_id` lexicográficamente menor como tie-breaker final

Esto evita decisiones no reproducibles.

## Export Policy
El exporter del fixture debe seguir mostrando todas las piezas necesarias para inspección, pero con semántica clara:

### Required behavior
- las boundaries canónicas siguen visibles como piezas principales
- los duplicados siguen trazables pero claramente marcados como secundarios
- el inspector puede enfocarse en:
  - canonical boundaries
  - duplicate family members
  - support boundaries
  - unresolved unknowns

## Inspector Impact
El inspector técnico debe poder responder:

- ¿esta línea es una pieza canónica o un duplicado?
- ¿de qué familia forma parte?
- ¿qué boundary sería la operable después?

### UI changes for this slice
- nueva metadata en sidebar de boundary:
  - `family id`
  - `family role`
  - `duplicate of`
- nueva métrica opcional:
  - `Duplicate boundaries`
- color/estilo visual diferenciado para duplicados
- ability to focus on duplicate family members

## Pipeline Impact
La intención arquitectónica de este slice es seguir consolidando un pipeline **boundary-first**:

1. raw traces
2. segmented boundaries
3. family clustering / dedup
4. canonical boundary graph
5. walls derived from canonical graph
6. openings hosted on stronger geometry
7. rooms and later executor behavior

Esto fortalece la idea correcta:
# `boundary + node` como pieza canónica futura

y no una nube de segmentos redundantes.

## Success Criteria
Este slice se considera exitoso si logra:

1. bajar `unknown boundaries` por debajo del estado actual (`286`)
2. demostrar que parte importante de las unknown eran duplicados/familias redundantes
3. hacer visible cuál boundary es canónica y cuál no
4. no romper:
   - `unsupported_exterior = 0`
   - `unsupported_shared = 0`
   - opening hosting actual
5. dejar el graph más preparado para el siguiente salto:
   - stronger opening hosting
   - mutability / constraints

## Testing Strategy
Strict TDD:

1. test sintético de boundaries duplicadas exactas
2. test de selección de boundary canónica determinística
3. test de persistencia de `support` como pieza explícita
4. test real sobre `SEMINOLE2000` que pruebe:
   - baja de `unknown`
   - aparición de `duplicate` / family metadata
5. test frontend del inspector que muestre family metadata en sidebar

## Risks

### Risk 1: deduplicar demasiado agresivo
Podría colapsar geometría que no debería unificarse.

**Mitigation:**
- empezar con duplicados exactos primero
- near-identical solo con thresholds conservadores

### Risk 2: romper trazabilidad visual
Si se ocultan demasiado los secundarios, parece que “faltan líneas”.

**Mitigation:**
- no borrarlos del inspector
- marcarlos como secundarios explícitos

### Risk 3: afectar openings hosting
Si se reasigna mal la canonicidad, openings podrían quedar hosteadas sobre la boundary equivocada.

**Mitigation:**
- no reescribir hosting fuerte todavía
- mantener mapping y validar regresión

## Expected Next Step After This Slice
Una vez que el graph tenga menos ruido redundante, el próximo salto correcto pasa a ser:

1. **stronger opening hosting** sobre boundaries más canónicas
2. después **mutability / constraints**
3. recién después **site-aware mutation contract**

## Bottom Line
Hoy el cuello de botella ya no es “ver más líneas”.
Es:

# transformar un graph redundante en un graph canónico

Ese es el trabajo correcto para que el plano deje de verse como fragmentos sueltos y se acerque a un ensamblaje realmente rearmable.
