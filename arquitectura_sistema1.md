# Sistema 1 — Generación de Floor Plan desde Imagen
## Arquitectura Técnica Completa y Exhaustiva

---

## Stack Tecnológico

| Componente | Tecnología | Rol |
|-----------|-----------|-----|
| Extracción geométrica | OpenCV | Detectar líneas, paredes, polígonos |
| OCR técnico | PaddleOCR | Leer dimensiones y texto del plano |
| Comprensión de documento | LayoutLM v3 (Microsoft) | Entender relación texto-geometría |
| Decisiones ambiguas | Claude API (Vision + Text) | Resolver lo que geometría no puede |
| Representación intermedia | IFC (ifcopenshell) | Modelo estándar del edificio |
| Validación de códigos | Python custom | IRC 2021, NEC 2020, IECC 2021 |
| Human in the Loop | FastAPI + WebSocket | Cola asíncrona de preguntas a Carlos |
| Generación DWG | ezdxf + bloques Pointe Homes | Output final en AutoCAD |
| Ejecución en AutoCAD | MCP autocad-mcp | Verificación visual final |
| Frontend | React + TypeScript | Interfaz web |
| Backend | Python + FastAPI | Orquestador del pipeline |
| Base de datos | PostgreSQL | Reglas, bloques, historial, aprendizaje |
| Cola de tareas | Celery + Redis | Procesamiento asíncrono |
| Almacenamiento | AWS S3 | Imágenes, DWGs, IFCs generados |

---

## Visión General del Pipeline

```
ENTRADA
PDF / JPG / PNG
        │
        ▼
┌─────────────────┐
│  PASO 1         │
│  Preprocesamiento│
│  de imagen      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  PASO 2         │
│  Extracción     │
│  geométrica     │
│  OpenCV         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  PASO 3         │
│  Extracción     │
│  de texto       │
│  PaddleOCR      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  PASO 4         │
│  Comprensión    │
│  LayoutLM v3    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  PASO 5         │
│  Claude Vision  │
│  ambigüedades   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  PASO 6         │
│  JSON canónico  │
│  con confianza  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  PASO 7         │
│  Validador      │
│  geométrico     │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
  OK          DUDAS
    │         │
    │         ▼
    │  ┌─────────────┐
    │  │  PASO 8     │
    │  │  Human in   │
    │  │  the Loop   │
    │  └─────┬───────┘
    │        │
    └────────┘
         │
         ▼
┌─────────────────┐
│  PASO 9         │
│  Generación IFC │
│  ifcopenshell   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  PASO 10        │
│  Validación     │
│  de códigos     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  PASO 11        │
│  Generación DWG │
│  ezdxf +        │
│  bloques PH     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  PASO 12        │
│  Verificación   │
│  MCP + AutoCAD  │
└────────┬────────┘
         │
         ▼
      SALIDA
      DWG profesional
```

---

## PASO 1 — Preprocesamiento de Imagen

### Objetivo
Convertir cualquier input (PDF, JPG, PNG, foto de pantalla) en una imagen limpia y estandarizada que maximice la precisión de los pasos siguientes.

### Micro-pasos

**1.1 — Detección del tipo de input**
```python
def detect_input_type(file_path: str) -> str:
    # PDF → convertir cada página a imagen
    # JPG/PNG → usar directamente
    # Verificar resolución mínima (300 DPI para texto legible)
```

**1.2 — Conversión PDF a imagen**
```python
# Librería: pdf2image
# Resolución: 300 DPI mínimo
# Formato output: PNG sin compresión
from pdf2image import convert_from_path
pages = convert_from_path(pdf_path, dpi=300)
# Seleccionar página con el floor plan (generalmente página 1)
```

**1.3 — Normalización de imagen**
```python
import cv2
import numpy as np

def normalize_image(img):
    # 1. Convertir a escala de grises
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 2. Aumentar contraste (CLAHE)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(gray)
    
    # 3. Reducir ruido
    denoised = cv2.fastNlMeansDenoising(enhanced, h=10)
    
    # 4. Binarización adaptativa (texto negro sobre blanco)
    binary = cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2
    )
    return binary
```

**1.4 — Detección y corrección de rotación**
```python
def deskew(img):
    # Detectar ángulo de inclinación con HoughLines
    # Corregir si la inclinación > 0.5 grados
    # Floor plans deben estar perfectamente horizontales
    coords = np.column_stack(np.where(img > 0))
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    (h, w) = img.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(img, M, (w, h))
```

**1.5 — Estandarización de resolución**
```python
# Target: 2480 x 3508 px (A4 a 300 DPI)
# Si la imagen es más pequeña: upscale con interpolación cúbica
# Si es más grande: downscale para uniformidad
TARGET_WIDTH = 2480
TARGET_HEIGHT = 3508
```

**Output del Paso 1:**
Imagen PNG normalizada, binarizada, sin rotación, en resolución estándar.

---

## PASO 2 — Extracción Geométrica con OpenCV

### Objetivo
Detectar todas las líneas, paredes y polígonos del plano usando matemática computacional, no inferencia de IA.

### Micro-pasos

**2.1 — Detección de líneas con Hough Transform**
```python
def detect_lines(img):
    # Detectar bordes con Canny
    edges = cv2.Canny(img, 50, 150, apertureSize=3)
    
    # Hough Transform probabilístico para líneas
    lines = cv2.HoughLinesP(
        edges,
        rho=1,              # Resolución 1 pixel
        theta=np.pi/180,    # Resolución 1 grado
        threshold=100,      # Mínimo de votos
        minLineLength=20,   # Mínimo largo de línea en px
        maxLineGap=5        # Máximo gap entre segmentos
    )
    return lines
```

