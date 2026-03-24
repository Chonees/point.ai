# Plan: MitUNet para detección de paredes

## ¿Qué es MitUNet?
Modelo de segmentación de paredes publicado en diciembre 2025. Combina Mix-Transformer (encoder) + U-Net (decoder) con Tversky Loss. Logra **87.84% mIoU** en walls — muy superior a nuestro mejor resultado (61% con SegFormer).

## ¿Por qué MitUNet y no SegFormer?
| Aspecto | SegFormer (nosotros) | MitUNet (paper) |
|---------|---------------------|-----------------|
| wall mIoU | 61% máximo | **87.84%** |
| Encoder | mit-b2 | mit-b4 (más grande) |
| Decoder | MLP simple | U-Net con scSE attention |
| Loss | Focal / CrossEntropy | **Tversky (α=0.6, β=0.4)** |
| Enfoque | 14 clases (wall+rooms+doors) | **Solo walls** |
| VRAM | ~8GB | 1751 MiB (~1.7GB) |

## Estrategia: 2 fases

### Fase 1: Probar el modelo pre-entrenado (30 minutos)
El repo ya tiene pesos entrenados en CubiCasa5k + fine-tuned en planos rusos.
1. Clonar repo
2. Instalar dependencias (`segmentation-models-pytorch==0.5.0`, `albumentations`)
3. Descargar pesos: `mitunet_finetune_a6_mit_b4_tversky_8864_28E.pth`
4. Correr inferencia con una imagen nuestra americana
5. Comparar visualmente: ¿detecta más paredes que CubiCasa baseline?

**Si funciona bien → integramos directo al backend (reemplaza SegFormer para walls)**
**Si no funciona → Fase 2**

### Fase 2: Fine-tunear con nuestros planos (4-6 horas)
Si el modelo pre-entrenado no funciona bien con planos americanos:
1. Generar masks binarios de walls desde nuestros `label.npy` (ya los tenemos)
2. Fine-tunear MitUNet con nuestros ~2,700 planos americanos
3. Usar Tversky Loss (α=0.6, β=0.4) como recomienda el paper
4. Learning rate bajo (1e-5) como hicieron ellos
5. 30 épocas, batch 4, 512x512

## Pasos técnicos

### Paso 1: Instalar
```bash
pip install segmentation-models-pytorch==0.5.0 albumentations
```

### Paso 2: Descargar pesos
El archivo `.pth` está en `experiments/models/` del repo.
Necesitamos git-lfs porque es un archivo grande.

### Paso 3: Script de inferencia
```python
import segmentation_models_pytorch as smp

# Crear modelo
aux_segformer = smp.Segformer(encoder_name="mit_b4", encoder_weights=None)
model = smp.Unet(
    encoder_name="mit_b4",
    encoder_weights=None,
    in_channels=3,
    classes=1,  # SOLO WALLS (binario)
    decoder_attention_type="scse"
)
model.encoder = aux_segformer.encoder

# Cargar pesos
state_dict = torch.load("path/to/weights.pth", map_location="cuda")
model.load_state_dict(state_dict)
```

### Paso 4: Integrar al backend
- Crear `backend/mitunet_inference.py`
- MitUNet produce mask binario de walls (1 canal)
- Para puertas/ventanas seguimos usando CubiCasa baseline
- Combinar: walls de MitUNet + openings de CubiCasa

### Paso 5: Fine-tune (si necesario)
```bash
python -u -m training.finetune_mitunet \
  --data-path D:/training_v2/converted/pointai_only \
  --run-dir D:/training_v2/mitunet_runs \
  --epochs 30 --batch-size 4 --device cuda \
  --learning-rate 1e-5
```

## Costos
- Fase 1: $0 (modelo pre-entrenado gratuito)
- Fase 2: $0 (entrenamiento local en RTX 4090)
- Solo tiempo de GPU

## Riesgos
- El modelo fue fine-tuned en planos rusos — pueden ser diferentes a los americanos
- Si no funciona directo, el fine-tune con labels de Gemini podría tener el mismo problema de calidad
- **Mitigación:** El encoder mit-b4 es mucho más potente que nuestro mit-b2, y Tversky Loss es mejor para walls finas

## Resultado esperado
Un modelo que detecte paredes con 80%+ mIoU en planos americanos, que combinado con CubiCasa para puertas/ventanas, genere DXFs mucho mejores que el baseline actual.
