# Point.ai — Estado Completo del Proyecto
**Última actualización: 22 de marzo 2026**

---

## Qué es Point.ai

Sistema AI para Pointe Homes (empresa con +90 modelos residenciales americanos): toma una imagen de floor plan y genera un archivo DXF profesional para AutoCAD LT 2026.

**Pipeline:**
```
Imagen floor plan → Modelo AI (segmentación) → Post-procesamiento (CV) → DXF → AutoCAD
```

---

## Historial completo de entrenamientos

### 1. CubiCasa Fine-tune — 2
olos, LR alto (0.0001)
- **Dataset:** 221 nuestros solos
- **Resultado:** room_acc 78.3%, icon_acc 97.1%
- **En la UI:** Peor que baseline — catastrophic forgetting, olvidó lo que sabía
- **Veredicto:** ❌ FALLÓ

### 2. CubiCasa Fine-tune — 221 solos, LR bajo (0.00001)
- **Dataset:** 221 nuestros solos
- **Resultado:** room_acc 48.9% después de 5 épocas
- **Problema:** LR tan bajo que no aprendió nada
- **Veredicto:** ❌ FALLÓ

### 3. CubiCasa Fine-tune — 146 nuestros + 4,203 CubiCasa
- **Dataset:** 4,349 combinados (primer dataset combinado)
- **Resultado:** room_acc 83%, val_loss 3.34 — mejor en números
- **En la UI:** `get_polygons()` se colgaba, inventaba paredes donde no hay
- **Veredicto:** ❌ Números mentían — visualmente peor que baseline

### 4. CubiCasa Fine-tune — 755 nuestros + 4,203 CubiCasa
- **Dataset:** 4,958 combinados
- **Resultado:** room_acc 80.5% — más datos de Gemini EMPEORÓ rooms
- **Análisis:** Gemini pinta menos paredes (6.6% vs 9.4% CubiCasa) y con bordes menos nítidos
- **Veredicto:** ❌ Error sistemático de Gemini, más datos no lo arregla

### 5. SegFormer v1 — 4,958 samples, weights manuales (wall=3x, door=5x)
- **Dataset:** 4,203 CubiCasa + 755 nuestros (PERO las 755 eran imágenes NEGRAS — bug en copy_pointai_to_combined)
- **Resultado:** wall_iou 61.2%, door_iou 28.0%, window_iou 54.2%
- **En la UI:** Paredes mejor que CubiCasa pero sin puertas/ventanas (post-procesamiento las filtra)
- **Nota:** Funcionó "bien" porque efectivamente entrenó solo con CubiCasa (las negras no aportaban nada)
- **Veredicto:** ⚠️ Mejor para walls pero sin openings

### 6. SegFormer v2 — weights extremos (wall=25x, door=25x, window=25x)
- **Dataset:** 4,958 samples (con negras)
- **Resultado:** wall_iou 35.4%, door_iou 6.6% — empeoró todo
- **Problema:** Weights tan extremos que el modelo ignoró rooms y perdió el contexto
- **Veredicto:** ❌ Over-engineering de weights destruyó el modelo

### 7. SegFormer v3 — Focal Loss + weights automáticos (freq inversa)
- **Dataset:** 5,914 samples (4,203 CubiCasa + 1,711 nuestros — TODAVÍA NEGRAS)
- **Resultado:** wall_iou se estancó en 48-53%, no superó v1
- **Early stopping:** época 29
- **Veredicto:** ❌ No superó v1, imágenes seguían negras

### 8. SegFormer v4 — Focal Loss + IMÁGENES REALES (bug arreglado)
- **Dataset:** 5,908 samples (4,203 CubiCasa + 1,705 nuestros REALES)
- **Resultado:** wall_iou 53.6%, door_iou 20.4%, window_iou 46.7%
- **Comparación con v1:** Peor en todo (v1: wall 61%, door 28%, window 54%)
- **Descubrimiento:** Las imágenes reales EMPEORARON el modelo vs las negras
- **Razón:** Los planos americanos y europeos son visualmente MUY diferentes:
  - CubiCasa: paredes = bloques grises gruesos, fondo blanco puro, texto finlandés
  - Nuestros: paredes = líneas finas negras, colores por habitación, dimensiones, muebles
  - El modelo se confunde aprendiendo dos estilos simultáneamente