**2.2 — Clasificación de líneas por orientación**
```python
def classify_lines(lines):
    horizontal = []  # ángulo < 5 grados
    vertical = []    # ángulo > 85 grados
    diagonal = []    # resto (escaleras, rampas)
    
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = abs(np.degrees(np.arctan2(y2-y1, x2-x1)))
        if angle < 5 or angle > 175:
            horizontal.append(line)
        elif 85 < angle < 95:
            vertical.append(line)
        else:
            diagonal.append(line)
    
    return horizontal, vertical, diagonal
```

**2.3 — Detección de paredes dobles**
```python
def detect_double_walls(horizontal, vertical, tolerance=10):
    # Las paredes en planos técnicos son DOS líneas paralelas
    # separadas por el grosor de la pared (4-6 pulgadas en escala)
    # Detectar pares de líneas paralelas con separación consistente
    wall_pairs = []
    for i, line1 in enumerate(horizontal):
        for j, line2 in enumerate(horizontal):
            if i >= j:
                continue
            gap = abs(line1[0][1] - line2[0][1])
            if 3 < gap < 15:  # Rango de grosor de pared en pixels
                wall_pairs.append((line1, line2, gap))
    return wall_pairs
```

**2.4 — Detección de polígonos cerrados (cuartos)**
```python
def detect_rooms(img):
    # Encontrar contornos cerrados
    contours, hierarchy = cv2.findContours(
        img, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )
    
    rooms = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 1000:  # Filtrar ruido pequeño
            continue
        
        # Aproximar a polígono
        epsilon = 0.02 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        
        # Solo cuartos rectangulares (4 vértices)
        if len(approx) == 4:
            x, y, w, h = cv2.boundingRect(approx)
            rooms.append({
                "bbox": (x, y, w, h),
                "area_px": area,
                "contour": approx
            })
    
    return rooms
```

**2.5 — Detección de aperturas (puertas y ventanas)**
```python
def detect_openings(wall_pairs, img):
    # Las aperturas son INTERRUPCIONES en las líneas de pared
    # Detectar gaps en líneas que de otro modo serían continuas
    openings = []
    for wall in wall_pairs:
        gaps = find_gaps_in_line(wall)
        for gap in gaps:
            # Clasificar por tamaño del gap
            # 28-36" = puerta interior
            # 36" = puerta principal
            # 24-48" = ventana
            opening_type = classify_opening_size(gap["width_px"])
            openings.append({
                "type": opening_type,
                "position": gap["position"],
                "width_px": gap["width_px"],
                "wall": wall
            })
    return openings
```

**2.6 — Detección de arcos de puerta**
```python
def detect_door_arcs(img):
    # Los arcos de swing de puertas son quarter-circles
    # Detectar círculos/arcos con HoughCircles
    circles = cv2.HoughCircles(
        img,
        cv2.HOUGH_GRADIENT,
        dp=1,
        minDist=20,
        param1=50,
        param2=30,
        minRadius=15,
        maxRadius=60
    )
    # Filtrar para quedarse solo con quarter-circles
    # (los arcos de puerta son siempre 90 grados)
    return filter_door_arcs(circles)
```

**2.7 — Cálculo de escala del plano**
```python
def calculate_scale(detected_dims_px, ocr_dims_text):
    # Relacionar dimensiones en pixels con dimensiones en texto
    # Ej: si el OCR leyó "13'11"" y esa pared mide 420px
    # escala = (13*12 + 11) / 420 = 167 / 420 = 0.397 in/px
    scale_samples = []
    for px_dim, text_dim in zip(detected_dims_px, ocr_dims_text):
        inches = parse_feet_inches(text_dim)
        scale_samples.append(inches / px_dim)
    
    # Usar mediana para robustez ante outliers
    return np.median(scale_samples)
```

**Output del Paso 2:**
Lista de paredes con coordenadas en pixels, lista de cuartos como polígonos, lista de aperturas, arcos de puerta detectados, escala calculada.

---

## PASO 3 — Extracción de Texto con PaddleOCR

### Objetivo
Leer con precisión todas las dimensiones, nombres de cuartos y notas técnicas del plano.

### Por qué PaddleOCR y no Tesseract
PaddleOCR tiene un modelo específico para texto en documentos técnicos y maneja mejor los números con formatos especiales como 13'11" y las fuentes arquitectónicas como ARCHITXT.

### Micro-pasos

**3.1 — Inicialización del modelo**
```python
from paddleocr import PaddleOCR

ocr = PaddleOCR(
    use_angle_cls=True,   # Detectar texto rotado (cotas verticales)
    lang='en',
    det_db_thresh=0.3,    # Sensibilidad de detección
    rec_algorithm='SVTR_LCNet'  # Mejor para texto técnico
)
```

**3.2 — Extracción de texto con posición**
```python
def extract_text_with_position(img):
    result = ocr.ocr(img, cls=True)
    
    text_elements = []
    for line in result[0]:
        bbox = line[0]      # Coordenadas del bounding box
        text = line[1][0]   # Texto detectado
        confidence = line[1][1]  # Confianza 0-1
        
        text_elements.append({
            "text": text,
            "bbox": bbox,
            "center": calculate_center(bbox),
            "confidence": confidence,
            "type": classify_text_type(text)
        })
    
    return text_elements
```

