# Plan Maestro de Reentrenado Full

## Objetivo

Llevar Point.ai desde el estado actual de:

- pipeline `v2` funcional
- conversion parcial/full de datasets
- smoke fine-tune en GPU
- UI con selector `baseline` / `experimental`

al estado de:

- dataset unificado serio
- trainer full reproducible
- checkpoints versionados
- benchmark real sobre planos Pointe
- criterio claro para promover un modelo nuevo a default

Este plan no asume atajos. Cada tramo cierra con:

- compilacion o import check
- tests automaticos
- smoke funcional
- criterio de aceptacion

## Estado de partida

Ya existe:

- `training/convert_resplan.py`
- `training/convert_floorplancad.py`
- `training/export_lmdb.py`
- `training/prepare_resplan_training.py`
- `training/prepare_floorplancad_training.py`
- `training/prepare_combined_training.py`
- `training/smoke_finetune.py`
- `backend/cubicasa_inference.py`
- `data/training/checkpoints/cubicasa_experimental.pt`

Limitaciones actuales:

- `training/smoke_finetune.py` no es trainer full
- el checkpoint `experimental` esta entrenado muy poco
- falta `convert_cubicasa.py`
- falta benchmark Pointe serio
- falta cierre formal del dataset full combinado

## Principios de ejecucion

1. No correr entrenamientos largos si el dataset no esta auditado.
2. No promover un checkpoint solo porque "parece mejor" en una imagen.
3. Cada fase debe dejar artefactos reproducibles en disco.
4. Cada cambio de training debe tener test o smoke especifico.
5. Cada experimento debe ser comparable contra baseline.

## Fase 0 - Congelar baseline y entorno

### Objetivo

Definir el punto cero antes de tocar el trainer full.

### Micro-pasos

1. Registrar baseline actual:
   - pesos: `floorplan-research/CubiCasa5k/model_best_val_loss_var.pkl`
   - inferencia actual: `backend/cubicasa_inference.py`
   - UI actual con selector de variante
2. Registrar entorno:
   - version de `torch`
   - disponibilidad CUDA
   - GPU detectada
3. Crear carpeta de experimentos:
   - `data/training/experiments/`
   - subcarpetas por experimento
4. Crear formato comun de metadatos de experimento:
   - `experiment_id`
   - datasets usados
   - seed
   - lr
   - batch_size
   - image_size
   - steps/epochs
   - checkpoint_base

### Gates

- `.\.venv\Scripts\python -m pytest -q`
- `npm --prefix frontend run build`
- smoke de inferencia `baseline`

### Criterio de aceptacion

- baseline congelado y documentado
- carpeta de experimentos creada
- metadata minima definida

## Fase 1 - Cerrar pipeline de datos

### Objetivo

Dejar un dataset unificado, auditable y entrenable en escala.

### Fase 1A - Convertir CubiCasa al formato comun

#### Implementacion

Crear:

- `training/convert_cubicasa.py`
- `tests/test_cubicasa_conversion.py`

#### Micro-pasos

1. Inspeccionar formato real de CubiCasa:
   - PNG
   - SVG
   - labels
   - corners/openings
2. Mapear a contrato comun usado por:
   - `convert_resplan.py`
   - `convert_floorplancad.py`
3. Exportar:
   - `image.png`
   - `label.npy` o formato comprimido final
   - `heatmaps.json`
   - `meta.json`
   - `preview.png`
4. Generar manifiesto:
   - `cubicasa_manifest.jsonl`

#### Gates

- test unitario de conversion
- smoke:
  - `python -m training.convert_cubicasa --limit 10`

#### Criterio de aceptacion

- 10 muestras convertidas sin error
- previews coherentes
- manifiesto valido

### Fase 1B - Replantear formato de almacenamiento

#### Objetivo

Evitar que el layout full quede inflado o lento por serializar tensores float innecesarios.

#### Implementacion