- **Veredicto:** ❌ Mezclar datasets de estilos diferentes confunde al modelo

### 9. Intento Híbrido — SegFormer walls + CubiCasa openings
- **Idea:** Usar lo mejor de cada modelo
- **Resultado:** Los openings de CubiCasa no coincidían con las paredes de SegFormer
- **Veredicto:** ❌ Coordenadas incompatibles entre modelos

---

## El bug crítico: imágenes negras

**Descubierto en v4:** `copy_pointai_to_combined` guardaba `image.png` como imágenes negras (bright=1, 100% dark pixels). Los entrenamientos v1, v2, v3 entrenaron con 755-1,711 imágenes corruptas.

**Impacto:** v1 logró wall_iou 61% porque efectivamente entrenó SOLO con CubiCasa (las negras no aportaban). Cuando arreglamos el bug (v4) y metimos imágenes reales, bajó a 53.6% porque los estilos americano y europeo se confundían.

---

## Disyuntiva actual (22 marzo 2026)

### El problema central
Los planos de CubiCasa (europeos) y nuestros (americanos) son visualmente muy diferentes:
- **CubiCasa:** bloques grises gruesos como paredes, sin colores, texto finlandés, minimalista
- **Nuestros:** líneas finas negras como paredes, habitaciones coloreadas, dimensiones, muebles

Mezclarlos confunde al modelo. Ningún entrenamiento mixto mejoró el baseline.

### La prueba que estamos por hacer
**Entrenar SegFormer SOLO con nuestros ~2,500 planos americanos (sin CubiCasa).**

Hipótesis: con un solo estilo consistente el modelo aprende mejor, aunque tenga menos datos.

- Si wall_iou supera o se acerca a 61% → confirmamos que CubiCasa confundía
- Si wall_iou queda en ~40-50% → el problema es la calidad de las labels de Gemini
- Si funciona, con 5,000 labels será aún mejor

### Estado del Gemini labeling
- **Hechas:** ~1,721 (gastamos ~$50 USD total)
- **En proceso:** corriendo desde 1722 hasta 5000
- **Velocidad:** ~1,000/día (con paros por 503 UNAVAILABLE y timeouts)
- **Costo restante:** ~$177 USD

---

## Métricas comparativas — todos los entrenamientos

| # | Modelo | Dataset | wall_iou / room_acc | door | window | ¿UI? |
|---|--------|---------|---------------------|------|--------|------|
| — | CubiCasa baseline | Original .pkl | ~75% room_acc | 96% icon | 96% icon | **✅ Mejor completo** |
| 1 | CubiCasa FT, LR alto | 221 nuestros | 78.3% room | — | — | ❌ Catastrophic forgetting |
| 2 | CubiCasa FT, LR bajo | 221 nuestros | 48.9% room | — | — | ❌ No aprendió |
| 3 | CubiCasa FT combinado | 146+4203 | 83% room | Peor | Peor | ❌ get_polygons cuelga |
| 4 | CubiCasa FT combinado v2 | 755+4203 | 80.5% room | Peor | Peor | ❌ Inventa paredes |
| 5 | **SegFormer v1** | 4203+755(negras) | **61.2% wall** | 28% | 54% | ⚠️ Walls sí, openings no |
| 6 | SegFormer v2 (25x weights) | 4958(negras) | 35.4% wall | 6.6% | 38% | ❌ Destruyó modelo |
| 7 | SegFormer v3 (Focal) | 5914(negras) | 53% wall | — | — | ❌ No superó v1 |
| 8 | SegFormer v4 (reales) | 4203+1705 | 53.6% wall | 20.4% | 46.7% | ❌ Estilos mixtos |
| 9 | Híbrido SF+Cubi | — | — | — | — | ❌ Coords incompatibles |
| **→** | **SegFormer v5 (PRÓXIMO)** | **~2,500 solo nuestros** | **?** | **?** | **?** | **La prueba definitiva** |

---

## Archivos clave del proyecto