**3.3 — Clasificación de tipos de texto**
```python
def classify_text_type(text: str) -> str:
    # Dimensión: "13'11"", "13'-11"", "167""
    if re.match(r"\d+['\"]\d*['\"]?", text):
        return "dimension"
    
    # Nombre de cuarto: mayúsculas, sin números
    if text.isupper() and not any(c.isdigit() for c in text):
        return "room_name"
    
    # Nota técnica: texto mixto largo
    if len(text) > 20:
        return "note"
    
    return "other"
```

**3.4 — Parser de dimensiones arquitectónicas**
```python
def parse_architectural_dim(text: str) -> dict:
    """
    Parsea formatos:
    - "13'11"" → 167 inches
    - "13'-11"" → 167 inches  
    - "167"" → 167 inches
    - "13.91'" → 167 inches
    - "14'4" x 17'4"" → {w: 172, h: 208}
    """
    patterns = [
        r"(\d+)'[-\s]?(\d+)\"",      # 13'11"
        r"(\d+)'(\d+)",               # 13'11
        r"(\d+)\"",                   # 167"
        r"(\d+\.?\d*)'",              # 13.91'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            if len(groups) == 2:
                feet, inches = int(groups[0]), int(groups[1])
                return {
                    "inches": feet * 12 + inches,
                    "raw": text,
                    "confidence": 0.95
                }
            elif len(groups) == 1:
                return {
                    "inches": int(groups[0]),
                    "raw": text,
                    "confidence": 0.85
                }
    
    return {"inches": None, "raw": text, "confidence": 0.0}
```

**3.5 — Asociación texto-geometría**
```python
def associate_text_to_room(text_elements, rooms):
    """
    Para cada cuarto detectado en OpenCV,
    encuentra el texto que está dentro de su bbox
    """
    for room in rooms:
        rx, ry, rw, rh = room["bbox"]
        room["labels"] = []
        room["dimensions"] = []
        
        for elem in text_elements:
            cx, cy = elem["center"]
            # ¿El texto está dentro del cuarto?
            if rx < cx < rx+rw and ry < cy < ry+rh:
                if elem["type"] == "room_name":
                    room["labels"].append(elem)
                elif elem["type"] == "dimension":
                    room["dimensions"].append(elem)
    
    return rooms
```

**Output del Paso 3:**
Cada cuarto tiene su nombre y dimensiones leídas con nivel de confianza por campo.

---

## PASO 4 — Comprensión con LayoutLM v3

### Objetivo
Entender la relación espacial entre texto y geometría. LayoutLM fue entrenado por Microsoft específicamente para documentos donde la posición del texto importa tanto como el texto mismo. Esto es exactamente un plano arquitectónico.

### Micro-pasos

**4.1 — Preparar input para LayoutLM**
```python
from transformers import LayoutLMv3Processor, LayoutLMv3ForTokenClassification
import torch

processor = LayoutLMv3Processor.from_pretrained(
    "microsoft/layoutlmv3-base",
    apply_ocr=False  # Ya tenemos el OCR de PaddleOCR
)

def prepare_layoutlm_input(img, text_elements):
    words = [elem["text"] for elem in text_elements]
    boxes = [normalize_bbox(elem["bbox"], img.shape) 
             for elem in text_elements]
    
    encoding = processor(
        img,
        words,
        boxes=boxes,
        return_tensors="pt",
        truncation=True,
        padding="max_length"
    )
    return encoding
```

**4.2 — Clasificación de tokens**
```python
def classify_tokens(encoding, model):
    """
    LayoutLM clasifica cada token como:
    - ROOM_NAME: nombre de cuarto
    - DIMENSION_W: dimensión de ancho
    - DIMENSION_H: dimensión de alto
    - DOOR_LABEL: etiqueta de puerta
    - WINDOW_LABEL: etiqueta de ventana
    - NOTE: nota técnica
    - OTHER
    """
    with torch.no_grad():
        outputs = model(**encoding)
    
    predictions = outputs.logits.argmax(-1)
    return predictions
```

**4.3 — Resolución de ambigüedades geométricas**
```python
def resolve_dimension_ambiguity(room, layoutlm_output):
    """
    LayoutLM ayuda a determinar cuál dimensión es ancho
    y cuál es alto basándose en el contexto espacial
    """
    dims = room["dimensions"]
    
    if len(dims) == 2:
        # Determinar cuál está más a la izquierda (ancho)
        # y cuál está más abajo (alto)
        if dims[0]["center"][0] < dims[1]["center"][0]:
            room["w_text"] = dims[0]["text"]
            room["h_text"] = dims[1]["text"]
        else:
            room["w_text"] = dims[1]["text"]
            room["h_text"] = dims[0]["text"]
    
    return room
```

**Output del Paso 4:**
Cada cuarto tiene nombre, ancho y alto correctamente identificados con nivel de confianza consolidado.

---

## PASO 5 — Claude Vision para Ambigüedades

### Objetivo
Claude Vision entra SOLO para lo que OpenCV + PaddleOCR + LayoutLM no pudieron resolver con confianza suficiente. No para todo.

### Umbral de activación
```python
CONFIDENCE_THRESHOLD = 0.85
# Si confianza < 0.85 en cualquier campo → Claude Vision lo resuelve
```

### Micro-pasos

