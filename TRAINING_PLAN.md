# Training Plan — PointAI Fine-Tune

## Objetivo
Fine-tunear CubiCasa5k para detectar mejor paredes, puertas y ventanas
en planos residenciales americanos (estilo Pointe Homes), sin degradar
el rendimiento en el baseline original.

## Por qué fallaron los intentos anteriores

| Intento | LR | Épocas | Dataset | Resultado |
|---------|-----|--------|---------|-----------|
| Run 1 | 1e-4 | 20 | 221 americanos | Catastrophic forgetting — empeoró |
| Run 2 | 1e-5 | 5 | 221 americanos | Poco aprendizaje — no mejoró |

**Causa raíz:** Entrenar solo con datos americanos hace que el modelo
"olvide" lo que aprendió de los 5,000 planos europeos de CubiCasa.
La solución es mezclar ambos datasets en cada batch.

---

## Plan definitivo

### Paso 1 — Preparar dataset CubiCasa5k (europeos)
Convertir los SVG originales de CubiCasa al formato label.npy + heatmaps.json.

```
floorplan-research/CubiCasa5k/cubicasa5k/cubicasa5k/
├── high_quality/        # 992 planos
├── colorful/            # 276 planos
└── high_quality_architectural/  # ~3,700 planos
```

Script a crear: `training/convert_cubicasa5k.py`
Output: `C:/PointAIData/training/converted/cubicasa_manifest.jsonl`

### Paso 2 — Labelear 5,000 planos americanos con Gemini
```powershell
python -m training.auto_label_gemini --dataset D:/PointAIData/dataset --start 222 --end 5000
```
Costo estimado: ~$215 USD (4,779 imágenes × $0.045)
Tiempo estimado: ~4 horas

### Paso 3 — Convertir labels americanos
```powershell
python -m training.label_converter --dataset D:/PointAIData/dataset --start 1 --end 5000
```

### Paso 4 — Preparar dataset americano
```powershell
python -m training.prepare_pointai_training --dataset D:/PointAIData/dataset --output C:/PointAIData/training
```
Output: `C:/PointAIData/training/converted/pointai_manifest.jsonl`

### Paso 5 — Combinar ambos datasets
```powershell
python -m training.prepare_curated_training `
  C:/PointAIData/training/converted/pointai_manifest.jsonl `
  C:/PointAIData/training/converted/cubicasa_manifest.jsonl `
  --output C:/PointAIData/training/combined `
  --min-score 30
```

### Paso 6 — Entrenamiento final
```powershell
python -u -m training.finetune `
  --data-path C:/PointAIData/training/combined/cubi_layout `
  --run-dir C:/PointAIData/training/runs_final `
  --epochs 50 `
  --device cuda `
  --learning-rate 0.00002 `
  --batch-size 8 `
  --log-every-steps 50
```

---

## Hiperparámetros (avalados por papers 2024)

| Parámetro | Valor | Fuente |
|-----------|-------|--------|
| Learning rate | 2e-5 | arXiv 2402.08096 — mix-cd paper |
| Épocas | 50 | arXiv 2402.19340 — multi-dataset segmentation |
| Batch composition | ~80% americanos + 20% CubiCasa | arXiv 2403.05175 — continual learning survey |
| Optimizer | AdamW | Mejor para continual learning que Adam |
| Batch size | 8 | Limitado por VRAM RTX 4090 laptop (16GB) |

## Composición del batch (clave anti-forgetting)
Con 5,000 americanos + 5,000 CubiCasa el split natural es 50/50.
El prepare_curated_training mezcla aleatoriamente — cada batch
verá planos europeos Y americanos, previniendo el olvido.

---

## Referencias
- CubiCasa5K paper: arXiv 1904.01920
- Catastrophic forgetting / rehearsal: arXiv 2402.08096
- Multi-dataset segmentation: arXiv 2402.19340
- Continual learning survey: arXiv 2403.05175

---

## Estado actual

- [x] 5,018 planos americanos scrapeados (D:/PointAIData/dataset)
- [x] 221 planos labelados con Gemini
- [x] Pipeline de entrenamiento funcionando (prepare + finetune)
- [x] CubiCasa5k dataset disponible localmente
- [ ] Convertir CubiCasa5k SVG → label.npy
- [ ] Labelear 4,779 planos restantes con Gemini
- [ ] Entrenamiento final combinado 50 épocas
