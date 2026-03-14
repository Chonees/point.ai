# Fase 1 Dataset Handoff

## Estado cerrado

- `training/convert_resplan.py`
  - Convierte planes de `ResPlan.pkl` a un formato de training intermedio.
  - Genera por muestra:
    - `image.png`
    - `label.npy` con shape `(2, H, W)`
    - `heatmaps.json` con 21 canales
    - `meta.json`
    - `preview.png` opcional
- `training/create_unified_index.py`
  - Construye splits reproducibles `train/val/test` a partir de manifests JSONL.
- `training/inspect_floorplancad.py`
  - Inspecciona los `tar.xz` sin extraer el dataset completo y deja un reporte JSON.
- `training/common.py`
  - Centraliza rasterización, normalización geométrica, serialización y previews.

## Validación ejecutada

- `.\.venv\Scripts\python -m pytest -q`
  - Resultado: `44 passed, 7 warnings`
- `.\.venv\Scripts\python -m training.convert_resplan --limit 2 --output data\training\resplan_pilot_smoke --preview-limit 1`
  - Resultado: conversión real de 2 muestras de `ResPlan`
- `.\.venv\Scripts\python -m training.inspect_floorplancad --scan-limit 200 --output data\training\floorplancad_inspection_smoke.json`
  - Resultado: reporte real sobre los 3 tarballs
- `.\.venv\Scripts\python -m training.create_unified_index data\training\resplan_pilot_smoke\resplan_manifest.jsonl --output data\training\unified_index_smoke`
  - Resultado: splits reproducibles generados

## Hallazgos reales

- `ResPlan` ya es utilizable para el primer ciclo.
  - Tiene geometrías estructurales claras y se deja rasterizar bien.
- `FloorPlanCAD` sigue sin parser implementado.
  - En el muestreo de `200` miembros por archivo solo aparecieron entradas `coco_vis/*.png`.
  - No apareció metadata/anotación en esa primera inspección rápida.
  - Conclusión: no debe bloquear el primer fine-tune.

## Salida generada

- `data/training/resplan_pilot_smoke/`
- `data/training/floorplancad_inspection_smoke.json`
- `data/training/unified_index_smoke/`

## Próxima fase recomendada

1. Escalar `ResPlan` de piloto a conversión completa.
2. Definir el formato final para entrenamiento:
   - mantener el intermedio actual y luego escribir LMDB
   - o escribir LMDB directo con dependencia opcional
3. Hacer un parser más profundo de `FloorPlanCAD` antes de prometer que entra al primer fine-tune.
4. Lanzar el primer entrenamiento con `CubiCasa5k + ResPlan`, sin esperar `FloorPlanCAD`.