**5.1 — Identificar campos de baja confianza**
```python
def find_low_confidence_fields(rooms: list) -> list:
    issues = []
    for room in rooms:
        for field in ["name", "w_inches", "h_inches"]:
            if room.get(f"{field}_confidence", 0) < CONFIDENCE_THRESHOLD:
                issues.append({
                    "room_id": room["id"],
                    "field": field,
                    "current_value": room.get(field),
                    "confidence": room.get(f"{field}_confidence"),
                    "crop": crop_region(room["bbox"])
                })
    return issues
```

**5.2 — Prompt quirúrgico a Claude Vision**
```python
def ask_claude_vision(issue: dict) -> dict:
    """
    No le mandamos toda la imagen.
    Le mandamos SOLO el recorte del área problemática.
    Prompt muy específico por tipo de problema.
    """
    client = anthropic.Anthropic()
    
    prompts = {
        "dimension": """
            Esta es una imagen recortada de un plano arquitectónico.
            Lee SOLO el número de dimensión visible.
            Formato de respuesta: {"value": "13'11\"", "confidence": 0.95}
            Solo JSON, sin explicación.
        """,
        "room_name": """
            Esta es una imagen recortada de un plano arquitectónico.
            Lee SOLO el nombre del cuarto visible.
            Formato de respuesta: {"value": "MASTER BEDROOM", "confidence": 0.95}
            Solo JSON, sin explicación.
        """,
        "door_swing": """
            Esta imagen muestra un arco de puerta.
            Determina la dirección del swing.
            Opciones: "cw" (clockwise) o "ccw" (counter-clockwise)
            Formato: {"value": "ccw", "confidence": 0.90}
            Solo JSON.
        """
    }
    
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": encode_crop(issue["crop"])
                }},
                {"type": "text", "text": prompts[issue["field"]]}
            ]
        }]
    )
    
    return json.loads(response.content[0].text)
```

**5.3 — Dos pasadas independientes para validación cruzada**
```python
def double_check_with_claude(issue: dict) -> dict:
    """
    Para campos críticos (dimensiones de cuartos),
    llamar a Claude dos veces con prompts ligeramente distintos.
    Si coinciden → alta confianza.
    Si difieren → va al Human in the Loop.
    """
    result_1 = ask_claude_vision(issue)
    result_2 = ask_claude_vision_v2(issue)  # Prompt alternativo
    
    if result_1["value"] == result_2["value"]:
        return {
            "value": result_1["value"],
            "confidence": max(result_1["confidence"], result_2["confidence"]),
            "verified": True
        }
    else:
        return {
            "value": None,
            "confidence": 0.0,
            "verified": False,
            "options": [result_1["value"], result_2["value"]]
        }
```

**Output del Paso 5:**
Todos los campos tienen valor y confianza. Los que Claude tampoco pudo resolver tienen `confidence: 0.0` y van al Paso 8.

---

## PASO 6 — JSON Canónico con Confianza

### Objetivo
Consolidar todos los outputs anteriores en un único JSON estructurado con nivel de confianza por campo.

### Schema del JSON canónico

```json
{
  "model": "WHITESTONE AT BABCOCK RANCH",
  "extraction_version": "1.0",
  "overall_confidence": 0.91,
  "scale": {
    "px_per_inch": 2.51,
    "confidence": 0.98
  },
  "rooms": [
    {
      "id": "room_001",
      "name": "OWNER'S SUITE",
      "name_confidence": 0.99,
      "x_px": 120,
      "y_px": 180,
      "w_px": 420,
      "h_px": 412,
      "w_inches": 167,
      "h_inches": 164,
      "w_text": "13'11\"",
      "h_text": "13'8\"",
      "w_confidence": 0.97,
      "h_confidence": 0.62,
      "doors": [
        {
          "wall": "right",
          "offset_px": 250,
          "offset_inches": 99,
          "width_inches": 36,
          "swing": "ccw",
          "swing_confidence": 0.88
        }
      ],
      "windows": [
        {
          "wall": "left",
          "offset_inches": 60,
          "width_inches": 48,
          "confidence": 0.94
        }
      ]
    }
  ],
  "fields_requiring_human": [
    {
      "room_id": "room_001",
      "field": "h_inches",
      "confidence": 0.62,
      "current_value": 164,
      "options": ["13'8\"", "13'0\""],
      "crop_s3_url": "s3://pointe-homes/crops/room_001_h.png"
    }
  ]
}
```

---

## PASO 7 — Validador Geométrico

### Objetivo
Detectar y autocorregir inconsistencias matemáticas antes de preguntar a Carlos.

### Micro-pasos

**7.1 — Verificación de suma de dimensiones**
```python
def verify_total_dimensions(rooms, detected_total):
    """
    La suma de cuartos en una fila debe igualar
    el ancho total del edificio.
    """
    row_groups = group_rooms_by_row(rooms)
    
    for row in row_groups:
        sum_widths = sum(r["w_inches"] for r in row)
        expected = detected_total["w_inches"]
        delta = abs(sum_widths - expected)
        delta_pct = delta / expected
        
        if delta_pct < 0.05:  # < 5% → autocorregir
            distribute_delta(row, delta)
        elif delta_pct < 0.15:  # 5-15% → marcar para Human Loop
            flag_for_review(row, delta)
        else:  # > 15% → error grave, pedir nueva imagen
            raise GeometryError(f"Inconsistencia grave: {delta_pct:.0%}")
```