1. Revisar `training/export_lmdb.py`
2. Definir formato final:
   - imagen como PNG
   - labels en `uint8` o `npz`
   - heatmaps comprimidos
3. Ajustar loader de training si hace falta
4. Mantener compatibilidad con el loader real de CubiCasa o encapsular uno nuevo

#### Gates

- `tests/test_training_export.py`
- nuevo test de tamaño y carga
- smoke de lectura de 100 muestras

#### Criterio de aceptacion

- carga correcta
- menor costo de I/O
- layout reproducible

### Fase 1C - Conversion full por dataset

#### Objetivo

Tener conversion full real de los tres repos.

#### Micro-pasos

1. `ResPlan full`
2. `FloorPlanCAD full`
3. `CubiCasa full`
4. generar `manifest` por dataset
5. generar `summary.json` por dataset

#### Gates

- conteos por dataset
- auditoria de archivos faltantes
- test de lectura aleatoria de muestras

#### Criterio de aceptacion

- manifests completos
- sin corrupcion silenciosa
- sin rutas rotas

### Fase 1D - Auditoria visual y estadistica

#### Objetivo

No entrenar a ciegas.

#### Micro-pasos

1. Generar 100 previews aleatorias por dataset
2. Medir distribucion de clases:
   - walls
   - openings
   - rooms
3. Detectar muestras degeneradas:
   - sin walls
   - sin rooms
   - solo background
4. Emitir reporte:
   - `data/training/audits/*.json`

#### Gates

- script de auditoria corre end-to-end
- reporte generado para los 3 datasets

#### Criterio de aceptacion

- dataset apto para training
- muestras malas identificadas o filtradas

## Fase 2 - Indice unificado y splits finales

### Objetivo

Construir el dataset full combinado con splits reproducibles.

### Micro-pasos

1. Generar manifiesto unificado
2. Crear splits reproducibles:
   - `train`
   - `val`
   - `test`
3. Balancear por dataset
4. Mantener un holdout Pointe aparte, no mezclado
5. Exportar layout final:
   - `combined_ready_full`

### Gates

- `tests/test_training_index.py`
- test de no overlap entre splits
- conteos finales por dataset y split

### Criterio de aceptacion

- split estable por seed
- mezcla controlada
- layout final listo para trainer

## Fase 3 - Trainer full

### Objetivo

Reemplazar el smoke trainer por un trainer serio, reanudable y medible.

### Implementacion

Crear:

- `training/finetune.py`
- `tests/test_finetune_config.py`
- `tests/test_finetune_smoke.py`

### Requisitos minimos

- resume from checkpoint
- AMP
- grad accumulation
- TensorBoard
- checkpoints periodicos
- best checkpoint por metrica
- config serializada a JSON
- seed fija
- soporte multi-dataset sampler

### Micro-pasos

1. portar la carga del modelo actual
2. definir config dataclass o parser robusto
3. implementar loop de train
4. implementar loop de val
5. guardar:
   - `latest.pt`
   - `best_val_loss.pt`
   - `best_pointe.pt`
6. guardar logs:
   - loss por step
   - loss por epoch
   - metricas por dataset

### Gates

- import check del trainer
- smoke de 2 steps
- smoke de resume desde checkpoint
- `pytest` especifico del trainer

### Criterio de aceptacion

- trainer reanuda correctamente
- checkpoints legibles por inferencia o por conversor de checkpoints
- logs consistentes

## Fase 4 - Matriz de experimentos

### Objetivo

No mezclar todo de una sin control.

### Experimentos obligatorios

1. `exp_001_baseline_eval`
   - solo evaluacion del baseline
2. `exp_002_cubicasa_resplan`
   - CubiCasa + ResPlan
3. `exp_003_cubicasa_resplan_floorplancad`
   - mezcla de los tres
4. `exp_004_reweighted`
   - mezcla completa con rebalanceo

### Metadatos por experimento

