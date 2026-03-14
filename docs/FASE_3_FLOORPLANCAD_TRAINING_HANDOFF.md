# Fase 3 FloorPlanCAD + Training Handoff

## Estado cerrado

- `training/convert_floorplancad.py`
  - Convierte `FloorPlanCAD` desde pares `root-level .png + .svg`.
  - Mapea:
    - `WALL`, `COLUMN` -> wall mask
    - `WINDOW` + detalles `semantic-id=33` -> window icon
    - `DOOR_FIRE` + arcos door-like en layer `0` -> door icon
  - Reconstruye:
    - `room_mask` genérico por interior inferido desde muros
    - `icon_mask`
    - heatmaps de muros y openings
- `training/prepare_floorplancad_training.py`
  - Hace conversión + splits + LMDB final de `FloorPlanCAD`
- `training/prepare_combined_training.py`
  - Mezcla múltiples manifests en un único layout compatible con CubiCasa
- `training/smoke_finetune.py`
  - Hace un paso real de fine-tune (`forward + backward + optimizer.step`) sobre un layout LMDB
  - Usa `cuda` si está disponible

## Validación ejecutada

- `.\.venv\Scripts\python -m pytest -q`
  - Resultado: `50 passed, 7 warnings`
- `.\.venv\Scripts\python -m training.prepare_floorplancad_training --limit 5 --output data\training\floorplancad_ready_smoke --preview-limit 2`
  - Resultado:
    - `5` muestras convertidas
    - `train=3`, `val=1`, `test=1`
- `.\.venv\Scripts\python -m training.prepare_combined_training data\training\resplan_ready_smoke\converted\resplan_manifest.jsonl data\training\floorplancad_ready_smoke\converted\floorplancad_manifest.jsonl --output data\training\combined_ready_smoke`
  - Resultado:
    - layout combinado con `15` entradas
    - `train=11`, `val=2`, `test=2`
- `.\.venv\Scripts\python -m training.smoke_finetune --data-path data\training\combined_ready_smoke\cubi_layout --steps 1 --batch-size 1 --image-size 64 --output data\training\smoke_finetune_combined.json`
  - Resultado:
    - `device = cuda`
    - `cuda_available = true`
    - `steps_run = 1`

## Runtime GPU

- `.venv` ahora usa:
  - `torch 2.10.0+cu128`
  - `torchvision 0.25.0+cu128`
  - `torchaudio 2.10.0+cu128`
- Verificación hecha:
  - `torch.cuda.is_available() == True`
  - GPU detectada: `NVIDIA GeForce RTX 4090 Laptop GPU`

## Artefactos útiles

- `data/training/floorplancad_ready_smoke/`
- `data/training/combined_ready_smoke/`
- `data/training/smoke_finetune_combined.json`
- `data/training/floorplancad_svg_report_smoke.json`

## Lo próximo

1. Escalar `FloorPlanCAD` de `limit 5` a conversión grande o completa.
2. Regenerar layout combinado con `ResPlan + FloorPlanCAD` ya ampliado.
3. Lanzar fine-tune largo:
   - más steps
   - checkpoints
   - logging
4. Medir contra baseline sobre holdout real.