**7.2 — Verificación de solapamientos**
```python
def check_overlaps(rooms):
    for i, a in enumerate(rooms):
        for j, b in enumerate(rooms):
            if i >= j:
                continue
            overlap = calculate_overlap(a, b)
            if overlap > 0:
                # Intentar resolver automáticamente
                # ajustando el cuarto de menor confianza
                resolve_overlap(a, b, overlap)
```

**7.3 — Verificación de continuidad de paredes**
```python
def verify_wall_continuity(rooms):
    """
    Las paredes compartidas entre cuartos adyacentes
    deben estar en la misma coordenada exacta.
    """
    adjacencies = find_adjacent_rooms(rooms)
    for a, b, shared_wall in adjacencies:
        if shared_wall == "right-left":
            # La pared derecha de A debe = pared izquierda de B
            expected = a["x"] + a["w"]
            actual = b["x"]
            if abs(expected - actual) > 1:  # > 1 inch de diferencia
                b["x"] = expected  # Alinear automáticamente
```

**Output del Paso 7:**
JSON canónico con inconsistencias geométricas resueltas automáticamente o marcadas para Human in the Loop.

---

## PASO 8 — Human in the Loop Asíncrono

### Objetivo
Presentarle a Carlos SOLO las dudas que ningún sistema pudo resolver, de forma clara y visual, sin términos técnicos.

### Arquitectura del sistema de cola

```
Pipeline detecta duda
        │
        ▼
PostgreSQL
tabla: review_queue
{id, job_id, room_id, field, 
 options, crop_url, status}
        │
        ▼
WebSocket notifica al frontend
        │
        ▼
Carlos ve la pregunta en la interfaz
        │
        ▼
Carlos responde
        │
        ▼
Pipeline continúa desde donde paró
```

### Modelo de datos
```sql
CREATE TABLE review_queue (
    id UUID PRIMARY KEY,
    job_id UUID REFERENCES jobs(id),
    room_id VARCHAR,
    field VARCHAR,           -- 'h_inches', 'name', 'door_swing'
    question TEXT,           -- Pregunta en español para Carlos
    options JSONB,           -- Opciones de respuesta
    crop_url TEXT,           -- Imagen del área problemática en S3
    status VARCHAR DEFAULT 'pending',  -- pending, answered, skipped
    answer JSONB,
    answered_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Interfaz de pregunta para Carlos

```
┌──────────────────────────────────────────┐
│  Necesito tu ayuda con 2 cosas           │
│  antes de continuar                      │
├──────────────────────────────────────────┤
│                                          │
│  Pregunta 1 de 2                         │
│  ┌────────────────────────────────────┐  │
│  │  [imagen recortada del cuarto]     │  │
│  └────────────────────────────────────┘  │
│                                          │
│  No pude leer bien esta dimensión.       │
│  ¿El Owner's Suite mide de alto:         │
│                                          │
│  ○  13'8"   (13 pies 8 pulgadas)        │
│  ○  13'0"   (13 pies exactos)           │
│  ○  Escribir otro valor: [____]          │
│                                          │
│                    [ Confirmar → ]       │
└──────────────────────────────────────────┘
```

### Tipos de preguntas posibles
```python
QUESTION_TEMPLATES = {
    "dimension": "No pude leer bien esta dimensión. ¿El {room} mide {axis}:",
    "room_name": "No pude leer el nombre de este cuarto. ¿Qué es?",
    "door_swing": "No pude determinar hacia dónde abre esta puerta del {room}.",
    "overlap": "El {room_a} y el {room_b} parecen sobreponerse. ¿Cómo los acomodo?",
    "missing_room": "Veo un espacio sin etiqueta. ¿Qué es este cuarto?"
}
```

### Sistema de aprendizaje de respuestas
```python
def save_correction_for_learning(question, answer, crop):
    """
    Cada respuesta de Carlos se guarda como ejemplo
    para mejorar las extracciones futuras.
    """
    db.corrections.insert({
        "field_type": question["field"],
        "crop_embedding": generate_embedding(crop),
        "correct_value": answer,
        "timestamp": now()
    })
    
    # La próxima vez que Claude Vision vea algo similar,
    # incluiremos este ejemplo en el prompt (few-shot)
```

**Output del Paso 8:**
JSON canónico 100% completo sin campos vacíos ni confianza baja.

---

## PASO 9 — Generación IFC

### Objetivo
Convertir el JSON canónico al formato estándar de la industria de construcción antes de generar el DWG. Esto garantiza que la geometría es 100% válida y consistente.

### Por qué IFC
- Es el formato estándar internacional para modelos de edificios (BIM)
- Fuerza la consistencia geométrica — si algo no es válido en IFC no se puede generar
- Independiente de AutoCAD — si mañana Pointe Homes quiere Revit ya tienen el modelo
- Permite validar contra códigos de construcción de forma programática

### Micro-pasos

**9.1 — Inicializar modelo IFC**
```python
import ifcopenshell
import ifcopenshell.api

def create_ifc_model():
    model = ifcopenshell.file()
    
    # Configurar unidades en pies e pulgadas
    ifcopenshell.api.run("unit.assign_unit", model, 
                          length={"is_metric": False, "raw": "INCH"})
    
    # Crear proyecto y sitio
    project = ifcopenshell.api.run("root.create_entity", model,
                                    ifc_class="IfcProject",
                                    name="Pointe Homes Floor Plan")
    
    site = ifcopenshell.api.run("root.create_entity", model,
                                 ifc_class="IfcSite")
    
    building = ifcopenshell.api.run("root.create_entity", model,
                                     ifc_class="IfcBuilding")
    
    storey = ifcopenshell.api.run("root.create_entity", model,
                                   ifc_class="IfcBuildingStorey",
                                   name="Ground Floor")
    
    return model, storey
