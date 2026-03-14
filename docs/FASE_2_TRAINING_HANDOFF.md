# Fase 2 Training Handoff

## Estado cerrado

- `training/export_lmdb.py`
  - Exporta manifests convertidos a un layout compatible con CubiCasa:
    - `cubi_lmdb/`
    - `train.txt`
    - `val.txt`
    - `test.txt`
    - `layout_summary.json`
- `training/prepare_resplan_training.py`
  - Ejecuta pipeline completo:
    - conversión `ResPlan`
    - splits reproducibles
    - export LMDB final
- La exportación guarda samples compatibles con `FloorplanSVG(format='lmdb')`:
  - `image`: `torch.FloatTensor` CHW en rango `0..255`
  - `label`: `torch.FloatTensor` con shape `(2,H,W)`
  - `heatmaps`: dict de 21 canales
  - `folder`: `sample_id`
  - `scale`

## Compatibilidad validada

- `lmdb` instalado en `.venv`
- `svgpathtools` instalado en `.venv`
- Test fuerte:
  - `tests/test_training_export.py`
  - valida que el LMDB exportado se abra con el loader real de CubiCasa
  - valida que `DictToTensor()` produzca el tensor de `23` canales esperado para training

## Smoke real ejecutado

Comando:

```powershell
.\.venv\Scripts\python -m training.prepare_resplan_training --limit 10 --output data\training\resplan_ready_smoke --preview-limit 2
```

Resultado:

- `10` muestras convertidas
- splits:
  - `train = 8`
  - `val = 1`
  - `test = 1`
- LMDB escrito en:
  - `data/training/resplan_ready_smoke/cubi_layout/cubi_lmdb`

Nota:
- Para splits de una sola muestra, el export duplica la línea en `val.txt` o `test.txt` porque el loader original de CubiCasa rompe con `np.genfromtxt` escalar. Eso queda registrado en `layout_summary.json` como `duplicated_singleton_splits`.

## Validación total

- `.\.venv\Scripts\python -m pytest -q`
  - Resultado: `46 passed, 7 warnings`

## Qué falta en la próxima fase

1. Lanzar el primer fine-tune real con `CubiCasa5k + ResPlan`.
2. Decidir si:
   - se mezcla el LMDB de CubiCasa con el nuevo layout en un índice común
   - o se entrena primero solo con `ResPlan` como smoke de entrenamiento
3. Medir baseline vs fine-tuned en un holdout real.
4. Seguir con parser más profundo de `FloorPlanCAD` solo si suma valor al primer ciclo.