| Archivo | Qué hace |
|---------|----------|
| `backend/cubicasa_inference.py` | Inferencia CubiCasa baseline + fine-tuned |
| `backend/segformer_inference.py` | Inferencia SegFormer v1/v4 + extracción mask→walls |
| `backend/structure_postprocess.py` | Post-procesamiento: snap, merge, filter walls/openings |
| `backend/worker_client.py` | Router de backends (cubicasa, segformer, heuristic) |
| `backend/app.py` | FastAPI endpoints |
| `frontend/src/App.tsx` | UI React con selector de modelo (Baseline, SegFormer v1, SegFormer v4) |
| `training/finetune.py` | Training CubiCasa (hourglass) |
| `training/finetune_segformer.py` | Training SegFormer (Focal Loss + auto weights) |
| `training/auto_label_gemini.py` | Labeling automático con Gemini Vision API |
| `training/label_converter.py` | TRAIN ONE.png → label.npy + heatmaps.json |
| `training/convert_labels_segformer.py` | label.npy 2ch → label_merged.npy 1ch (14 clases) |
| `training/convert_cubicasa.py` | CubiCasa SVG → label.npy |
| `training/copy_pointai_to_combined.py` | Copiar nuestros samples al dataset combinado |
| `training/segformer_dataset.py` | PyTorch Dataset para SegFormer |

---

## Datos en disco

**D: (SSD externo)**
```
D:\
├── PointAIData\dataset\0001-5000\     # 5,000 floor plans scrapeados
│   ├── XXXX\original.jpg              # imagen original
│   ├── XXXX\TRAIN ONE.png             # label de Gemini (~1,721 tienen)
│   ├── XXXX\label.npy                 # label numérico
│   └── XXXX\heatmaps.json            # junctions
├── originals\cubicasa5k\              # repo CubiCasa original + .pkl
├── training_v2\
│   ├── converted\cubicasa\            # 5,908 samples convertidos
│   │   ├── cubicasa\                  # 4,203 CubiCasa (SVG→pixel)
│   │   └── pointai\                   # 1,705 nuestros (Gemini, REALES)
│   ├── segformer_runs\                # SegFormer v1 checkpoints (el mejor para walls)
│   └── segformer_runs_v4\             # SegFormer v4 checkpoints
└── CubiCasa5k\                        # backup del .pkl
```

**C: (local)**
```
C:\Users\lucas\OneDrive\Escritorio\
├── Point.ai\                          # proyecto principal
└── floorplan-research\CubiCasa5k\     # repo CubiCasa + model .pkl
```

---

## Costos incurridos

| Concepto | Costo |
|----------|-------|
| Gemini labeling (~1,721 imgs) | ~$50 USD |
| Gemini labeling restante (~3,279 imgs) | ~$177 USD |
| Entrenamiento GPU | $0 (local, RTX 4090 laptop) |
| **Total gastado** | **~$50 USD** |
| **Total proyectado** | **~$227 USD** |

---

## Lecciones aprendidas

1. **Fine-tunear un modelo SVG con pixel labels no funciona** — formatos incompatibles
2. **Más datos de baja calidad empeoran el modelo** — error sistemático no se promedia
3. **Las métricas no predicen el resultado visual** — room_acc 83% fue peor en la UI que 75%
4. **El post-procesamiento es tan importante como el modelo** — modelo perfecto no sirve si get_polygons se cuelga
5. **Modelos modernos (SegFormer) son mejores para pixels** — no tienen bagaje SVG
6. **Mezclar datasets de estilos visualmente diferentes confunde al modelo** — CubiCasa (europeo) + nuestros (americanos) = peor que cada uno solo
7. **SIEMPRE verificar que las imágenes de training no estén corruptas** — entrenamos 3 versiones con imágenes negras sin darnos cuenta
8. **El bug más simple puede arruinar semanas de trabajo** — copy_pointai_to_combined guardaba imágenes negras
9. **Focal Loss + class weights automáticos (freq inversa) funciona mejor que weights manuales extremos**
10. **Un solo estilo de datos consistente es mejor que muchos estilos mezclados**

---

## Plan inmediato

1. ✅ Seguir labeleando con Gemini hasta tener ~2,500
2. → Entrenar SegFormer v5 SOLO con nuestros ~2,500 (sin CubiCasa)
3. → Evaluar: ¿wall_iou supera 55%? ¿Funciona bien en la UI?
4. → Si sí: labelear hasta 5,000 y entrenar modelo final
5. → Si no: repensar approach completamente (YOLO pipeline, Claude Vision directo, etc.)
