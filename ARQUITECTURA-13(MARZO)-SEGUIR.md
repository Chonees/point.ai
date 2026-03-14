# Point.ai - Estado Real de la Branch `staging` al 13/14 de Marzo

## Resumen ejecutivo

La branch `staging` ya no esta en etapa de idea. Quedo convertido un pipeline real, testeado y utilizable para:

- recibir imagenes en `v2`
- inferir estructura
- normalizar a contrato canonico
- generar preview y DXF
- preparar datasets de entrenamiento
- correr fine-tune en GPU
- comparar desde la UI un modelo `baseline` contra un modelo `experimental`

Todavia no esta demostrado que el modelo experimental dibuje mejor que el baseline en planos reales de Pointe. Lo que si esta resuelto es la infraestructura para probarlo de punta a punta.

## Estado de la branch

- Branch actual: `staging`
- Estado: dirty, con cambios staged y unstaged
- `git diff --cached --stat`:
  - `138 files changed`
  - `17218 insertions`
  - `722 deletions`
- `git diff --stat` adicional sobre trabajo no staged del ultimo tramo:
  - `10 files changed`
  - `244 insertions`
  - `32 deletions`

Conclusion: la branch concentra varias fases implementadas en serio. No es un cambio chico ni un experimento aislado.

## Lo que se logro hoy

### 1. Se estabilizo el pipeline `v2` de imagen a DXF

Se dejo operativo el camino:

`image -> worker_client -> inferencia -> parse_structure_payload -> quality_gate -> preview -> DXF`

Archivos clave:

- `backend/app.py`
- `backend/worker_client.py`
- `backend/worker_server.py`
- `backend/plan_parser.py`
- `backend/structure_postprocess.py`
- `backend/structural_generator.py`
- `backend/quality_gate.py`

Impacto real:

- la API ya no depende de `torch` en import-time
- la inferencia no esta pegada directo al endpoint
- el resultado `v2` ya vuelve con `structure`, `quality_metrics`, `review_flags`, `needs_review`, `preview_url`
- los casos malos ya pueden degradar a revision en vez de salir como falso exito

### 2. Se integro CubiCasa5k como backend usable

Se cableo `backend/cubicasa_inference.py` con lazy imports, carga de pesos y conversion a contrato `walls[] + openings[] + structure_meta`.

Tambien se corrigio el adaptador para no perder puertas y ventanas que CubiCasa reporta como `icon`.

Impacto real:

- `cubicasa_local` ya es backend valido
- se puede alternar con `heuristic_local`
- el worker entiende ambos

### 3. Se agrego observabilidad, artefactos y benchmark base

Se incorporaron:

- `backend/artifacts.py`
- `backend/observability.py`
- `backend/benchmark.py`
- `backend/worker_contract.py`

Tambien se generaron casos base de benchmark en `data/benchmark/`.

Impacto real:

- se guardan artefactos por corrida
- hay contrato formal entre backend y worker
- se puede inspeccionar preview, structure y salida DXF
- existe una base de benchmark reproducible, aunque todavia no alcanza para decir que el sistema esta listo para produccion

### 4. Se construyo el pipeline de conversion de datasets

Se implemento la capa de training en `training/`:

- `training/common.py`
- `training/convert_resplan.py`
- `training/create_unified_index.py`
- `training/export_lmdb.py`
- `training/inspect_floorplancad.py`
- `training/inspect_floorplancad_svg.py`
- `training/convert_floorplancad.py`
- `training/prepare_resplan_training.py`
- `training/prepare_floorplancad_training.py`
- `training/prepare_combined_training.py`
- `training/smoke_finetune.py`

Impacto real:

- `ResPlan` se convierte a layout compatible con CubiCasa
- `FloorPlanCAD` ya no esta bloqueado por formato desconocido
- se pueden generar splits reproducibles `train/val/test`
- se puede exportar todo a LMDB compatible con el loader real de CubiCasa

### 5. Se verifico GPU real y se corrio entrenamiento

La `.venv` quedo preparada para entrenamiento con CUDA.

Validado:

- `torch 2.10.0+cu128`
- `torch.cuda.is_available() == True`
- GPU detectada: `NVIDIA GeForce RTX 4090 Laptop GPU`

Ademas se corrio fine-tune real de smoke en GPU y se genero un checkpoint experimental:

- `data/training/checkpoints/cubicasa_experimental.pt`
- resumen en `data/training/checkpoints/cubicasa_experimental_summary.json`

Resumen actual del checkpoint:

- `steps_run = 40`
- `last_loss = 4.550766468048096`
- `device = cuda`
- `dataset_size = 11`

### 6. La UI quedo lista para comparar variantes

Se modifico `frontend/src/App.tsx` para que el upload panel permita elegir:

- `Baseline`
- `Experimental`

Tambien se propago `model_variant` por backend:

- `backend/models.py`
- `backend/app.py`
- `backend/worker_client.py`
- `backend/worker_server.py`
- `backend/cubicasa_inference.py`

Impacto real:

- desde la UI ya se puede subir una misma imagen y comparar dos salidas
- el backend carga pesos distintos segun variante
- el resultado reporta la variante usada en `quality_metrics.model_variant`

## Validacion ejecutada

### Suite de tests

Resultado final actual:

- `.\.venv\Scripts\python -m pytest -q`
- `53 passed, 7 warnings`

Cobertura relevante agregada:

- `tests/test_v2_api.py`
- `tests/test_worker_client.py`
- `tests/test_worker_server.py`
- `tests/test_worker_contract.py`
- `tests/test_cubicasa_adapter.py`
- `tests/test_quality_gate.py`
- `tests/test_plan_parser.py`
- `tests/test_structural_generator.py`
- `tests/test_benchmark.py`
- `tests/test_resplan_conversion.py`
- `tests/test_training_export.py`
- `tests/test_training_index.py`
- `tests/test_floorplancad_inspector.py`
- `tests/test_floorplancad_svg_inspector.py`
- `tests/test_floorplancad_conversion.py`
- `tests/test_prepare_combined_training.py`

### Build de frontend

Validado:

- `npm --prefix frontend run build`

Resultado:

- build OK

### Validaciones funcionales reales

Se validaron estos caminos:

- `parse_structure_payload` con plan legacy
- `POST /api/v2/parse-structure`
- `POST /api/v2/generate-dxf`
- descarga de DXF
- preview overlay
- inferencia CubiCasa local
- carga del checkpoint experimental
- llamada end-to-end con `model_variant="experimental"`

## Artefactos utiles que ya existen

### Handoffs

- `docs/FASE_1_DATASET_HANDOFF.md`
- `docs/FASE_2_HANDOFF.md`
- `docs/FASE_2_TRAINING_HANDOFF.md`
- `docs/FASE_3_HANDOFF.md`
- `docs/FASE_3_FLOORPLANCAD_TRAINING_HANDOFF.md`
- `docs/FASE_4_HANDOFF.md`
- `docs/PLAN_REENTRENADO_FULL.md`

### Datasets convertidos y smokes

- `data/training/resplan_pilot_smoke/`
- `data/training/resplan_ready_smoke/`
- `data/training/floorplancad_ready_smoke/`
- `data/training/combined_ready_smoke/`
- `data/training/floorplancad_samples/`
- `data/training/floorplancad_svg_report_smoke.json`
- `data/training/floorplancad_inspection_smoke.json`

### Avance real de `FloorPlanCAD full`

Estado actual observado:

- `data/training/floorplancad_ready_full/converted/floorplancad/`
- directorios de muestras convertidas detectadas: `5842`

Esto significa que el trabajo pesado de conversion ya avanzo bastante, pero todavia no esta cerrado del todo como layout final consolidado para entrenamiento largo.

### Checkpoints y resumentes de training

- `data/training/smoke_finetune_combined.json`
- `data/training/smoke_finetune_combined_5steps.json`
- `data/training/checkpoints/cubicasa_experimental.pt`
- `data/training/checkpoints/cubicasa_experimental_summary.json`

## Analisis honesto de lo conseguido

