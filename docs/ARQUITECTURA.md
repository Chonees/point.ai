# Plan Realista de MVP AI-Based para Point.ai

## Resumen
Vamos a **dejar de usar `imagen -> Claude -> rooms rectangulares -> DXF` como camino principal** y construir un pipeline nuevo donde la IA entienda estructura y el DXF final mantenga el estilo Pointe Homes.

La decisión técnica es esta:
- **Mantener el renderer CAD actual como referencia visual y de layers**.
- **Sacar a Claude del core geométrico**.
- **Usar un servicio de inferencia GPU del lado servidor**, no la GPU del usuario.
- **Construir el MVP sobre geometría + doors + windows**, y recién después sumar rooms/text/labels/fixtures.

El primer MVP útil no va a prometer “entender todo el plano”. Va a prometer esto:
- huella exterior correcta
- muros principales conectados
- openings como puertas/ventanas reales
- DXF con layers y estilo Pointe coherente

## Stack elegido y de dónde tomamos lógica
### 1. Modelo base elegido
**Elegido para el MVP:** `CubiCasa5k / floortrans`
- Nos sirve como base AI real porque ya está en el dominio correcto: floor plans.
- Ya trae dataset, loader, pesos y postproceso de polígonos.
- Es más útil para arrancar que `TF2DeepFloorplan`, porque tiene mejor conexión con `walls / icons / openings`.

**Uso concreto**
- `CubiCasa5k/floortrans/loaders/svg_loader.py`: formato de labels y lectura del dataset
- `CubiCasa5k/floortrans/post_prosessing.py`: reconstrucción de paredes, openings y limpieza geométrica
- `CubiCasa5k/eval.py`: evaluación por clases y estructura base de benchmark

### 2. Lógica de reconstrucción geométrica
**Tomar de:** `FloorplanTransformation`
- No lo usamos como stack productivo.
- Sí lo usamos como referencia para:
  - reconstrucción raster -> vector
  - corners / lines / icon reasoning
  - resolver paredes conectadas y openings
- Piezas más valiosas:
  - `pytorch/IP.py`
  - conceptos de `corner -> wall line -> opening/icon -> reconstructed floorplan`

### 3. Lógica pragmática de análisis
**Tomar de:** `FloorPlanTo3D-API---Simsys`
- No usar su modelo como base principal de producción.
- Sí reutilizar o portar su lógica de ingeniería:
  - `analysis/wall_analysis.py`: thickness, orientation, junctions, centerlines
  - `analysis/door_analysis.py`: orientación y swing heurístico
  - `analysis/window_analysis.py`: clasificación geométrica básica
  - `image_processing/mask_processing.py`: limpieza de máscaras y segmentación de muros
- Esto nos da una capa de análisis útil encima de las máscaras del modelo.

### 4. Qué NO usar como core
**`TF2DeepFloorplan`**
- Lo dejaría como benchmark secundario y referencia de serving.
- No lo elegiría como core del MVP porque está más orientado a `room + boundary segmentation` que a `door/window semantics` listas para CAD.

## Arquitectura elegida
### 1. Separación de servicios
**Servicio A: Point.ai API**
- Sigue siendo el backend de producto.
- Recibe la imagen.
- Llama al servicio de inferencia.
- Corre postproceso final y genera DXF.
- Devuelve preview + DXF.

**Servicio B: Inference GPU**
- Corre en servidor con GPU.
- Usa el modelo base de floor plan analysis.
- Devuelve máscaras, logits o detecciones estructurales.

Esto evita:
- depender de la GPU del usuario
- mezclar dependencias viejas/experimentales dentro del backend principal
- bloquear la app web con inferencia pesada

### 2. Contrato canónico nuevo
El backend nuevo no debe hablar en `rooms` rectangulares.  
Debe hablar en este contrato:

- `walls[]`
  - `id`
  - `polyline` o `axis-aligned segment`
  - `thickness`
  - `is_exterior`
- `openings[]`
  - `id`
  - `kind = door | window`
  - `wall_id`
  - `position`
  - `span`
  - `orientation`
  - `swing` solo para doors
  - `confidence`
- `structure_meta`
  - `image_size`
  - `scale_status = unverified | calibrated`
  - `unit = pixel | inch`

Este contrato es el único que debe alimentar al generador DXF nuevo.

### 3. Renderer CAD
No vamos a intentar forzar este contrato dentro del orquestador actual basado en rooms.

Decisión:
- conservar `layers` y estilo Pointe como referencia
- crear un renderer nuevo para geometría estructural
- reutilizar:
  - naming de layers
  - primitives
  - estilo visual de puertas y ventanas
- dejar el pipeline viejo intacto para compatibilidad

El generador nuevo va a dibujar:
- muros desde `walls[]`
- puertas desde `openings[kind=door]`
- ventanas desde `openings[kind=window]`

## Implementación del MVP
### Fase 1. Benchmark serio y selección final del baseline
Objetivo: elegir el baseline real sobre datos Pointe antes de integrar.

Acciones:
- correr `CubiCasa/floortrans` sobre un set chico de planos reales Pointe
- correr `TF2DeepFloorplan` solo como comparativa de boundary quality
- usar `Simsys` para comparar su postproceso, no su modelo, salvo que sorprenda positivamente

