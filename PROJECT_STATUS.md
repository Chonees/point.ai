# Point.ai — Estado Completo del Proyecto
**Última actualización: 20 de marzo 2026**

---

## Qué es Point.ai

Sistema AI para Pointe Homes (empresa con +90 modelos residenciales americanos): toma una imagen de floor plan y genera un archivo DXF profesional para AutoCAD LT 2026.

**Pipeline:**
```
Imagen floor plan → Modelo AI (segmentación) → Post-procesamiento (CV) → DXF → AutoCAD
```

---

## Cronología completa de lo que hicimos

### Fase 1: Scraping de datos
- **Qué:** Scrapeamos 5,018 imágenes de floor plans americanos de houseplans.com
- **Script:** `scripts/scrape_builder_plans.py` usando Playwright
- **Problemas:**
  - El scraper contaba páginas visitadas mal (guardaba plan pages como visited)
  - Target logic: `--target 5000` daba solo 2,500 a houseplans, necesitamos `--target 10000`
  - Se trababa por AJAX pagination
- **Resultado:** 5,018 imágenes en `D:\PointAIData\dataset\0001-5000\`
- **Costo:** $0 (solo tiempo)

### Fase 2: Labeling con Gemini
- **Qué:** Usamos Gemini Vision API (gemini-3.1-flash-image-preview) para pintar cada floor plan con colores semánticos
- **Script:** `training/auto_label_gemini.py`
- **Colores:** Wall=(32,37,45), Window=(69,142,255), Door=(214,116,47), Bedroom=(233,242,255), etc.
- **Problemas:**
  - API key inválida al principio (billing no linkeado)
  - Gemini se colgaba sin timeout → agregamos ThreadPoolExecutor con 90s timeout
  - Rate limit 429 RESOURCE_EXHAUSTED → retries con 60s wait
  - Algunas imágenes fallaban silenciosamente
- **Resultado:** 757 imágenes labeladas (0001-0757), cada una con `TRAIN ONE.png`
- **Costo:** ~$41 USD ($0.054 por imagen)
- **Pendiente:** 4,243 imágenes más (~$229 USD)

### Fase 3: Conversión de labels
- **Qué:** Convertir `TRAIN ONE.png` (colores) a `label.npy` (class IDs por pixel) + `heatmaps.json`
- **Script:** `training/label_converter.py`
- **Resultado:** 755 de 757 convertidos exitosamente (2 sin TRAIN ONE válido)

### Fase 4: Fine-tuning CubiCasa5k — FALLÓ

#### Intento 1: 221 labels, learning rate alto (0.0001)
- **Dataset:** 221 nuestros solos en LMDB
- **Resultado:** room_acc subió a 78.3% pero en la UI funcionaba PEOR que baseline
- **Problema:** Catastrophic forgetting — el modelo olvidó lo que CubiCasa sabía
- **Aprendizaje:** No se puede fine-tunear CubiCasa con pocos datos sin perder conocimiento

#### Intento 2: 221 labels, learning rate bajo (0.00001)
- **Dataset:** Mismos 221
- **Resultado:** room_acc solo 48.9% después de 5 épocas — no aprendió suficiente
- **Problema:** Learning rate demasiado bajo para tan pocos datos
- **Aprendizaje:** Con 221 imágenes no hay forma de mejorar el baseline

#### Intento 3: 146 nuestros + 4,203 CubiCasa (dataset combinado v1)
- **Qué:** Convertimos los 4,203 SVGs de CubiCasa a pixel labels y combinamos con 146 nuestros
- **Problema previo:** numpy version incompatibility — CubiCasa escrito para numpy 1.x, teníamos numpy 2.x. 99.6% de samples fallaban con "setting an array element with a sequence"
- **Fix:** Parchear la conversión para manejar arrays ragged
- **Resultado:** room_acc 83%, val_loss 3.34 — mejor en números
- **Pero en la UI:** `get_polygons()` se colgaba con timeout de 30s. Las predicciones del fine-tuned producían bordes difusos que el post-procesamiento no podía manejar
- **Resultado visual:** Peor que baseline, inventaba paredes donde no había

#### Intento 4: 755 nuestros + 4,203 CubiCasa (dataset combinado v2)
- **Resultado:** room_acc bajó a 80.5% (vs 83% con 146) — MÁS datos de Gemini EMPEORÓ rooms
- **Análisis cuantitativo de labels:**
  - Gemini: wall coverage 6.6%, border sharpness 245.8
  - CubiCasa SVG: wall coverage 9.4%, border sharpness 312.6
  - Gemini detecta MENOS paredes y con bordes MENOS nítidos
- **Conclusión definitiva:** Labels de Gemini tienen error SISTEMÁTICO, no aleatorio. Más datos no lo arreglan para CubiCasa.

#### Por qué falló todo con CubiCasa
- CubiCasa fue entrenado originalmente con SVGs vectoriales (precisión perfecta)
- Nosotros le dimos pixel labels (aproximados)
- Los dos formatos se "pelearon" — el modelo se confundió
- Además, CubiCasa usa 21 canales de heatmaps para junction detection que nuestras labels no tienen
- El post-procesamiento (`get_polygons`) depende de esos heatmaps y no funciona bien con predicciones de modelos fine-tuneados

### Fase 5: SegFormer — PARCIALMENTE EXITOSO

#### Por qué SegFormer
- Modelo moderno (2021, NVIDIA) de segmentación semántica
- Pre-entrenado en ImageNet (pixels), nunca vio SVGs → no hay conflicto de formatos
- Soporta 14+ clases custom
- Cabe en RTX 4090 laptop (16GB VRAM)
- Elimina dependencia de `get_polygons` — extraemos paredes directo del mask con CV

#### Preparación
1. Instalamos `transformers` de HuggingFace
2. Mergeamos labels de 2 canales (rooms+icons) a 1 canal (14 clases)
3. Script: `training/convert_labels_segformer.py`
4. Dataset PyTorch: `training/segformer_dataset.py` (lee PNG+NPY directo, sin LMDB)
5. Training script: `training/finetune_segformer.py`

#### Entrenamiento v1
- **Modelo:** nvidia/mit-b2 (27M params)
- **Dataset:** 4,958 samples (4,203 CubiCasa + 755 nuestros)
- **Config:** 30 épocas, batch 4, lr 6e-5, AMP, class weights wall=3x door/window=5x
- **Duración:** ~5 horas en RTX 4090 laptop
- **Resultados finales:**
  - val_loss: 0.617 (best)
  - mean_iou: 58.2%
  - **wall_iou: 61.2%** ← muy bueno
  - window_iou: 54.2%
  - **door_iou: 28.0%** ← muy malo
- **En la UI:** Paredes se ven MEJOR que CubiCasa. Pero puertas/ventanas no aparecen porque:
  1. El modelo detecta pocos pixels de door (0.7% del dataset)
  2. El post-procesamiento filtra los openings ("span does not fit wall", "furniture-like")

#### Intento híbrido — FALLÓ
- **Idea:** SegFormer para paredes + CubiCasa para puertas/ventanas
- **Problema:** Las coordenadas de paredes de SegFormer no coinciden con las de CubiCasa. Cuando el post-procesamiento intenta anclar openings de CubiCasa a paredes de SegFormer, no matchean → filtra todo
- **Segundo intento:** Usar CubiCasa completo + agregar paredes extra de SegFormer. Pero el threshold de duplicación (30px → 15px) hacía que o descartara todo o duplicara todo
- **Conclusión:** Combinar outputs de dos modelos con coordenadas diferentes es muy complejo

---

## Estado actual (20 marzo 2026)

### Qué funciona
- **CubiCasa baseline** en la UI — detecta paredes, puertas, ventanas. No perfecto pero funcional
- **SegFormer v1 entrenado** — detecta paredes mejor pero puertas/ventanas mal
- **Frontend React** con selector de modelos
- **Backend FastAPI** con múltiples backends
- **Pipeline completo** imagen → DXF funciona end-to-end

### Qué está corriendo ahora
1. **Gemini labeling** de imágenes 758-5000 (si la cuota se reseteó)
2. **SegFormer v2 por entrenar** con class weights wall=25x, door=25x, window=25x (todo el resto 0.05x)

### Archivos clave del proyecto

| Archivo | Qué hace |
|---------|----------|
| `backend/cubicasa_inference.py` | Inferencia CubiCasa baseline + fine-tuned |
| `backend/segformer_inference.py` | Inferencia SegFormer + extracción mask→walls |
| `backend/structure_postprocess.py` | Post-procesamiento: snap, merge, filter walls/openings |
| `backend/worker_client.py` | Router de backends (cubicasa, segformer, heuristic) |
| `backend/app.py` | FastAPI endpoints |
| `frontend/src/App.tsx` | UI React con selector de modelo |
| `training/finetune.py` | Training CubiCasa (hourglass) |
| `training/finetune_segformer.py` | Training SegFormer |
| `training/auto_label_gemini.py` | Labeling automático con Gemini Vision API |
| `training/label_converter.py` | TRAIN ONE.png → label.npy + heatmaps.json |
| `training/convert_labels_segformer.py` | label.npy 2ch → label_merged.npy 1ch (14 clases) |
| `training/convert_cubicasa.py` | CubiCasa SVG → label.npy |
| `training/segformer_dataset.py` | PyTorch Dataset para SegFormer |

### Datos en disco

**D: (SSD externo)**
```
D:\
├── PointAIData\dataset\0001-5000\     # 5,000 floor plans scrapeados
│   ├── XXXX\original.jpg              # imagen original
│   ├── XXXX\TRAIN ONE.png             # label de Gemini (757 tienen)
│   ├── XXXX\label.npy                 # label numérico (755 tienen)
│   └── XXXX\heatmaps.json            # junctions (755 tienen)
├── originals\cubicasa5k\              # repo CubiCasa original + .pkl
├── training_v2\
│   ├── converted\cubicasa\            # 4,958 samples convertidos
│   │   ├── cubicasa\                  # 4,203 CubiCasa (SVG→pixel)
│   │   ├── pointai\                   # 755 nuestros (Gemini)
│   │   └── segformer_class_stats.json # distribución de clases
│   ├── cubi_layout\                   # LMDB para CubiCasa training
│   ├── segformer_runs\                # SegFormer v1 checkpoints
│   └── segformer_runs_v2\             # SegFormer v2 (por entrenar)
├── checkpoints\runs_combined\         # CubiCasa fine-tuned (no sirve)
└── CubiCasa5k\                        # backup del .pkl
```

**C: (local)**
```
C:\Users\lucas\OneDrive\Escritorio\
├── Point.ai\                          # proyecto principal
└── floorplan-research\CubiCasa5k\     # repo CubiCasa + model .pkl
```

---

## Decisiones técnicas tomadas

| Decisión | Por qué | Resultado |
|----------|---------|-----------|
| Scraping houseplans.com | Necesitábamos planos americanos, CubiCasa solo tiene europeos | 5,018 imágenes |
| Gemini para labeling | Barato ($0.054/img), automático, buena calidad visual | Labels imperfectas pero usables |
| Fine-tune CubiCasa | Ya funcionaba, solo queríamos mejorarlo | Falló — conflicto SVG vs pixel |
| Combinar CubiCasa + nuestros datos | Para no perder conocimiento original | Funcionó parcialmente pero inferior al baseline |
| SegFormer como alternativa | Modelo moderno, entrena con pixels nativamente | Paredes excelentes, puertas/ventanas malas |
| Class weights altos para door/window | Forzar al modelo a prestar atención a clases raras | Por probar en v2 |

---

## Métricas comparativas

| Modelo | room_acc / mean_iou | wall | door | window | ¿Funciona en UI? |
|--------|-------------------|------|------|--------|-------------------|
| CubiCasa baseline | ~75% room_acc | Decente | 96% icon_acc | 96% icon_acc | **SÍ — el mejor completo** |
| CubiCasa + 146 nuestros | 83% room_acc | Peor | Peor | Peor | No — get_polygons se cuelga |
| CubiCasa + 755 nuestros | 80.5% room_acc | Peor | Peor | Peor | No — inventa paredes |
| SegFormer v1 | 58.2% mean_iou | **61.2%** | 28.0% | 54.2% | Paredes sí, openings no |
| SegFormer v2 (pendiente) | ? | ? | ? | ? | Por probar |

---

## Plan a futuro

### Corto plazo (esta semana)

1. **Terminar Gemini labeling** (758-5000) → $229 USD
2. **Entrenar SegFormer v2** con weights 25x para wall/door/window
3. **Evaluar SegFormer v2:**
   - Si door_iou > 50% → conectar a UI, arreglar post-procesamiento
   - Si door_iou sigue bajo → ir a plan B

### Mediano plazo (próximas 2-3 semanas)

4. **Si SegFormer v2 funciona:**
   - Convertir las 5,000 labels de Gemini al formato SegFormer
   - Reentrenar con 9,200+ imágenes (4,203 CubiCasa + 5,000 nuestros)
   - Arreglar post-procesamiento mask→DXF para SegFormer
   - Testing con planos reales de Pointe Homes

5. **Si SegFormer v2 NO funciona:**
   - **Opción A:** Pipeline YOLO + Shapely + LLM (más robusto, más trabajo)
   - **Opción B:** Dos modelos — SegFormer solo paredes + CubiCasa solo openings, con post-procesamiento que combine coordenadas correctamente
   - **Opción C:** Mejorar solo el post-procesamiento del CubiCasa baseline

### Producción (MVP)

6. **Elegir el mejor approach** basado en resultados
7. **Optimizar inferencia** — <5 segundos por imagen
8. **Deploy en servidor** — no depender de laptop
9. **Testing con clientes reales** de Pointe Homes
10. **Escala:** procesar los 90+ modelos de Pointe Homes automáticamente

---

## Costos incurridos

| Concepto | Costo |
|----------|-------|
| Gemini labeling (757 imgs) | $41 USD |
| Gemini labeling pendiente (4,243 imgs) | ~$229 USD |
| Entrenamiento GPU | $0 (local, RTX 4090) |
| NVIDIA DLI cursos (recomendado) | $90-$120 USD |
| **Total gastado** | **$41 USD** |
| **Total proyectado** | **~$360-$390 USD** |

---

## Lecciones aprendidas

1. **Fine-tunear un modelo entrenado con SVGs usando pixel labels no funciona** — los formatos son incompatibles
2. **Más datos de baja calidad empeoran el modelo** — error sistemático no se promedia
3. **Las métricas de entrenamiento no predicen el resultado visual** — room_acc 83% funcionaba peor en la UI que 75%
4. **El post-procesamiento es tan importante como el modelo** — un modelo perfecto no sirve si `get_polygons` se cuelga
5. **Modelos modernos (SegFormer) son mejores para entrenar desde cero con pixels** — no tienen bagaje de formatos anteriores
6. **Class weights importan mucho para clases minoritarias** — door (0.7% de pixels) necesita peso 25x+ para que el modelo le preste atención
