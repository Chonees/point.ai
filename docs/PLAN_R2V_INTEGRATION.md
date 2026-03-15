# R2V Integration Plan

## Motivación

CubiCasa5k emite máscaras de píxeles (44 canales) que necesitan `structure_postprocess.py`
(500+ líneas de snap/merge/junction) para producir geometría CAD. El approach es frágil:
pequeños cambios en umbralización rompen walls, openings se anclan mal, paredes se fragmentan.

**Raster-to-Vector** (Liu et al., ICCV 2017) resuelve el mismo problema directamente:
la red neuronal detecta junctions, el IP solver (programación entera) los ensambla en
primitivos vectoriales consistentes. No hay post-proceso frágil.

| | CubiCasa5k | R2V (ICCV 2017) |
|---|---|---|
| Output | Máscaras de píxeles | Segmentos + bounding boxes |
| Post-proceso | 500 líneas frágil | IP solver integrado |
| Consistencia geométrica | Depende de umbralización | Garantizada |
| Dataset de train | Floor plans europeos | 100k floor plans producción (LIFULL) |
| Resolución interna | 768px (configurable) | 256×256 |
| Licencia | MIT | MIT |

## Arquitectura del pipeline R2V

```
Imagen (cualquier resolución)
         ↓
[Preprocess]
  BGR→RGB, resize 256×256
  normalizar [-0.5, +0.5], CHW tensor
         ↓
[DRN Model] (PyTorch)
  corner_pred: (H, W, NUM_WALL_CORNERS+8)  ← junction heatmaps (sigmoid)
  icon_pred:   (H, W, NUM_ICONS+2)         ← icon semantics (softmax)
  room_pred:   (H, W, NUM_ROOMS+2)         ← room semantics (softmax)
         ↓
[IP Solver] (PuLP — programación entera binaria)
  Variables: wall points, wall lines, door lines, icon rects, room labels
  Objetivo: maximizar confidence scores respetando:
    - consistencia de junctions
    - exclusión de conflictos
    - puertas deben estar en paredes
  → primitivos vectoriales garantizados consistentes
         ↓
[_r2v_to_contract()]
  escalar coords 256px → original
  flip Y (imagen: top-left) → (CAD: bottom-left)
  → WorkerContract {walls[], openings[]}
         ↓
[DXF Generator] (sin cambios)
  components/walls.py, doors.py, windows.py
```

## Setup requerido

```bash
# 1. Clonar R2V al lado de CubiCasa5k
cd /path/to/floorplan-research   # hermano del directorio Point.ai
git clone https://github.com/art-programmer/FloorplanTransformation.git

# 2. Instalar dependencias del IP solver
pip install pulp scikit-image

# 3. Descargar pesos pretrained
#    Google Drive ID: 1e5c7308fdoCMRv0w-XduWqyjYPV4JWHS
#    Colocar en: floorplan-research/FloorplanTransformation/pytorch/checkpoint/floorplan/checkpoint.pth
mkdir -p floorplan-research/FloorplanTransformation/pytorch/checkpoint/floorplan
# gdown 1e5c7308fdoCMRv0w-XduWqyjYPV4JWHS \
#   -O floorplan-research/FloorplanTransformation/pytorch/checkpoint/floorplan/checkpoint.pth

# 4. Verificar
python -c "from backend.r2v_inference import r2v_available; print(r2v_available())"
# → (True, None)   si todo está en su lugar
# → (False, "...")  con mensaje de qué falta si no
```

## Archivos modificados

| Archivo | Cambio |
|---|---|
| `backend/r2v_inference.py` | NUEVO — backend completo (lazy imports, cache, IP solver) |
| `backend/worker_client.py` | Routing `r2v_local` en `infer_structure` |
| `backend/app.py` | `model_variant='r2v'` → `backend='r2v_local'` en `_parse_v2_input` |
| `frontend/src/App.tsx` | Opción "R2V" reemplaza "Experimental" |
| `tests/test_worker_client.py` | `experimental` → `baseline` |
| `tests/test_worker_server.py` | `experimental` → `baseline` |
| `tests/test_v2_api.py` | `experimental` → `baseline` |
| `tests/test_finetune.py` | `experimental` → `baseline` |
| `training/smoke_finetune.py` | default `experimental` → `baseline` |

## Cómo probar la diferencia

### UI (recomendado)
1. `uvicorn backend.app:app --reload`
2. Abrir http://localhost:5173 → Upload Plan
3. Subir una imagen de floor plan de Pointe Homes
4. Seleccionar **Baseline** → Generate → anotar wall_count, opening_count, tiempo
5. Seleccionar **R2V** → Generate → comparar resultados
6. Ver estructura detectada en el overlay y en el DXF

### CLI
```bash
# Baseline (CubiCasa5k)
curl -s -X POST http://localhost:8000/api/v2/generate-dxf \
  -H "Content-Type: application/json" \
  -d "{\"image\": \"$(base64 -w0 mi_plano.png)\", \"model_variant\": \"baseline\"}" \
  | python -m json.tool | grep -A5 quality_metrics

# R2V
curl -s -X POST http://localhost:8000/api/v2/generate-dxf \
  -H "Content-Type: application/json" \
  -d "{\"image\": \"$(base64 -w0 mi_plano.png)\", \"model_variant\": \"r2v\"}" \
  | python -m json.tool | grep -A5 quality_metrics
```

### Variable de entorno (backend forzado)
```bash
POINTAI_INFERENCE_BACKEND=r2v_local uvicorn backend.app:app --reload
```

### Verificar disponibilidad sin iniciar servidor
```bash
python -c "from backend.r2v_inference import r2v_available; ready, msg = r2v_available(); print('OK' if ready else f'NOT READY: {msg}')"
```

## Próximos pasos

### Fine-tuning R2V en floor plans US residential
El modelo pretrained fue entrenado en floor plans japoneses (LIFULL). Para Pointe Homes:

1. **Convertir dataset** a formato R2V:
   - Label format: corner heatmaps `(H×W×NUM_WALL_CORNERS+8)` + icon maps + room maps
   - Adaptar `training/convert_cubicasa.py` → `training/convert_r2v.py`
2. **Adaptar pipeline de training**:
   - Nuevo `training/finetune_r2v.py` (diferente split de canales que CubiCasa 44ch)
   - Usar PyTorch oficial de R2V (`pytorch/train.py`)
3. **Fine-tunar en RTX 4090** con floor plans US:
   - Dataset: FloorPlanCAD (5842 converted) + Pointe Homes etiquetados
4. **Benchmark**:
   - R2V pretrained vs R2V fine-tuned vs CubiCasa baseline
   - Métricas: precision/recall de walls, openings, shell exterior

### Mejoras a `_r2v_to_contract()`
- Inferir `is_exterior` desde `wallLabels` del IP solver (label de habitación por lado de la pared)
- Mejorar detección de door swing (R2V da endpoints, no dirección de arco)
- Soporte para resolución > 256×256 (reentrenar con imagen más grande)
