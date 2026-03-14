# Fase 4 — Handoff Completo

> **Contexto**: Point.ai convierte imágenes de floor plans en DWG profesionales para Pointe Homes.
> **Estado**: Fases 1-3 completadas. 24 tests green. Pipeline funcional con inferencia heurística local.
> **Objetivo Fase 4**: Desplegar worker GPU real con modelo de segmentación, validar contra planos Pointe de producción, y cerrar el MVP end-to-end con escala real.

---

## 1. Qué es Point.ai (contexto completo)

Pointe Homes tiene >90 modelos residenciales. Hoy un arquitecto dibuja cada plano a mano en AutoCAD LT 2026. Point.ai automatiza eso: recibe una imagen de un floor plan y produce un DWG con layers, muros, puertas y ventanas al estilo Pointe Homes.

### Decisiones de arquitectura ya tomadas

- **Claude queda fuera del core geométrico**. No extrae coordenadas. Se reserva para reconciliar ambigüedad post-MVP.
- **El contrato canónico es `walls[] + openings[]`**, no `rooms[]`. Los rooms son un adapter legacy.
- **Dos servicios**: Point.ai API (backend Python/FastAPI) + Worker GPU (Docker/CUDA/PyTorch).
- **Modelo base elegido**: CubiCasa5k/floortrans. Simsys aporta lógica de postproceso. FloorplanTransformation aporta reconstrucción corner→wall→opening.
- **El renderer CAD nuevo** genera DXF desde estructura canónica. El legacy (`generator.py` con `rooms[]`) sigue intacto.

### Convenciones CAD Pointe Homes

