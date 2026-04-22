# Point.ai MVP — Floor Plan Catalog + Site Plan Fit

## Objetivo

Construir un MVP **chat-first** donde el usuario pueda decir:

> “Necesito hacer entrar una **Seminole 2000** en este **site plan**”

y el sistema haga:

1. analizar el **site plan** subido
2. traer un **floor plan curado** del catálogo
3. ubicarlo **1:1** dentro del lote / buildable area
4. generar un **Reconstruction Plan** textual
5. dejar que el usuario edite ese plan en el chat
6. ejecutar la reconstrucción geométrica aprobada
7. devolver un **DXF final**

## Decisión de producto

El MVP **NO** va a detectar floor plans crudos en runtime cada vez.

El MVP va a trabajar así:

- **Floor plans**: curados offline una vez
- **Site plans**: analizados online en runtime
- **Chat**: interfaz principal
- **DXF**: formato operativo del pipeline

## Por qué este approach

Resolver `N site plans x N floor plans` como archivos crudos en cada corrida mete demasiado ruido:

- layers inconsistentes
- blocks explotados
- cotas confundidas con geometría
- labels partidos
- distinto estilo de drafting por archivo

Si el floor plan ya existe y ya está dibujado al 100%, lo correcto es convertirlo a un **objeto rico y confiable** una sola vez.

---

## Alcance del MVP

### Input

- **1 site plan DXF** subido por el usuario
- **1 floor plan** elegido del catálogo curado

### Output

- preview inline dentro del chat:
  - site plan
  - buildable area
  - floor plan overlay 1:1
  - overflow real
  - rooms y medidas relevantes
- **Reconstruction Plan** textual editable
- **DXF final** con:
  - floor plan reconstruido
  - site plan con el floor plan adaptado ubicado dentro

---

## Arquitectura del MVP

### 1. Floor Plan Catalog (offline)

Cada floor plan se cura una vez y se guarda como modelo estructurado.

#### Datos mínimos por floor plan

##### Identidad
- `floor_plan_id`
- `name`
- `source_dxf`
- `canonical_unit`
- `version`

##### Geometría global
- `footprint_polygon`
- `footprint_bbox`
- `gross_area`
- `overall_width`
- `overall_height`

##### Rooms
Por cada room:
- `room_id`
- `name`
- `polygon`
- `bbox`
- `centroid`
- `width`
- `height`
- `area`
- `measurement_source`
- `adjacent_rooms[]`
- `is_exterior_touching`
- `is_wet_zone`
- `is_core`
- `mutability`
- `min_width`
- `min_height`
- `min_area`

##### Walls
Por cada wall:
- `wall_id`
- `start`
- `end`
- `orientation`
- `length`
- `is_exterior`
- `is_structural_unknown`
- `left_room`
- `right_room`
- `movable`
- `hosted_openings[]`

##### Openings
- `opening_id`
- `type`
- `host_wall_id`
- `position_on_wall`
- `width`
- `belongs_to_rooms[]`

##### Fixtures / blocks relevantes
Solo los que aportan semántica útil para reconstrucción:
- toilet
- sink
- tub
- kitchen fixtures
- cabinets relevantes

### 2. Site Plan Analyzer (runtime)

Del site plan nuevo queremos extraer:

- `property_boundary`
- `buildable_polygon`
- `setbacks`
- `street/front`
- taper / curvaturas / ángulos
- `confidence`

### 3. Overlay + Fit Engine

Con el floor plan catalogado y el site plan runtime:

- normaliza a la misma unidad
- registra el floor plan 1:1
- genera overlay
- calcula invade / no invade
- detecta dónde y cuánto no entra

### 4. Reconstruction Planner

Si no entra, el sistema genera un plan textual editable.

#### Formato objetivo