### Lo que si quedo resuelto

- la arquitectura `v2` ya existe y corre
- la API y la UI ya no dependen de humo
- ya hay worker contract, artifacts, benchmark y quality gate
- ya hay pipeline de conversion para datasets
- ya hay entrenamiento en GPU funcionando
- ya existe un checkpoint experimental cargable por inferencia
- ya se puede comparar desde la UI baseline vs experimental

### Lo que NO esta resuelto todavia

- no hay evidencia seria de que `experimental` sea mejor que `baseline`
- el checkpoint experimental actual es corto y sirve para probar el plumbing, no para declararlo modelo ganador
- falta benchmark real con planos Pointe etiquetados
- falta entrenamiento largo con dataset mas grande
- falta cerrar `FloorPlanCAD full` en layout final listo para training sin pasos manuales pendientes
- falta medir precision/recall reales para walls, openings y shell exterior

### Conclusion tecnica

Hoy el cuello de botella ya no es la infraestructura. El cuello de botella paso a ser la calidad del modelo y la calidad del benchmark.

En otras palabras:

- antes faltaba sistema
- ahora ya hay sistema
- lo que falta es demostrar que el modelo entrenado mejora el caso real

## Estado de cada fase

### Fase 0 - Estabilizacion del pipeline

Estado: cerrada

Hecho:

- lazy import de runtime pesado
- worker routing
- quality gate
- benchmark base
- tests del flujo `v2`

### Fase 1 - Conversion de datasets

Estado: mayormente resuelta

Hecho:

- ResPlan convertido
- FloorPlanCAD inspeccionado y convertido
- export LMDB
- combinacion de manifests

Pendiente:

- cerrar conversion completa consolidada de `FloorPlanCAD full`

### Fase 2 - Fine-tune del modelo

Estado: arrancada, no cerrada

Hecho:

- entorno CUDA listo
- smoke fine-tune en GPU
- checkpoint experimental guardado

Pendiente:

- entrenamiento largo serio
- checkpoints multiples
- comparacion contra baseline en holdout real

### Fase 3 - Postproceso geometrico serio

Estado: parcial

Hecho:

- parse y postprocess canonico
- merge/snap/junction graph base
- quality gate

Pendiente:

- thickness mas robusto
- mejor centerline extraction
- mejor reconstruccion de openings
- integracion de ideas utiles de Simsys

### Fase 4 - Escala y unidades

Estado: pendiente

Hecho:

- existe `scale_hint`
- existe `scale_status`

Pendiente:

- OCR de cotas
- heuristica de puertas estandar
- trazabilidad completa de origen de escala

### Fase 5 - Benchmark Pointe + produccion

Estado: pendiente

Pendiente:

- dataset Pointe real etiquetado
- benchmark serio sobre casos reales
- metricas minimas para promocionar un modelo a default
- separacion backend web / worker GPU para despliegue final

## Lo que falta ahora, en orden correcto

### Prioridad 1

Lanzar fine-tune largo real sobre layout combinado mas grande.

Objetivo:

- sacar un checkpoint experimental serio
- no seguir comparando contra un smoke de 40 steps

### Prioridad 2

Cerrar `FloorPlanCAD full` como dataset consolidado.

Objetivo:

- manifiesto final
- splits finales
- layout LMDB final

### Prioridad 3

Armar benchmark de verdad sobre planos Pointe.

Objetivo:

- medir si el modelo experimental mejora algo real
- decidir si `experimental` puede pasar a `baseline`

### Prioridad 4

Reforzar postproceso.

Objetivo:

- evitar muros demasiado fragmentados
- mejorar anchoring de openings
- mejorar shell exterior

## Estado final de hoy

El trabajo del dia dejo a Point.ai en un punto muy distinto al inicial:

- antes no habia un flujo serio de entrenamiento ni comparacion
- ahora hay pipeline `v2`, datasets convertidos, training en GPU, checkpoint experimental y UI lista para comparar variantes

Lo que falta ya no es "armar el sistema", sino "hacer que el modelo gane en casos reales y probarlo con evidencia".