```

**9.2 — Crear paredes desde JSON**
```python
def create_walls_from_json(model, storey, rooms):
    for room in rooms:
        # Pared inferior
        create_wall(model, storey, 
                    start=(room["x"], room["y"]),
                    end=(room["x"] + room["w"], room["y"]),
                    thickness=6,  # 6 pulgadas, estándar Pointe Homes
                    height=108)   # 9 pies, altura estándar
        
        # Pared superior, izquierda, derecha
        # (omitir paredes compartidas con cuartos adyacentes)
```

**9.3 — Crear aperturas en paredes**
```python
def create_openings(model, walls, rooms):
    for room in rooms:
        for door in room["doors"]:
            wall = find_wall(walls, room, door["wall"])
            opening = ifcopenshell.api.run(
                "root.create_entity", model,
                ifc_class="IfcOpeningElement"
            )
            # Posicionar apertura en la pared
            # Agregar IfcDoor con dimensiones correctas
        
        for window in room["windows"]:
            # Similar para ventanas (IfcWindow)
```

**9.4 — Validar el modelo IFC**
```python
def validate_ifc(model):
    from ifcopenshell.validate import validate
    
    errors = validate(model, detailed=True)
    
    if errors:
        # Clasificar errores por severidad
        critical = [e for e in errors if e.severity == "ERROR"]
        warnings = [e for e in errors if e.severity == "WARNING"]
        
        if critical:
            raise IFCValidationError(critical)
        
        return warnings
    
    return []
```

**Output del Paso 9:**
Archivo `.ifc` con el modelo del edificio 100% válido y consistente.

---

## PASO 10 — Validación de Códigos de Construcción

### Objetivo
Verificar automáticamente que el modelo cumple IRC 2021, NEC 2020 e IECC 2021 antes de generar el DWG.

### Micro-pasos

**10.1 — Base de datos de reglas**
```sql
CREATE TABLE building_codes (
    id UUID PRIMARY KEY,
    code VARCHAR,        -- 'IRC_2021', 'NEC_2020', 'IECC_2021', 'NM_TITLE14'
    rule_id VARCHAR,     -- 'R304.1', 'R311.7.1'
    description TEXT,
    element_type VARCHAR, -- 'room', 'corridor', 'door', 'window'
    measurement VARCHAR,  -- 'min_area', 'min_width', 'min_height'
    value_inches DECIMAL,
    applies_to_states VARCHAR[]  -- ['TX', 'NM'] o ['ALL']
);
```

**10.2 — Reglas mínimas cargadas**
```python
RULES = {
    "IRC_2021_R304.1": {
        "description": "Área mínima de habitaciones",
        "applies_to": ["bedroom", "living", "dining"],
        "min_area_sqft": 70,
        "min_width_inches": 84
    },
    "IRC_2021_R311.2": {
        "description": "Ancho mínimo de pasillo",
        "applies_to": ["corridor", "hallway"],
        "min_width_inches": 36
    },
    "IRC_2021_R311.3": {
        "description": "Ancho mínimo de puerta de entrada",
        "applies_to": ["entry_door"],
        "min_width_inches": 32
    },
    "IRC_2021_R305.1": {
        "description": "Altura mínima de techo",
        "applies_to": ["all_rooms"],
        "min_height_inches": 84
    }
}
```

**10.3 — Validador**
```python
def validate_against_codes(ifc_model, state: str) -> dict:
    violations = []
    warnings = []
    
    rooms = extract_rooms_from_ifc(ifc_model)
    
    for room in rooms:
        applicable_rules = get_rules_for_room(room["type"], state)
        
        for rule in applicable_rules:
            result = check_rule(room, rule)
            
            if result["status"] == "VIOLATION":
                violations.append({
                    "room": room["name"],
                    "rule": rule["id"],
                    "description": rule["description"],
                    "actual": result["actual"],
                    "required": result["required"],
                    "auto_fixable": result["auto_fixable"]
                })
            elif result["status"] == "WARNING":
                warnings.append(result)
    
    return {"violations": violations, "warnings": warnings}
```

**10.4 — Autocorrección de violaciones simples**
```python
def auto_fix_violations(ifc_model, violations):
    for v in violations:
        if v["auto_fixable"]:
            if v["rule"] == "IRC_2021_R304.1":
                # Expandir el cuarto al mínimo requerido
                expand_room_to_minimum(ifc_model, v["room"])
            elif v["rule"] == "IRC_2021_R311.2":
                # Ampliar pasillo
                widen_corridor(ifc_model, v["room"])
```

**Output del Paso 10:**
IFC validado contra códigos. Violaciones críticas corregidas o reportadas.

---

## PASO 11 — Generación DWG con Estilo Pointe Homes

### Objetivo
Convertir el IFC validado al DWG final con el estilo exacto de Pointe Homes usando los bloques reales extraídos del Seminole 2000.

### Prerequisito crítico
Antes de construir este paso, Rentería debe exportar una plantilla `.DWT` del Seminole 2000 con:
- Todos los bloques: puerta interior, puerta principal, ventana, baño, cocina, garage
- Todos los estilos de texto: ARCHITXT y los 9 estilos identificados
- Todos los estilos de cota: los 3 estilos identificados
- Todos los tipos de línea: los 15 tipos identificados
- Las 52 capas con sus propiedades exactas

### Micro-pasos

**11.1 — Cargar plantilla DWT**
```python
import ezdxf