```txt
Plan de reconstrucción propuesto para SEMINOLE2000 en 158 DAWSON STREET

Objetivo:
- Hacer entrar el footprint dentro del buildable polygon sin tocar master suite ni baños.

Diagnóstico:
- Invasión principal en lateral derecho: 18 in
- Invasión secundaria en frente curvo: 9 in

Cambios propuestos:
1. Reducir GARAGE 12 in desde pared este
2. Reducir FLEX ROOM 8 in desde pared norte
3. Reacomodar pasillo central 4 in
4. Mantener MASTER BEDROOM, MASTER BATH y KITCHEN sin cambios

Impacto esperado:
- Área total nueva: XXXX
- GARAGE: pasa de X a Y
- FLEX ROOM: pasa de X a Y
- Buildable fit esperado: OK

Validaciones requeridas:
- Sin overlaps
- Sin gaps
- Puertas reancladas
- Cotas recalculadas
```

### 5. Geometry Reconstruction Engine

La reconstrucción **NO** se apoya en pixels ni en mover líneas DXF a ciegas.

Se apoya en un modelo:

- topológico
- paramétrico
- room-first
- wall-first

#### Reglas del motor

- mover walls conocidas por `wall_id`
- actualizar la pared compartida del vecino si aplica
- recalcular corners y closures
- reanclar openings
- recalcular polygons de rooms
- recalcular footprint
- recalcular cotas y áreas
- regenerar DXF válido

### 6. Validation Gate

Una reconstrucción solo vive si pasa:

#### Geometría
- rooms cerrados
- sin gaps
- sin overlaps
- footprint coherente

#### Semántica
- cada room conserva identidad
- ownership de walls consistente
- openings siguen hosteados correctamente

#### Medición
- cotas consistentes
- áreas razonables
- sumatoria de rooms coherente

#### Fit
- footprint dentro de buildable polygon
- overflow = 0 o aceptable

---

## UX del MVP

### Flujo

1. usuario abre un thread
2. sube el site plan DXF
3. escribe:
   - “Necesito hacer entrar una Seminole 2000 en este site plan”
4. Point:
   - analiza el site plan
   - selecciona el floor plan del catálogo
   - muestra el overlay inline
   - produce el Reconstruction Plan
5. usuario puede responder:
   - “no toques garage”
   - “podés achicar living”
   - “master y baños intocables”
6. Point recalcula el plan textual
7. cuando el usuario aprueba:
   - Point ejecuta
   - devuelve preview final
   - exporta DXF

---

## Criterio técnico más importante

El paso más hard del pipeline NO es detectar rooms.

El paso más hard es:

- reconstruir geometría válida
- reconectar walls
- mantener ownership
- recalcular cotas correctas
- exportar un DXF serio

Por eso el catálogo curado es la base del sistema.

Si el floor plan entra al motor como dibujo crudo, la probabilidad de reconstrucción correcta baja muchísimo.

Si entra como modelo curado con rooms, walls, openings y constraints, la probabilidad sube radicalmente.

---

## Formato operativo recomendado

- **DWG**: master editable si el estudio lo necesita
- **DXF**: formato operativo del pipeline Point.ai

Motivo:
- parseo directo
- menos dependencia externa
- mejor testabilidad
- mejor depuración

---

## Auditoría inicial de floor plans del catálogo

### Archivos auditados

- `D:\PointAIData\PLANS\originalFloorPlans\SEMINOLE2000.dxf`
- `D:\PointAIData\PLANS\originalFloorPlans\SANTA-BARBARA.dxf`

### Hallazgos iniciales

#### SEMINOLE2000.dxf
- unidad canónica: `inch`
- medidas floor: `468 x 792 in`
- rooms extraídos hoy: **14**
- nombres de rooms bien separados:
  - `KITCHEN`
  - `BEDROOM 2`
  - `BEDROOM 3`
  - `LIVING ROOM`
  - `MSTR. BEDROOM`
  - `MASTER BATH`
  - `GARAGE`
  - etc.
- usa layers claramente aprovechables:
  - `WALLS`
  - `ROOM LBLS`
  - `DIMS`
  - `DOORS`
  - `WINS`
- conclusion inicial:
  - **buen candidato para curado automatizado con poca intervención**