Salida de esta fase:
- decisión final del modelo de inferencia v1
- score visual y estructural sobre 10-20 planos reales
- carpeta de artefactos: máscaras, overlays, openings detectados, preview DXF

Criterio de elección:
- continuidad de muros
- huella exterior
- falsos positivos de texto/furniture como wall
- recall de doors/windows

### Fase 2. Servicio de inferencia GPU
Objetivo: dejar un servicio estable, aislado del backend principal.

Decisiones:
- Docker + Linux CUDA
- PyTorch como stack preferido del servicio
- carga única del modelo al iniciar
- endpoint interno:
  - `POST /infer/structure`
  - input: imagen
  - output: masks / polygons / detections estructurales

Comportamiento:
- si el modelo devuelve segmentación, el servicio también puede devolver logits opcionales para debugging
- si falla, responde error tipado y nunca genera DXF parcial silencioso

### Fase 3. Postproceso geométrico
Objetivo: pasar de máscaras a estructura CAD útil.

Pipeline:
1. limpiar máscaras
2. separar `wall body`, `door`, `window`
3. extraer skeleton / centerline de muros
4. snap ortogonal
5. merge de colineares
6. construir `wall graph`
7. detectar junctions `L/T/X`
8. asignar openings a muros válidos
9. estimar swing de puertas con heurística tipo Simsys
10. clasificar exterior/interior

Reglas clave:
- texto, cotas y muebles nunca entran al wall graph
- un opening solo existe si está anclado a un muro válido
- si un muro no queda conectado razonablemente, se marca con baja confianza y se conserva para preview, no para render final

### Fase 4. Generación DXF nueva
Objetivo: salida CAD utilizable con el look Pointe.

Cambios:
- agregar un generador estructural nuevo en paralelo al actual
- mantener `/api/generate` legacy sin tocar
- agregar:
  - `POST /api/v2/parse-structure`
  - `POST /api/v2/generate-dxf`

`parse-structure` devuelve:
- `walls`
- `openings`
- `preview_url`
- métricas de calidad

`generate-dxf` devuelve:
- `dxf_url`
- `preview_url`
- `structure`
- `needs_review`
- `scale_status`

### Fase 5. Escala y unidades
Decisión por defecto para el MVP:
- la geometría interna se maneja en coordenadas de imagen
- si el usuario provee `scale_hint`, se convierte a pulgadas antes del render
- si no hay escala:
  - el DXF se genera igual
  - queda marcado como `scale_status=unverified`

Eso evita inventar medidas falsas.

## Qué entra y qué no entra en el MVP
### Entra
- contorno exterior
- muros interiores estructurales
- doors
- windows
- preview de overlays
- DXF válido con layers Pointe base

### No entra en el camino crítico
- room labels
- dimension text
- OCR
- fixtures
- furniture
- bathtub/sink/toilet/cabinets
- Claude como extractor geométrico

### Fase siguiente al MVP
Cuando la estructura esté estable:
- OCR para room labels y dimensions
- rooms derivados desde wall graph
- luego fixtures y blocks Pointe
- Claude solo para reconciliar ambigüedad, no para extraer coordenadas

## Test plan y criterios de aceptación
### Dataset de validación
- 20 planos Pointe reales
- 5 limpios
- 10 medianamente complejos
- 5 con escaleras/deck/nichos/quiebres

### Validaciones obligatorias
- huella exterior visualmente correcta
- deck y main entry no desaparecen cuando están presentes
- los openings no se convierten en muros continuos
- no aparecen muebles/cotas/texto como muros
- el DXF abre limpio en AutoCAD
- layers correctas: `WALLS`, `DOORS`, `WINS`

### Métricas mínimas del MVP
- `wall footprint IoU >= 0.85`
- `exterior wall recall >= 0.90`
- `door/window precision >= 0.80`
- `door/window recall >= 0.75`
- `0` fixtures/muebles dibujados como muros en los casos de validación
- tiempo p50 end-to-end <= 15 s en GPU 4070 o equivalente de servidor

### Artefactos por corrida
Guardar siempre:
- máscara de estructura
- wall graph overlay
- openings overlay
- preview DXF rasterizado
- JSON canónico de estructura

## Deploy para empresa
### MVP deployado
- backend centralizado
- inferencia en servidor con GPU
- el cliente no usa su GPU
- un único contenedor GPU puede servir para el primer despliegue

### Producción siguiente
- separar API y worker GPU
- cola de trabajos
- almacenamiento persistente de previews y DXF
- observabilidad por plano y por versión de modelo

## Supuestos y defaults
- El producto final no dependerá de la GPU del usuario.
- El primer despliegue será en backend GPU centralizado.
- `CubiCasa/floortrans` es el baseline inicial de inferencia; `Simsys` aporta postproceso; `FloorplanTransformation` aporta lógica de reconstrucción; `TF2DeepFloorplan` queda como benchmark secundario.
- El renderer CAD actual no se desecha, pero deja de depender de `rooms[]` como contrato principal.
- Claude queda fuera del camino crítico de geometría en el MVP.