- 1 unidad AutoCAD = 1 pulgada (INSUNITS=2)
- Espesor de muro = 4" (doble línea paralela)
- Layers: `WALLS`(color 7, lw 60), `DOORS`(color 157, lw 9), `WINS`(color 121, lw -3)
- Puertas: hueco en pared + 2 líneas paralelas (slab 1.5") + arc swing 90°
- Ventanas: hueco + 3 líneas paralelas + end caps + sill exterior
- Garage: línea discontinua en el hueco
- Sliding: dos paneles offset con flechas

---

## 2. Estado actual del codebase

### Inventario de archivos (4,265 líneas totales)

```
backend/
├── app.py                    # FastAPI — rutas legacy + v2
├── artifacts.py              # Guardado de preview PNG + structure JSON por corrida
├── benchmark.py              # Runner de benchmark contra dataset Pointe
├── claude.py                 # Claude Vision (analyze_image, generate_plan) — NO se usa en v2
├── generator.py              # Generador legacy: rooms[] → DXF (NO tocar)
├── image_utils.py            # decode/encode imagen base64 ↔ numpy
├── inference_client.py       # Inferencia heurística local: imagen → walls/openings crudos
├── models.py                 # Pydantic: request/response models para FastAPI
├── plan_parser.py            # Parser canónico: rooms[] o structure{} → estructura normalizada
├── prompts.py                # Prompts de Claude (legacy)
├── structural_generator.py   # Generador v2: structure{} → DXF con estilo Pointe
├── structure_postprocess.py  # Snap + merge + junctions L/T/X + clasificación ext/int + anchoring
├── validation.py             # Validación legacy de rooms[] (reglas de Claude)
├── worker_client.py          # Router: heuristic_local | remote → infer_structure()
├── worker_contract.py        # Contrato del worker GPU: request, response, errores tipados
└── components/
    ├── layers.py             # setup_doc() — layers Pointe Homes en ezdxf
    ├── primitives.py         # add_line, add_arc, add_text, add_hatch_rect
    ├── walls.py              # draw_wall_h/v, split_segments, collect_walls, dedup_walls
    ├── doors.py              # draw_door, draw_garage_door, draw_sliding_door
    ├── windows.py            # draw_window_h/v
    └── labels.py             # draw_label

tests/
├── helpers.py                   # build_synthetic_structure_image() — imagen 220×160 con muros+openings
├── test_plan_parser.py          # legacy rooms → canonical, inferred image → canonical
├── test_inference_client.py     # heuristic local detecta walls/openings
├── test_v2_api.py               # parse-structure y generate-dxf por plan/image, descarga preview+DXF
├── test_worker_contract.py      # validación request/response, errores tipados
├── test_worker_client.py        # routing heuristic/remote, error handling
├── test_junction_graph.py       # L/T/X detection, postprocess metrics
├── test_benchmark.py            # dataset loading, case execution, comparison
└── test_structural_generator.py # DXF con normal/garage/sliding doors
```

### Endpoints actuales

| Endpoint | Input | Output | Pipeline |
|----------|-------|--------|----------|
| `POST /api/analyze` | `image` (b64) | `description` (text) | Claude Vision |
| `POST /api/generate` | `prompt`, `image?` | `dxf_url`, `plan` | Claude → rooms → legacy DXF |
| `POST /api/v2/parse-structure` | `plan?`, `structure?`, `image?`, `scale_hint?` | `structure`, `preview_url`, `quality_metrics`, `review_flags` | Inferencia → postproceso → canonical |
| `POST /api/v2/generate-dxf` | `plan?`, `structure?`, `image?`, `scale_hint?` | `dxf_url`, `preview_url`, `structure`, `scale_status`, `quality_metrics` | Inferencia → postproceso → DXF |

### Flujo v2 completo (imagen → DXF)

```
imagen b64
  → worker_client.infer_structure()         # elige backend por env var
    → inference_client._infer_with_heuristics()  # o worker remoto
  → plan_parser.parse_structure_payload(structure=...)
    → structure_postprocess.postprocess_structure()
      → _normalize_wall_geometry()
      → _snap_walls()                        # cluster + snap a grid
      → _snap_to_intersections()             # snap endpoints a ejes perpendiculares
      → _merge_walls()                       # colineares con gap < 48px
      → build_junction_graph()               # L/T/X entre H y V walls
      → _classify_walls_with_junctions()     # exterior si coverage >= 70%
      → _anchor_openings()                   # nearest wall, offset, side, swing
  → structural_generator.generate()          # ezdxf → DXF con layers Pointe
  → artifacts.save_structure_artifacts()     # preview PNG + structure JSON
```

### Variables de entorno relevantes

| Variable | Default | Efecto |
|----------|---------|--------|
| `POINTAI_INFERENCE_BACKEND` | `heuristic_local` | `heuristic_local` o `remote` |
| `POINTAI_WORKER_URL` | `http://localhost:8100` | URL del worker GPU |
| `ANTHROPIC_API_KEY` | — | Solo para endpoints legacy (Claude) |

### Contrato del worker GPU (ya definido en `worker_contract.py`)

**Request** `POST /infer/structure`:
```json
{
  "image": "<base64>",
  "options": {}
}
```

**Response** (éxito):
```json
{
  "model_name": "floortrans-v1",
  "model_version": "0.1.0",
  "image_size": {"width": 512, "height": 512},
  "walls": [
    {
      "polyline": [{"x": 10, "y": 10}, {"x": 200, "y": 10}],
      "thickness": 4.0,
      "is_exterior": true,
      "confidence": 0.92,
      "orientation": "horizontal"
    }
  ],
  "openings": [
    {
      "kind": "door",
      "position": {"x": 80, "y": 10},
      "span": 30,
      "orientation": "horizontal",
      "confidence": 0.88,
      "swing": "up",
      "door_type": "normal"
    }
  ],
  "masks_available": true,
  "debug_overlay_b64": "<base64 PNG overlay o null>",
  "inference_time_ms": 120.5
}
```

**Response** (error):
```json
{
  "error": {
    "code": "INFERENCE_FAILED",
    "message": "GPU OOM on 4096x4096 image"
  }
}
```

Códigos de error: `INVALID_IMAGE`, `MODEL_NOT_LOADED`, `INFERENCE_FAILED`, `POSTPROCESS_FAILED`.

### Tests (24 passed)

```powershell
.\.venv\Scripts\python -m pytest -q
```

---

## 3. Qué resolvió cada fase

### Fase 1 — Contrato v2 y renderer estructural
- Contrato canónico `walls[] + openings[] + structure_meta`.
- `plan_parser.py`: adapta `rooms[]` legacy → canonical.
- `structural_generator.py`: renderiza DXF desde canonical.
- Endpoints `v2` en `app.py`.

### Fase 2 — Inferencia local y postproceso
- `inference_client.py`: imagen → masks OpenCV → walls/openings crudos.
- `structure_postprocess.py`: snap, merge, clasificación ext/int, anchoring.
- `artifacts.py`: preview PNG + structure JSON por corrida.
- Pipeline completo `image → structure → DXF` funcional con heurísticas.

### Fase 3 — Worker client, junctions, benchmark
- `worker_client.py`: routing `heuristic_local | remote` por env var.
- `worker_contract.py`: contrato tipado del worker GPU con validación.
- Junction graph `L/T/X` en postproceso.
- Snap por intersección (endpoints → ejes perpendiculares).
- Clasificación exterior mejorada (coverage 70% del bounding box).
- `draw_garage_door()` y `draw_sliding_door()` en renderer.
- `benchmark.py`: runner de benchmark con comparación contra ground truth.
- Manejo de `WorkerError` → HTTP 502 en endpoints v2.

---

## 4. Qué debe resolver la Fase 4

La Fase 4 cierra la brecha entre "funciona con imágenes sintéticas" y "funciona con planos Pointe reales". Tiene 5 bloques de trabajo.

---

### Bloque A — Worker GPU real

**Objetivo**: un contenedor Docker que carga un modelo de segmentación de floor plans y responde a `POST /infer/structure` con el contrato definido en `worker_contract.py`.

**Decisiones ya tomadas**:
- Docker + Linux CUDA
- PyTorch
- Modelo: CubiCasa5k/floortrans como baseline
- Carga única del modelo al iniciar el contenedor (no cold-start por request)
- Si falla, error tipado — nunca output parcial silencioso

**Qué hay que construir**:

1. **Directorio `worker/`** en la raíz del proyecto:
   ```
   worker/
   ├── Dockerfile
   ├── requirements.txt
   ├── app.py              # FastAPI con POST /infer/structure
   ├── model_loader.py     # Carga CubiCasa/floortrans al inicio
   ├── inference.py        # Forward pass: imagen → masks
   └── postprocess.py      # Masks → walls[] + openings[] (vectorización)
   ```

2. **`worker/app.py`**: FastAPI que expone `POST /infer/structure`. Debe:
   - Validar la imagen (decodificar b64, verificar formato).
   - Pasar al modelo.
   - Postprocesar masks → polylines de muros y bounding boxes de openings.
   - Devolver el JSON que `validate_worker_response()` en `worker_contract.py` acepta.
   - Devolver errores con los códigos definidos: `INVALID_IMAGE`, `MODEL_NOT_LOADED`, `INFERENCE_FAILED`, `POSTPROCESS_FAILED`.

3. **`worker/postprocess.py`**: la pieza más crítica. Toma las masks de segmentación y produce:
   - **Walls**: skeleton/centerline → polylines axis-aligned de 2 puntos + thickness.
   - **Openings**: regiones de door/window → bounding box + kind + position + span.
   - **Orientación**: horizontal/vertical por aspecto del segmento.
   - **Confianza**: score del modelo por píxel promediado por segmento.
   - Debe filtrar texto, muebles, cotas — todo lo que no sea muro/opening.
   - Referencia de lógica a portar: `Simsys/analysis/wall_analysis.py` (thickness, orientation, junctions, centerlines), `Simsys/analysis/door_analysis.py` (swing heurístico), `Simsys/image_processing/mask_processing.py` (limpieza de masks).

4. **Integración con backend**: ya está hecha. Solo hay que:
   - Setear `POINTAI_INFERENCE_BACKEND=remote` y `POINTAI_WORKER_URL=http://worker:8100`.
   - El `worker_client.py` ya llama al endpoint y valida la respuesta.
   - El `plan_parser.py` ya pasa la estructura por el postproceso completo.

**Validación del bloque**:
- `docker build -t pointai-worker worker/` funciona.
- `docker run --gpus all -p 8100:8100 pointai-worker` levanta.
- `curl -X POST http://localhost:8100/infer/structure -d '{"image":"..."}' ` devuelve JSON válido.
- Los tests existentes siguen pasando (no se toca el backend, solo se agrega el worker).

---

### Bloque B — Dataset benchmark Pointe

**Objetivo**: tener un set de planos reales para medir si el pipeline funciona.

**Estructura esperada** (ya implementada en `benchmark.py`):
```
data/benchmark/
├── seminole_2000/
│   ├── input.png          # scan o screenshot del plano
│   └── expected.json      # ground truth (walls + openings)
├── bayshore_1800/
│   ├── input.png
│   └── expected.json
├── ...
```

**Recolección**:
- 20 planos Pointe reales: 5 limpios, 10 medianos, 5 complejos (escaleras, deck, nichos, quiebres).
- Imágenes limpias (sin rotación, buen contraste, resolución >= 1024px en el lado mayor).
- Ground truth: puede ser anotado a mano o extraído de los DWG existentes con `extract_floorplan.py`.

**Formato de `expected.json`**:
```json
{
  "walls": [
    {
      "id": "w1",
      "orientation": "horizontal",
      "polyline": [{"x": 100, "y": 50}, {"x": 500, "y": 50}],
      "thickness": 4,
      "is_exterior": true
    }
  ],
  "openings": [
    {
      "id": "o1",
      "kind": "door",
      "position": {"x": 200, "y": 50},
      "span": 32
    }
  ]
}
```

**Ejecución**:
```powershell
# Con heurístico local (sin GPU):
python -m backend.benchmark --dataset data/benchmark --output data/benchmark_results

# Con worker GPU:
$env:POINTAI_INFERENCE_BACKEND="remote"
$env:POINTAI_WORKER_URL="http://localhost:8100"
python -m backend.benchmark --dataset data/benchmark --output data/benchmark_results --backend remote
```

---

### Bloque C — Métricas de aceptación del MVP

**Objetivo**: que `benchmark.py` no solo compare conteos sino que mida calidad real.

**Métricas a agregar en `compare_structures()`**:

1. **Wall footprint IoU**: rasterizar muros predichos y esperados en una grilla, calcular intersección/unión.
   - Threshold MVP: `>= 0.85` en planos limpios.

2. **Exterior wall recall**: % de muros exteriores esperados que fueron detectados.
   - Threshold MVP: `>= 0.90`.

3. **Door/window precision**: % de openings predichos que existen en el ground truth (±tolerancia de posición).
   - Threshold MVP: `>= 0.80`.

4. **Door/window recall**: % de openings esperados que fueron detectados.
   - Threshold MVP: `>= 0.75`.

5. **False positive rate**: muros predichos que no corresponden a ningún muro real (muebles, texto, cotas dibujados como muro).
   - Threshold MVP: `0` en los 5 planos limpios.

**Implementación sugerida**: agregar estas funciones en `benchmark.py`, extender `compare_structures()`. La rasterización se puede hacer con OpenCV (`cv2.fillPoly` sobre un canvas para cada set de muros, luego IoU = bitwise_and / bitwise_or).

---

### Bloque D — Postproceso para planos reales

El postproceso actual (`structure_postprocess.py`) funciona bien para muros axis-aligned sobre imágenes sintéticas. Con planos reales van a aparecer problemas nuevos. Hay que preparar el postproceso para eso.

**Problemas esperados y soluciones**:

1. **Texto/cotas detectados como muro**: el modelo puede segmentar texto grueso o líneas de cota como wall.
   - Solución: filtrar segmentos por aspect ratio. Un muro real tiene largo >> ancho. Un carácter de texto es cuadrado o más alto que ancho. Agregar `_filter_text_artifacts()` después del merge.
   - Regla: si `length < 3 * thickness` y no tiene junctions, descartar.

2. **Muebles detectados como muro**: rectángulos de closets, counters, bathtubs.
   - Solución: si un segmento forma un rectángulo cerrado pequeño (área < threshold) sin conexión al wall graph principal, descartarlo.

3. **Muros diagonales**: si el modelo los emite, hoy `_normalize_wall_geometry()` tira error.
   - Solución mínima: proyectar al eje más cercano (H o V) si el ángulo es < 15°. Si es diagonal real (>15°), marcar con `confidence` baja y `review_flag`, no renderizar en DXF pero guardar en preview.

4. **Swing de puerta**: hoy se infiere solo por `side` del muro. Con planos reales hay que detectar el arco.
   - Solución: si el modelo devuelve un campo `swing`, usarlo. Si no, mantener la heurística actual de side. Post-MVP se puede agregar detección geométrica del arco.

5. **Paredes de espesor variable**: muros exteriores suelen ser más gruesos que interiores.
   - Ya soportado: `thickness` viene por muro. Solo asegurar que el modelo lo infiera bien.

---

### Bloque E — Escala y unidades (Fase 5 de ARQUITECTURA.md, incluida aquí)

**Objetivo**: que el DXF salga en pulgadas reales cuando hay información de escala disponible.

**Estado actual**:
- `structure_meta.unit` puede ser `"pixel"` o `"inch"`.
- `structure_meta.scale_status` puede ser `"unverified"` o `"calibrated"`.
- Si viene `scale_hint` en el request, el parser setea `unit="inch"` y `scale_status="calibrated"`.
- Pero **no se aplica** ninguna conversión de coordenadas. Las coordenadas salen tal cual.

**Qué falta**:

1. **Aplicar `scale_hint`**: en `plan_parser._normalize_structure()`, si `scale_hint` está presente, multiplicar todas las coordenadas y spans por `scale_hint` antes del postproceso.
   - `scale_hint` = pulgadas por pixel. Ejemplo: si la imagen tiene 100px de ancho y el plano real tiene 500", `scale_hint = 5.0`.

2. **Auto-detección de escala** (post-MVP): si el modelo detecta una cota con valor numérico (ej: "24'-0"") y puede medir la distancia correspondiente en píxeles, calcular `scale_hint` automáticamente.

3. **DXF sin escala**: si no hay `scale_hint`, el DXF sale en coordenadas de pixel con `scale_status="unverified"`. Esto ya funciona. No inventar medidas falsas.

**Implementación sugerida**:
```python
# En plan_parser._normalize_structure(), después de normalizar walls/openings:
if scale_hint is not None:
    walls = _apply_scale(walls, scale_hint)
    openings = _apply_scale_openings(openings, scale_hint)
```

---

## 5. Orden de ejecución recomendado

```
Semana 1:
  1. Construir worker/ (Dockerfile + app.py + model_loader.py)
  2. Hacer que el worker levante y responda con un mock JSON hardcodeado
  3. Verificar que worker_client.py conecta y los 24 tests siguen green

Semana 2:
  4. Integrar modelo CubiCasa/floortrans real en el worker
  5. Construir worker/postprocess.py (masks → walls/openings)
  6. Probar con 3-5 planos Pointe limpios, verificar output visual

Semana 3:
  7. Armar dataset benchmark (20 planos con ground truth)
  8. Agregar métricas IoU y precision/recall en benchmark.py
  9. Correr benchmark, iterar postproceso hasta alcanzar thresholds

Semana 4:
  10. Agregar filtros anti-texto y anti-mueble en postproceso
  11. Implementar scale_hint real en plan_parser
  12. Test final end-to-end: imagen real → DXF → abrir en AutoCAD → validar
```

---

## 6. Criterio de aceptación de la Fase 4

| Criterio | Threshold |
|----------|-----------|
| Worker GPU respondiendo `POST /infer/structure` | modelo real cargado |
| Tests existentes | 24/24 green |
| Tests nuevos contra mock del worker | >= 3 tests nuevos green |
| Dataset benchmark | >= 10 planos Pointe reales |
| Wall footprint IoU (planos limpios) | >= 0.85 |
| Exterior wall recall | >= 0.90 |
| Door/window precision | >= 0.80 |
| Door/window recall | >= 0.75 |
| Muebles/texto como muros (planos limpios) | 0 |
| Tiempo p50 end-to-end (GPU 4070 o equiv) | <= 15s |
| DXF abre limpio en AutoCAD LT 2026 | sin errores |
| Layers correctos en DXF | WALLS, DOORS, WINS presentes |
| Artefactos por corrida de benchmark | structure JSON + preview PNG + quality JSON |

---

## 7. Archivos que NO se deben tocar

- `backend/generator.py` — legacy, funciona, no romper.
- `backend/claude.py` — solo para endpoints legacy.
- `backend/prompts.py` — solo para endpoints legacy.
- `backend/validation.py` — solo para pipeline legacy rooms[].
- `backend/components/labels.py` — solo para pipeline legacy.
- `backend/extract_floorplan.py` — utilidad de extracción, no forma parte del pipeline.

## 8. Dependencias del proyecto

```
# Backend (ya instaladas en .venv)
fastapi, uvicorn, anthropic, ezdxf, opencv-python-headless, numpy, python-dotenv, pydantic, httpx

# Worker (nuevo, hay que crear requirements.txt)
fastapi, uvicorn, torch, torchvision, opencv-python-headless, numpy, Pillow
```

---

## 9. Cómo correr todo

```powershell
# Backend
cd Point.ai
.\.venv\Scripts\python -m uvicorn backend.app:app --reload

# Tests
.\.venv\Scripts\python -m pytest -q

# Benchmark (heurístico)
.\.venv\Scripts\python -m backend.benchmark --dataset data/benchmark --output data/benchmark_results

# Worker GPU (cuando esté listo)
cd worker
docker build -t pointai-worker .
docker run --gpus all -p 8100:8100 pointai-worker

# Backend apuntando al worker
$env:POINTAI_INFERENCE_BACKEND="remote"
$env:POINTAI_WORKER_URL="http://localhost:8100"
.\.venv\Scripts\python -m uvicorn backend.app:app --reload
```