#### SANTA-BARBARA.dxf
- unidad canónica: `inch`
- medidas floor: `1633.66 x 1080 in` por geometría actual
- rooms extraídos hoy: **4**
- problema importante:
  - el extractor actual fusiona muchos labels en un room gigante
- labels detectados muestran naming consistente pero partido:
  - `MASTER`
  - `BEDROOM`
  - `MSTR.`
  - `BATH`
  - `DINING`
  - `LIVING ROOM`
  - `BEDROOM 3`
  - `BEDROOM 2`
  - etc.
- blocks útiles presentes:
  - `TOILET1`
  - `WASH_DRY`
  - `STOVE`
  - `SINK`
  - `DISHWASHER`
  - `TUB`
- conclusion inicial:
  - **necesita curado más fuerte de labels / room segmentation antes de entrar al catálogo**

### Conclusión de la comparación

Los dos floor plans **sí vienen de una familia CAD parecida**, pero no igual de limpia.

#### Lo que comparten
- DXF
- unidad operativa usable
- layers de walls / dims / room labels
- blocks/fixtures detectables

#### Lo que NO comparten todavía de manera segura
- calidad de segmentación de rooms
- consistencia de labels multi-token
- footprint confiable sin curado adicional

### Decisión práctica

Para el MVP:

1. **curar primero SEMINOLE2000**
2. usarlo como floor plan de referencia del catálogo
3. después curar `SANTA-BARBARA` con reglas mejores de labels y partition

### Salidas reales ya generadas

- `D:\PointAIData\PLANS\catalog\seminole-2000.json`
  - `readiness.status = ready_for_catalog`
  - 14 rooms curados hoy
  - rooms ya incluyen `polygon`, `bbox` y `centroid`
- `D:\PointAIData\PLANS\catalog\santa-barbara.json`
  - `readiness.status = needs_manual_review`
  - issue: `Aggregate room labels suggest unresolved room segmentation.`
  - rooms ya incluyen `polygon`, `bbox` y `centroid`

---

## Temporary topology inspector

Uso temporal de curacion/debug para validar `SEMINOLE2000` antes de avanzar al executor geometrico.

### Workflow

1. Regenerar la fixture real desde el catalogo curado:

   ```bash
   .\.venv\Scripts\python.exe scripts/export_seminole_topology_fixture.py D:\PointAIData\PLANS\catalog\seminole-2000.json --output frontend/src/features/catalogInspector/catalogInspector.fixture.json
   ```

2. Abrir la app React con el flag temporal:
   - `?debug=seminole-topology`

3. Usar la screen para inspeccionar:
   - room identity (`room_id`)
   - category inference
   - adjacency
   - exterior-touch
   - topology issues
   - raw CAD wall traces
   - wall graph support states (`exact`, `snapped`, `unsupported`)
   - focus queue de paredes problematicas

4. Para seguir progreso real, mirar estas metricas del header:
   - `Shared exact`
   - `Shared snapped`
   - `Shared unsupported`

5. Para atacar problemas de a uno, usar `Focus mode`:
   - `Shared`
   - `Exact`
   - `Snapped`
   - `Unsupported`

6. Navegar con:
   - `Previous issue`
   - `Next issue`

7. Leer el canvas asi:
   - gris = traza cruda real del CAD
   - verde/cian = pared con soporte fuerte
   - ambar = pared snappeada a traza real
   - rojo = pared todavia sin soporte real

### Proposito

Esta pantalla es intencionalmente temporal y removible. Existe para verificar que la topologia derivada del floor plan sea coherente antes de invertir en el motor de reconstruccion geometrica.

## Próximos pasos

### Paso 1
Definir el contrato exacto del `FloorPlanCatalogEntry`.

### Paso 2
Construir el extractor/curador offline para:
- `SEMINOLE2000`
- `SANTA-BARBARA`

### Paso 3
Guardar el resultado curado en una base canónica.

### Paso 4
Conectar el chat para:
- elegir floor plan del catálogo
- subir site plan
- generar overlay + Reconstruction Plan

### Paso 5
Construir el primer geometry executor acotado.