def load_pointe_homes_template():
    doc = ezdxf.readfile("pointe_homes_template.dwt")
    return doc
```

**11.2 — Crear nuevo documento desde plantilla**
```python
def create_drawing_from_template(template_path: str):
    doc = ezdxf.readfile(template_path)
    msp = doc.modelspace()
    # Borrar contenido pero mantener capas, bloques y estilos
    msp.delete_all_entities()
    return doc, msp
```

**11.3 — Dibujar paredes desde IFC**
```python
def draw_walls(msp, rooms):
    for room in rooms:
        x, y, w, h = room["x"], room["y"], room["w"], room["h"]
        
        # Cada pared = dos líneas paralelas (pared doble de 6")
        WALL_THICKNESS = 6  # pulgadas
        
        walls_to_draw = get_walls_to_draw(room, rooms)
        
        for wall in walls_to_draw:
            # Línea exterior
            msp.add_line(
                wall["start_outer"],
                wall["end_outer"],
                dxfattribs={"layer": "WALLS", "lineweight": 60}
            )
            # Línea interior
            msp.add_line(
                wall["start_inner"],
                wall["end_inner"],
                dxfattribs={"layer": "WALLS", "lineweight": 60}
            )
```

**11.4 — Insertar bloques de puertas**
```python
def insert_doors(msp, rooms, doc):
    DOOR_BLOCKS = {
        36: "DOOR_36",   # Puerta 3 pies (entrada, master)
        32: "DOOR_32",   # Puerta 2'8" (dormitorios)
        28: "DOOR_28",   # Puerta 2'4" (baños)
        "garage": "DOOR_GARAGE"
    }
    
    for room in rooms:
        for door in room["doors"]:
            block_name = DOOR_BLOCKS.get(door["width_inches"], "DOOR_32")
            
            # Calcular posición y rotación del bloque
            position, rotation = calculate_door_transform(room, door)
            
            msp.add_blockref(
                block_name,
                insert=position,
                dxfattribs={
                    "layer": "DOORS",
                    "rotation": rotation,
                    "xscale": 1,
                    "yscale": 1 if door["swing"] == "ccw" else -1
                }
            )
```

**11.5 — Insertar bloques de ventanas**
```python
def insert_windows(msp, rooms):
    for room in rooms:
        for window in room["windows"]:
            position, rotation = calculate_window_transform(room, window)
            
            # Ventana = 3 líneas perpendiculares a la pared
            # en capa WINS con color verde (3)
            draw_window_symbol(msp, position, rotation, 
                             window["width_inches"])
```

**11.6 — Insertar fixtures de baños**
```python
def insert_bathroom_fixtures(msp, rooms, doc):
    BATHROOM_BLOCKS = {
        "toilet": "FIXTURE_TOILET",
        "tub": "FIXTURE_TUB",
        "shower": "FIXTURE_SHOWER",
        "vanity_single": "FIXTURE_VANITY_S",
        "vanity_double": "FIXTURE_VANITY_D"
    }
    
    bathrooms = [r for r in rooms if "bath" in r["name"].lower()]
    for bathroom in bathrooms:
        # Posicionar fixtures según el tamaño del baño
        fixtures = determine_fixtures(bathroom)
        for fixture in fixtures:
            msp.add_blockref(
                BATHROOM_BLOCKS[fixture["type"]],
                insert=fixture["position"],
                dxfattribs={"layer": "FIXTURES"}
            )
```

**11.7 — Agregar dimensiones**
```python
def add_dimensions(msp, rooms, doc):
    dim_style = doc.dimstyles.get("ARCH_DIM")  # Estilo Pointe Homes
    
    # Dimensiones exteriores del edificio
    add_exterior_dimensions(msp, rooms, dim_style)
    
    # Dimensiones de cada cuarto
    for room in rooms:
        # Dimensión de ancho
        msp.add_linear_dim(
            base=(room["x"], room["y"] - 24),  # 2 pies debajo
            p1=(room["x"], room["y"]),
            p2=(room["x"] + room["w"], room["y"]),
            dxfattribs={"layer": "DIMS", "dimstyle": "ARCH_DIM"}
        ).render()
        
        # Dimensión de alto
        msp.add_linear_dim(
            base=(room["x"] - 24, room["y"]),
            p1=(room["x"], room["y"]),
            p2=(room["x"], room["y"] + room["h"]),
            angle=90,
            dxfattribs={"layer": "DIMS", "dimstyle": "ARCH_DIM"}
        ).render()
```

**11.8 — Agregar etiquetas de cuartos**
```python
def add_room_labels(msp, rooms):
    for room in rooms:
        center_x = room["x"] + room["w"] / 2
        center_y = room["y"] + room["h"] / 2
        
        # Nombre del cuarto en mayúsculas
        msp.add_text(
            room["name"],
            dxfattribs={
                "layer": "ROOM LBLS",
                "style": "ARCHITXT",
                "height": 9,  # 9 pulgadas, estándar Pointe Homes
                "color": 2    # Amarillo
            }
        ).set_placement(
            (center_x, center_y + 6),
            align=TextEntityAlignment.CENTER
        )
        
        # Dimensión debajo del nombre
        dim_text = f"{room['w_text']} x {room['h_text']}"
        msp.add_text(
            dim_text,
            dxfattribs={
                "layer": "ROOM LBLS",
                "style": "ARCHITXT",
                "height": 7,
                "color": 2
            }
        ).set_placement(
            (center_x, center_y - 4),
            align=TextEntityAlignment.CENTER
        )
