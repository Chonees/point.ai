# Research: Automatic Architectural Dimensioning — State of the Art

## 1. El problema que queremos resolver

Dada una imagen de floor plan con paredes y aberturas detectadas, generar **dimension chains profesionales** en DXF que cumplan con estándares arquitectónicos (NCS, IRC 2021, convenciones Pointe Homes).

---

## 2. Cómo lo resuelven los profesionales (Vectorworks, Revit)

### Vectorworks: "Dimension Exterior Walls" Command

Vectorworks tiene un comando que **automáticamente dimensiona todo el edificio** en 3 cadenas:

```
Cadena 1: Aberturas — centerline de puertas/ventanas
Cadena 2: T-junctions — donde muros interiores tocan el exterior
Cadena 3: Overall — dimensión total de esquina a esquina
```

**Cómo calcula aberturas:**
- Ventanas: rough opening = unit size + 2 × shim gap
- Puertas: rough opening = leaf size + 2 × jamb width + 2 × shim gap
- Dimensiona a **center** o **edges** del opening (configurable)
- Puede dimensionar respecto a **walls** o **core components**
- Puede usar **outer sides** o **centerlines**

Fuente: [Vectorworks Dimension Exterior Walls](https://app-help.vectorworks.net/2023/eng/VW2023_Guide/Dimensions/Dimensioning_exterior_walls.htm)

### Revit: Auto-Aligned Dimensions

- Un click en una pared → dimensiona toda la pared con intersecciones
- Puede dimensionar pared con intersecting walls, o pared con openings
- Selecciona **Centers** o **Widths** para openings
- Usa references de Revit (wall faces, centerlines, grid lines)

Fuente: [Revit Auto Dimensions](https://help.autodesk.com/cloudhelp/2022/ENU/Revit-DocumentPresent/files/GUID-C26D95E4-F272-4C67-8C1D-BC26C0493B75.htm)

### pyRevit / Dynamo Scripts

La comunidad ha construido scripts que:
- Crean sublists de segmentos colineares por dirección
- Manejan casos donde una línea de boundary consiste en múltiples segmentos
- Limitación actual: no manejan arcos ni muros curvos
- Son work-in-progress, no perfectos

Fuentes:
- [pyRevit Auto-Dimension Floor Plans](https://discourse.pyrevitlabs.io/t/auto-dimension-floor-plans/2893)
- [Dynamo Auto-Dimension Rooms](https://maciejglowka.com/blog/auto-dimensioning-rooms-with-dynamo-and-python/)
- [Dynamo Auto-Dimension from Walls](https://forum.dynamobim.com/t/auto-dimension-from-walls/26631)

---

## 3. AI/ML para floor plan recognition

### CubiCasa5k (lo que ya usamos)

- 5000 floor plans, 80+ categorías
- Detecta: walls, doors, windows, room types
- Método: CNN → junction detection → integer programming → vectorization
- **NO genera dimensions** — solo vectoriza la geometría

Fuente: [CubiCasa5k GitHub](https://github.com/CubiCasa/CubiCasa5k)

### Raster-to-Vector (ICCV 2017)

- Convierte imagen raster → vector-graphics
- Detecta 13 tipos de wall junctions (I, L, T, X + orientaciones)
- ~90% precision y recall
- Genera primitivas: wall lines, door lines, icon boxes
- **NO genera dimensions**

Fuente: [FloorplanTransformation GitHub](https://github.com/art-programmer/FloorplanTransformation)

### FloorPlanParser

- API: envía imagen → recibe vectorized walls/doors/windows con start/end points
- Da coordenadas exactas de cada elemento
- **NO genera dimensions**

Fuente: [FloorPlanParser GitHub](https://github.com/TINY-KE/FloorPlanParser)

### CPN-Floor

- Keypoint-based detection para walls, doors, windows, scale indicators
- 87% precision, 88% recall
- Error posicional <1% de las dimensiones del plano
- **Detecta scale indicators** — puede leer la escala del plano

Fuente: [CPN-Floor ResearchGate](https://www.researchgate.net/publication/355867277_Residential_floor_plan_recognition_and_reconstruction)

### DeepFloorplan (ICCV 2019)

- Multi-task network: room-boundary + room-type recognition
- Room-boundary-guided attention
- Segmentación semántica de rooms

Fuente: [DeepFloorplan GitHub](https://github.com/zlzeng/DeepFloorplan)

### FloorPlanCAD (ICCV 2021)

- Dataset grande de dibujos CAD
- Panoptic symbol spotting (detecta TODO en un plano CAD)
- Incluye dimensiones como entidades reconocibles

Fuente: [FloorPlanCAD Paper](https://openaccess.thecvf.com/content/ICCV2021/papers/Fan_FloorPlanCAD_A_Large-Scale_CAD_Drawing_Dataset_for_Panoptic_Symbol_Spotting_ICCV_2021_paper.pdf)

### ResPlan (2025 — MÁS RECIENTE)

- **17,000 floor plans** vectorizados con graph representation
- Walls con snap alignment, collinear merging
- Wall depth uniforme (0.15m) para cada layout
- Rooms como nodos con type + area
- Adjacency edges con tipo (door, open-arch)
- **Pipeline open-source** para geometry cleaning

Fuente: [ResPlan ArXiv](https://arxiv.org/abs/2508.14006), [ResPlan GitHub](https://github.com/m-agour/ResPlan)

---

## 4. Software comercial que ya hace esto

### Kreo (Construction Takeoff)

- **Un click → detecta, clasifica y mide** todo el plano
- Auto Measure: rooms, walls, doors, windows, areas, perimeters
- Clasifica en grupos: walls, doors, stairs, living rooms, bedrooms
- Calcula: GIA, GEA, NIA automáticamente
- **13.5x más rápido** que medición manual
- Combina: ML + computer vision + OCR
- Cloud-based, producción real

Fuente: [Kreo Auto Measure](https://help-takeoff.kreo.net/en/articles/5481199-auto-measure)

### Planner 5D

- Upload imagen → reconocimiento automático → 3D scene
- Mediciones aproximadas basadas en calidad de imagen
- Permite ajuste manual post-detección

Fuente: [Planner 5D AI](https://planner5d.com/ai)

### Maket AI

- Input: room quantities + dimension requirements + natural language
- Genera cientos de opciones de layout
- Cumple con regulaciones locales
- **No extrae dimensiones de imágenes** — genera desde especificaciones

Fuente: [Maket AI](https://www.maket.ai/)

---

## 5. Papers académicos clave

### GPLAN (2020) — Dimensioned Floorplans from Adjacencies

- Input: adjacency graph (qué rooms son vecinos)
- Output: floorplan dimensionado con boundary rectangular
- Método: **st-graphs + linear programming optimization**
- Genera dimensiones que satisfacen constraints del usuario
- Minimiza área total preservando topología

Fuente: [GPLAN ArXiv](https://arxiv.org/abs/2008.01803)

### Automated Generation of Dimensioned Rectangular Floorplans (2019)

- Genera planos rectangulares dimensionados
- Iterative linear optimization con st-graphs H y V
- Objective function: minimizar área total del plano

Fuente: [ArXiv 1910.00081](https://arxiv.org/pdf/1910.00081)

### Comprehensive Survey of Floor Plan Recognition (2025)

- Review completo: técnicas tradicionales → deep learning
- Cubre: wall detection, room segmentation, symbol recognition
- Estado del arte: deep learning supera métodos clásicos en todos los benchmarks

Fuente: [ACM 2025 Survey](https://dl.acm.org/doi/full/10.1145/3747227.3747250)

### Automatic Floor Plan Analysis and Recognition (2022)

- ScienceDirect survey
- Keypoint detection + geometric constraints + post-processing
- 87% precision, 88% recall

Fuente: [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0926580522002217)

---

## 6. Datasets disponibles

| Dataset | Size | Contents | Measurements |
|---------|------|----------|-------------|
| CubiCasa5k | 5,000 | Walls, rooms, icons | No |
| FloorPlanCAD | Large | CAD symbols, dims | Yes (as symbols) |
| MLSTRUCT-FP | 954 | Walls in JSON, scale info | Yes (px/m) |
| ResPlan | 17,000 | Vector walls, room graphs | Yes (areas, connectivity) |
| RPLAN | 80,000+ | Room layouts | Room areas only |
| Zillow Indoor | Large | Panoramic images | Door/window detection |

---

## 7. Conclusión: qué approach tomar

### Lo que NO existe (gap en el mercado)

**Ninguna herramienta open-source genera dimension chains arquitectónicas automáticamente.** Todos los papers y tools se enfocan en:
- Detectar walls/rooms/openings ✓ (ya lo hacemos)
- Vectorizar geometría ✓ (ya lo hacemos)
- Generar floor plans desde specs (GPLAN)

Pero **ninguno genera las 3 cadenas de dims** como Vectorworks/Revit.

### El approach correcto para Point.ai

No necesitamos IA para esto. Es **puro algoritmo determinístico** que imita lo que Vectorworks hace:

```
Input:
  - Wall segments [{start, end, orientation}]
  - Opening annotations [{type, position, width}]
  - Scale (inches/pixel, del sqft label)

Algorithm:
  1. Identify exterior walls (outermost in each direction)
  2. For each exterior wall:
     a. Find all openings ON this wall
     b. Sort by position along the wall
     c. Chain 1: corner → CL opening 1 → CL opening 2 → ... → corner
     d. Chain 2: wall segments between openings
     e. Chain 3: overall corner-to-corner
  3. For interior rooms:
     a. Face-to-face measurement (width × length)
     b. Room label centered
  4. Generate DIMLINEAR entities on DIMS layer

Complexity: O(W × O) where W=walls, O=openings
```

Este algoritmo es ~200 líneas de Python, determinístico, testeable, y produce exactamente lo que un arquitecto espera.

---

## Sources

### Software Documentation
- [Vectorworks Dimension Exterior Walls](https://app-help.vectorworks.net/2023/eng/VW2023_Guide/Dimensions/Dimensioning_exterior_walls.htm)
- [Revit Auto Aligned Dimensions](https://help.autodesk.com/cloudhelp/2022/ENU/Revit-DocumentPresent/files/GUID-C26D95E4-F272-4C67-8C1D-BC26C0493B75.htm)
- [Kreo Auto Measure](https://help-takeoff.kreo.net/en/articles/5481199-auto-measure)
- [Kreo Floor Plan Recognition](https://www.kreo.net/news-2d-takeoff/floor-plan-recognition-technologies)

### Academic Papers
- [GPLAN: Computer-Generated Dimensioned Floorplans](https://arxiv.org/abs/2008.01803)
- [Automated Generation of Dimensioned Rectangular Floorplans](https://arxiv.org/pdf/1910.00081)
- [Raster-to-Vector: Revisiting Floorplan Transformation (ICCV 2017)](https://art-programmer.github.io/floorplan-transformation.html)
- [FloorPlanCAD: Large-Scale CAD Dataset (ICCV 2021)](https://openaccess.thecvf.com/content/ICCV2021/papers/Fan_FloorPlanCAD_A_Large-Scale_CAD_Drawing_Dataset_for_Panoptic_Symbol_Spotting_ICCV_2021_paper.pdf)
- [ResPlan: 17,000 Residential Floor Plans (2025)](https://arxiv.org/abs/2508.14006)
- [Comprehensive Survey Floor Plan Recognition (2025)](https://dl.acm.org/doi/full/10.1145/3747227.3747250)
- [Automatic Floor Plan Analysis and Recognition (2022)](https://www.sciencedirect.com/science/article/abs/pii/S0926580522002217)
- [CPN-Floor Residential Recognition](https://www.researchgate.net/publication/355867277_Residential_floor_plan_recognition_and_reconstruction)

### Open-Source Tools
- [CubiCasa5k](https://github.com/CubiCasa/CubiCasa5k)
- [FloorplanTransformation](https://github.com/art-programmer/FloorplanTransformation)
- [FloorPlanParser](https://github.com/TINY-KE/FloorPlanParser)
- [DeepFloorplan](https://github.com/zlzeng/DeepFloorplan)
- [ResPlan](https://github.com/m-agour/ResPlan)
- [MLSTRUCT-FP](https://github.com/MLSTRUCT/MLSTRUCT-FP)
- [Floor-Plan-Detection](https://github.com/rbg-research/Floor-Plan-Detection)

### Community Scripts
- [pyRevit Auto-Dimension Floor Plans](https://discourse.pyrevitlabs.io/t/auto-dimension-floor-plans/2893)
- [Dynamo Auto-Dimension Rooms](https://maciejglowka.com/blog/auto-dimensioning-rooms-with-dynamo-and-python/)
- [Dynamo Auto-Dimension from Walls](https://forum.dynamobim.com/t/auto-dimension-from-walls/26631)
