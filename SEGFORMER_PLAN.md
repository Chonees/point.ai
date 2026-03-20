# Plan: SegFormer para Floor Plan Segmentation

## Contexto

CubiCasa baseline detecta ~75% de paredes en planos americanos. Intentamos fine-tunear CubiCasa con labels de Gemini pero:
- El formato SVG vs pixel causó conflicto
- Más datos de Gemini empeoraron rooms (83% → 80.5%)
- `get_polygons()` se cuelga con modelos fine-tuneados
- Las labels de Gemini detectan menos paredes (6.6% vs 9.4% de CubiCasa)

SegFormer es un modelo moderno (2021) que entrena 100% con pixels, sin conflicto de formatos. Además, **eliminamos get_polygons()** — extraemos paredes directamente del mask con CV, resolviendo el timeout.

## Approach

### Labels: Merge 2 canales → 1 canal (14 clases)

CubiCasa usa 2 canales. SegFormer necesita 1. Merge simple:
- Clases 0-11: room classes (background, outdoor, wall, kitchen, living, bedroom, bath, entry, railing, storage, garage, room)
- Clase 12: window (del icon channel)
- Clase 13: door (del icon channel)
- Icons 3-10 (closet, toilet, etc.) se ignoran — no los usamos para DXF

### Post-procesamiento: Mask → Walls (sin get_polygons)

En vez de `get_polygons()` (que se cuelga), extraemos directamente:
1. Wall mask (clase==2) → morphología → skeletonize → HoughLinesP → segmentos H/V
2. Door mask (clase==13) → connected components → blobs → ubicación
3. Window mask (clase==12) → connected components → blobs → ubicación
4. Alimentar al mismo `structure_postprocess.py` que ya tenemos

### Training: nvidia/mit-b2 en RTX 4090 laptop (16GB)

- Modelo: `nvidia/mit-b2` (25M params)
- Input: 512x512
- Batch: 4 con AMP (FP16) — ~12GB VRAM
- Epochs: 30 con early stopping
- LR: 6e-5 con warmup + cosine decay
- Loss: CrossEntropyLoss con class weights (wall=3x, door/window=5x)
- Sin LMDB — lee PNG+NPY directo del disco

## Pasos de implementación

### Paso 1: Convertir labels (nuevo: `training/convert_labels_segformer.py`)
- Lee cada `label.npy` (2, H, W)
- Merge a single channel (H, W) con 14 clases
- Guarda `label_merged.npy` al lado (no pisa original)
- Imprime estadísticas de distribución de clases

### Paso 2: Dataset PyTorch (nuevo: `training/segformer_dataset.py`)
- Lee `image.png` + `label_merged.npy` directo del disco
- Resize a 512x512 (INTER_AREA para imágenes, INTER_NEAREST para labels)
- Augmentations: flip H/V, rotación 90/180/270, color jitter
- Split 85/15 train/val
- NO usa LMDB ni FloorplanSVG

### Paso 3: Script de training (nuevo: `training/finetune_segformer.py`)
- Carga `nvidia/mit-b2` con `ignore_mismatched_sizes=True`
- CrossEntropyLoss con weights (wall=3, door=5, window=5, background=0.1)
- AdamW + cosine scheduler + warmup 500 steps
- AMP habilitado
- Checkpoints: latest.pt, best_val.pt, best_inference.pt
- Métricas: loss, val_loss, mIoU, wall_iou, door_iou, window_iou

### Paso 4: Inference (nuevo: `backend/segformer_inference.py`)
- Misma API que `cubicasa_inference.py`
- Carga modelo, preprocess con ImageNet norm
- Forward → argmax → mask de clases
- `_mask_to_structure()`: extrae walls/doors/windows del mask con CV
- Retorna mismo formato dict que cubicasa (walls, openings, structure_meta)

### Paso 5: Integración backend
- `worker_client.py`: agregar `segformer_local` backend
- `app.py`: agregar routing `elif model_variant == "segformer"`

### Paso 6: Frontend
- `App.tsx`: agregar "SegFormer" al selector de modelo

## Archivos a crear
- `training/convert_labels_segformer.py`
- `training/segformer_dataset.py`
- `training/finetune_segformer.py`
- `backend/segformer_inference.py`

## Archivos a modificar
- `backend/worker_client.py` (~15 líneas)
- `backend/app.py` (~5 líneas)
- `frontend/src/App.tsx` (~5 líneas)

## Dependencias nuevas
- `transformers>=4.35.0`
- `datasets` (opcional, para métricas)

## VRAM estimado (RTX 4090 laptop 16GB)
- Training: ~12GB con batch 4 + AMP → 4GB headroom
- Inference: ~2GB → corre junto con otros modelos

## Verificación
1. Correr `convert_labels_segformer.py` → verificar que label_merged.npy tiene 14 clases
2. Entrenar 30 épocas → verificar que wall_iou sube
3. Correr inference en 5 planos americanos → comparar visualmente con CubiCasa baseline
4. Probar en UI → verificar que no hay timeout (sin get_polygons)

## Orden de ejecución
```
Paso 1 (labels) → Paso 2 (dataset) → Paso 3 (training) → esperar
                                                              ↓
Paso 4 (inference) → Paso 5 (backend) → Paso 6 (frontend) → probar
```
Pasos 4-6 se pueden hacer en paralelo con 1-3 usando pesos dummy.