```

**11.9 — Guardar DWG**
```python
def save_dwg(doc, output_path: str):
    doc.saveas(output_path)
    
    # También guardar en S3
    s3_client.upload_file(output_path, 
                          "pointe-homes-dwg",
                          f"generated/{Path(output_path).name}")
```

**Output del Paso 11:**
Archivo `.DWG` con estilo visual idéntico al Seminole 2000 original.

---

## PASO 12 — Verificación Visual con MCP + AutoCAD

### Objetivo
Abrir el DWG generado en AutoCAD, tomar un screenshot, y hacer una comparación visual automática contra la imagen original para detectar errores obvios antes de entregar a Carlos.

### Micro-pasos

**12.1 — Abrir DWG en AutoCAD via MCP**
```python
async def open_in_autocad(dwg_path: str):
    result = await mcp_client.call_tool(
        "drawing",
        {"operation": "open", "path": dwg_path}
    )
    
    # Zoom extents para ver todo el plano
    await mcp_client.call_tool(
        "view",
        {"operation": "zoom_extents"}
    )
```

**12.2 — Tomar screenshot**
```python
async def capture_result():
    screenshot = await mcp_client.call_tool(
        "view",
        {"operation": "get_screenshot"}
    )
    return screenshot["image_data"]  # Base64 PNG
```

**12.3 — Comparación automática con Claude Vision**
```python
def compare_original_vs_generated(original_img, generated_screenshot):
    client = anthropic.Anthropic()
    
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/png",
                    "data": encode(original_img)
                }},
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/png",
                    "data": encode(generated_screenshot)
                }},
                {"type": "text", "text": """
                    Compara estos dos floor plans.
                    El primero es el original. El segundo es el generado.
                    Lista SOLO las diferencias importantes de layout.
                    Formato: {"match_score": 0.92, "differences": [...]}
                    Solo JSON.
                """}
            ]
        }]
    )
    
    return json.loads(response.content[0].text)
```

**12.4 — Presentar resultado final a Carlos**
```
┌────────────────────────────────────────────┐
│  ✓ Plano generado correctamente            │
├──────────────────┬─────────────────────────┤
│  Original        │  Generado en AutoCAD    │
│  [imagen]        │  [screenshot]           │
├──────────────────┴─────────────────────────┤
│  Similitud: 94%                            │
│                                            │
│  ⚠ Una diferencia detectada:              │
│  El closet del Master aparece más angosto  │
│                                            │
│  [ Aceptar y descargar DWG ]               │
│  [ Corregir este detalle ]                 │
└────────────────────────────────────────────┘
```

---

## Estructura de Archivos del Proyecto

```
sistema1/
├── pipeline/
│   ├── step1_preprocess.py
│   ├── step2_opencv_geometry.py
│   ├── step3_paddleocr_text.py
│   ├── step4_layoutlm.py
│   ├── step5_claude_vision.py
│   ├── step6_canonical_json.py
│   ├── step7_geometry_validator.py
│   ├── step8_human_loop.py
│   ├── step9_ifc_generator.py
│   ├── step10_code_validator.py
│   ├── step11_dwg_generator.py
│   └── step12_autocad_verify.py
├── templates/
│   └── pointe_homes_base.dwt      ← Pendiente: Rentería exporta esto
├── blocks/
│   ├── doors/
│   ├── windows/
│   ├── fixtures/
│   └── electrical/
├── rules/
│   ├── irc_2021.json
│   ├── nec_2020.json
│   ├── iecc_2021.json
│   └── nm_title14.json
├── api/
│   ├── main.py                    ← FastAPI
│   ├── routes/
│   └── websocket/
├── frontend/
│   └── src/
│       ├── Upload.tsx
│       ├── Progress.tsx
│       ├── HumanLoop.tsx          ← Interfaz de preguntas a Carlos
│       └── Preview.tsx
└── db/
    ├── migrations/
    └── models/
```

---

## Lo que se Necesita de Pointe Homes para Arrancar

| Entregable | Quién | Urgencia |
|-----------|-------|---------|
| Plantilla `.DWT` del Seminole 2000 | Rentería | Crítico — bloquea Paso 11 |
| Lista de bloques estándar | Rentería | Crítico |
| Reglas mínimas de diseño escritas | Rentería | Alto |
| 5 imágenes de planos de prueba variados | Carlos V | Alto |
| Credenciales AWS S3 o alternativa | Carlos V | Medio |

---

## Señal de Éxito del Sistema 1

Carlos sube una imagen de un plano de constructor nacional. El sistema genera un DWG en AutoCAD que:

1. Tiene todas las capas con los nombres correctos de Pointe Homes
2. Las paredes son dobles con grosor de 6 pulgadas
3. Las puertas usan los bloques reales con su arco de swing correcto
4. Las dimensiones usan el estilo ARCHITXT
5. La similitud visual con el original es mayor al 90%
6. No viola ninguna regla del IRC 2021

Todo en menos de 5 minutos desde que Carlos sube la imagen.