- config
- dataset counts
- seed
- tiempo total
- GPU usada
- checkpoint base
- metricas de salida

### Gates

- cada experimento debe correr smoke de 10-20 steps antes del full run
- si smoke falla, no se lanza corrida larga

### Criterio de aceptacion

- al menos 1 checkpoint usable por experimento
- resultados comparables entre si

## Fase 5 - Benchmark Pointe serio

### Objetivo

Tener una verdad de negocio, no solo loss.

### Micro-pasos

1. Armar dataset Pointe holdout:
   - 20-50 planos
2. Etiquetado minimo:
   - shell exterior
   - muros principales
   - openings clave
3. Definir metricas:
   - wall IoU
   - exterior wall recall
   - opening precision
   - opening recall
   - `needs_review` rate
   - tiempo por inferencia
4. Crear runner:
   - `training/eval_pointe.py` o extender `backend/benchmark.py`

### Gates

- benchmark corre completo
- resultados guardados por experimento

### Criterio de aceptacion

- existe ranking real baseline vs experimental
- se puede decidir con datos si promover o descartar un modelo

## Fase 6 - Promocion de checkpoint

### Objetivo

Solo pasar a default un modelo que gane de verdad.

### Regla

Un checkpoint nuevo solo pasa a `baseline` si:

- mejora metricas Pointe
- no empeora fuerte tiempos de inferencia
- no empeora openings de forma significativa
- pasa smoke de UI + DXF

### Micro-pasos

1. copiar checkpoint ganador a ruta estable
2. registrar metadata
3. actualizar selector o default si corresponde
4. correr regression suite

### Gates

- `pytest -q`
- `npm --prefix frontend run build`
- smoke de `POST /api/v2/generate-dxf`

### Criterio de aceptacion

- modelo promovido de forma reproducible

## Plan de compilacion y test por tramo

### Cada vez que se toque conversion de dataset

- `.\.venv\Scripts\python -m pytest tests/test_*conversion*.py -q`
- smoke del script tocado

### Cada vez que se toque export/layout

- `.\.venv\Scripts\python -m pytest tests/test_training_export.py tests/test_training_index.py -q`

### Cada vez que se toque trainer

- smoke `2-10 steps`
- test de resume
- validar checkpoint generado

### Cada vez que se toque inferencia

- `.\.venv\Scripts\python -m pytest tests/test_cubicasa_adapter.py tests/test_v2_api.py tests/test_worker_client.py tests/test_worker_server.py -q`

### Gate general al cerrar cada fase

- `.\.venv\Scripts\python -m pytest -q`
- `npm --prefix frontend run build`

## Riesgos y mitigaciones

### Riesgo 1 - Dataset full demasiado pesado

Mitigacion:

- auditar tamaño antes de correr full
- usar formato comprimido
- no picklear floats sin necesidad

### Riesgo 2 - FloorPlanCAD meta ruido

Mitigacion:

- experimento separado con y sin FloorPlanCAD
- no convertirlo en dependencia obligatoria del primer checkpoint serio

### Riesgo 3 - Trainer inestable

Mitigacion:

- smoke corto primero
- AMP
- grad clipping
- resume y checkpoints

### Riesgo 4 - Modelo aprende datasets sinteticos y no Pointe

Mitigacion:

- benchmark Pointe temprano
- holdout real
- criterio de promocion estricto

## Orden de ejecucion recomendado

1. `convert_cubicasa.py`
2. rediseño del export/layout
3. conversion full de los 3 datasets
4. auditoria visual y estadistica
5. `finetune.py`
6. `exp_002`
7. benchmark Pointe
8. `exp_003`
9. benchmark Pointe
10. promocion o descarte

## Definicion de exito

El plan se considera cumplido cuando:

- existe dataset full unificado
- existe trainer full reproducible
- existe benchmark Pointe real
- existe al menos un checkpoint que gane al baseline en metricas reales
- ese checkpoint puede correrse desde la UI sin romper tiempos ni DXF
