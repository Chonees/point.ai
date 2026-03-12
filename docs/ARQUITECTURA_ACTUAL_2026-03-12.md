# Arquitectura Sistema 1 — Point.ai (Implementacion Actual)

**Fecha:** 2026-03-12
**Version:** 1.0
**Empresa:** Pointe Homes

---

## Flujo General

```
Usuario escribe prompt en el browser
        |
   index.html (frontend)
        | POST /api/generate
   app.py (FastAPI backend)
        | llama Claude API
   Claude devuelve JSON (floor plan)
        | pasa el JSON a...
   generator.py (orchestrator)
        | usa los components/
   primitives -> layers -> walls -> doors -> windows -> labels
        |
   Archivo .dxf guardado en disco
        | GET /downloads/xxx.dxf
   Usuario descarga el DXF
```

---

## 1. PRIMITIVES — `scripts/components/primitives.py`

La capa mas baja. Son wrappers de 1 linea sobre ezdxf para no repetir la sintaxis fea de ezdxf en todos lados.

### `add_line` (linea 9-10)

```python
def add_line(msp, x1, y1, x2, y2, layer):
    msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": layer})
```

Dibuja una linea entre dos puntos en un layer. `msp` es el modelspace (el "lienzo" del DXF). `dxfattribs={"layer": layer}` le dice a que capa pertenece.

### `add_arc` (lineas 13-20)

```python
def add_arc(msp, cx, cy, radius, start_angle, end_angle, layer):
    msp.add_arc(
        center=(cx, cy),
        radius=radius,
        start_angle=start_angle,
        end_angle=end_angle,
        dxfattribs={"layer": layer}
    )
```

Dibuja un arco (usado para el swing de puertas). `cx,cy` = centro, `radius` = radio, angulos en grados.

### `add_text` (lineas 23-25)

```python
def add_text(msp, x, y, text, height, layer):
    t = msp.add_text(text, dxfattribs={"layer": layer, "height": height})
    t.set_placement((x, y), align=TextEntityAlignment.MIDDLE_CENTER)
```

Texto centrado. `TextEntityAlignment.MIDDLE_CENTER` lo centra horizontal y verticalmente en el punto dado.

### `add_hatch_rect` (lineas 28-35)

```python
def add_hatch_rect(msp, x1, y1, x2, y2):
    """Relleno SOLID entre dos caras de pared (rectangulo)."""
    hatch = msp.add_hatch(color=colors.BYLAYER, dxfattribs={"layer": "HATCH"})
    hatch.set_pattern_fill("SOLID")
    hatch.paths.add_polyline_path(
        [(x1, y1), (x2, y1), (x2, y2), (x1, y2)],
        is_closed=True
    )
```

Relleno solido rectangular. Crea un poligono cerrado con patron "SOLID". Se usa para rellenar las paredes entre las dos lineas paralelas.

**Por que existe:** Sin esto, cada componente tendria que escribir `msp.add_line((x1,y1), (x2,y2), dxfattribs={"layer": "WALLS"})` completo. Con primitives escribis `add_line(msp, x1, y1, x2, y2, "WALLS")`.

---

## 2. LAYERS — `scripts/components/layers.py`

La configuracion compartida del documento DXF.

### `LAYERS` (lineas 8-24)

```python
LAYERS = {
    "WALLS":            {"color": 7,   "lineweight": 60},
    "DOORS":            {"color": 157, "lineweight": 9},
    "WINS":             {"color": 121, "lineweight": -3},
    "DIMS":             {"color": 137, "lineweight": 15},
    "HATCH":            {"color": 123, "lineweight": 0},
    "FIXTURES":         {"color": 2,   "lineweight": 15},
    "ROOM LBLS":        {"color": 253, "lineweight": 30},
    "TEXT LBLS":        {"color": 81,  "lineweight": 18},
    "TEXT":             {"color": 7,   "lineweight": -3},
    "DOORTEXT":         {"color": 253, "lineweight": 20},
    "CABS-FLOORPLAN":   {"color": 4,   "lineweight": -3},
    "HEADERS":          {"color": 7,   "lineweight": 50},
    "ELECTRICAL":       {"color": 164, "lineweight": -3},
    "ELECTRICAL WALLS": {"color": 65,  "lineweight": 9},
    "MISC":             {"color": 3,   "lineweight": 30},
}
```

Diccionario con los 15 layers de Pointe Homes, extraidos del Seminole 2000 real. Cada layer tiene:
- `color`: numero de color AutoCAD (7=blanco, 157=violeta para puertas, 121=verde para ventanas, etc.)
- `lineweight`: grosor de linea en centesimas de mm (60 = 0.60mm, -3 = default)

### `setup_doc()` (lineas 27-41)

```python
def setup_doc():
    """Create DXF document with all Pointe Homes layers. Returns (doc, msp)."""
    doc = ezdxf.new("R2018")
    doc.units = 1  # inches

    msp = doc.modelspace()

    for name, props in LAYERS.items():
        layer = doc.layers.new(name=name)
        layer.color = props["color"]
        lw = props["lineweight"]
        if lw > 0:
            layer.lineweight = lw

    return doc, msp
```

Crea un documento DXF nuevo:
- `ezdxf.new("R2018")` — formato AutoCAD 2018 (compatible con AutoCAD LT 2026)
- `doc.units = 1` — unidades en pulgadas (estandar Pointe Homes: 1 unit = 1 inch)
- Loop que crea cada layer con su color y lineweight
- Retorna `(doc, msp)` — el documento y su modelspace

**Por que existe separado:** Es el UNICO config compartido. Todos los demas componentes tienen sus propios standards. Pero `setup_doc()` necesita crear TODOS los layers de una vez cuando inicia el documento.

---

## 3. WALLS — `scripts/components/walls.py`

El componente mas complejo. Tiene 3 capas: standards, dibujo, y orquestacion.

### Standards (lineas 15-18)

```python
THICKNESS = 4      # inches — two parallel LINEs 4" apart
LINEWEIGHT = 60    # 0.60mm
COLOR = 7
LAYER = "WALLS"
```

`THICKNESS` es la constante mas importante — `doors.py` y `windows.py` la importan porque puertas y ventanas existen DENTRO de las paredes.

### Dibujo

#### `draw_wall_h` (lineas 23-35)

```python
def draw_wall_h(msp, x1, x2, y, gaps=None):
    resolved_gaps = gaps or []
    segments = split_segments(x1, x2, resolved_gaps)
    for sx1, sx2 in segments:
        add_line(msp, sx1, y,              sx2, y,              LAYER)
        add_line(msp, sx1, y + THICKNESS,  sx2, y + THICKNESS,  LAYER)
    for gx1, gx2 in resolved_gaps:
        add_line(msp, gx1, y, gx1, y + THICKNESS, LAYER)
        add_line(msp, gx2, y, gx2, y + THICKNESS, LAYER)
```

Pared horizontal doble con end caps en cada abertura:
- Recibe `gaps` = lista de `(gx1, gx2)` para puertas/ventanas
- `split_segments` parte la pared en segmentos continuos evitando los huecos
- Por cada segmento: dibuja 2 lineas paralelas (a `y` y a `y+4`)
- Por cada gap: dibuja 2 end caps verticales (las lineas cortas que cierran el hueco)

#### `draw_wall_v` (lineas 38-50)

```python
def draw_wall_v(msp, x, y1, y2, gaps=None):
    resolved_gaps = gaps or []
    segments = split_segments(y1, y2, resolved_gaps)
    for sy1, sy2 in segments:
        add_line(msp, x,              sy1, x,              sy2, LAYER)
        add_line(msp, x + THICKNESS,  sy1, x + THICKNESS,  sy2, LAYER)
    for gy1, gy2 in resolved_gaps:
        add_line(msp, x, gy1, x + THICKNESS, gy1, LAYER)
        add_line(msp, x, gy2, x + THICKNESS, gy2, LAYER)
```

Igual pero vertical. 2 lineas a `x` y `x+4`, end caps horizontales.

### Utilidades

#### `split_segments` (lineas 55-67)

```python
def split_segments(start, end, gaps):
    if not gaps:
        return [(start, end)]
    result = []
    cur = start
    for g1, g2 in sorted(gaps):
        if cur < g1:
            result.append((cur, g1))
        cur = g2
    if cur < end:
        result.append((cur, end))
    return result
```

Algoritmo simple:
- Ordena los gaps por posicion
- Recorre de izquierda a derecha: si hay espacio antes del gap, agrega segmento
- Si hay espacio despues del ultimo gap, agrega segmento final

Ejemplo: pared de 0 a 300 con gap `(100, 136)` -> segmentos `[(0, 100), (136, 300)]`

#### `merge_spans` (lineas 70-89)

```python
def merge_spans(spans_with_gaps):
    if not spans_with_gaps:
        return []
    items = sorted(spans_with_gaps, key=lambda t: t[0])
    cs, ce, cg = items[0][0], items[0][1], list(items[0][2])
    merged = []
    for s, e, g in items[1:]:
        if s <= ce:
            ce = max(ce, e)
            cg.extend(g)
        else:
            merged.append((cs, ce, cg))
            cs, ce, cg = s, e, list(g)
    merged.append((cs, ce, cg))
    return merged
```

Cuando dos rooms comparten la misma pared horizontal (ej: BED1 y BED2 tienen su top wall en el mismo `y=704`), hay 2 spans en esa coordenada Y. Este merge los junta en uno solo combinando sus gaps. Algoritmo clasico de merge de intervalos solapados.

### Orquestacion

#### `collect_walls` (lineas 94-129)

```python
def collect_walls(rooms):
    T = THICKNESS
    h_walls = defaultdict(list)
    v_walls = defaultdict(list)

    for room in rooms:
        rx, ry, rw, rh = room["x"], room["y"], room["w"], room["h"]

        gaps = {"bottom": [], "top": [], "left": [], "right": []}

        for d in room.get("doors", []):
            off, w, wall = d["offset"], d["width"], d["wall"]
            if wall in ("bottom", "top"):
                gaps[wall].append((rx + off, rx + off + w))
            else:
                gaps[wall].append((ry + off, ry + off + w))

        for wn in room.get("windows", []):
            off, w, wall = wn["offset"], wn["width"], wn["wall"]
            if wall in ("bottom", "top"):
                gaps[wall].append((rx + off, rx + off + w))
            else:
                gaps[wall].append((ry + off, ry + off + w))

        h_walls[ry     ].append((rx,       rx + rw,     gaps["bottom"]))
        h_walls[ry + rh].append((rx,       rx + rw,     gaps["top"]))
        v_walls[rx     ].append((ry + T,   ry + rh - T, gaps["left"]))
        v_walls[rx+rw-T].append((ry + T,   ry + rh - T, gaps["right"]))

    return h_walls, v_walls
```

**Phase 1** del pipeline:
- Recorre cada room del JSON
- Extrae los gaps de sus puertas y ventanas
- Registra 4 paredes por room en diccionarios indexados por coordenada:
  - `h_walls[ry]` = pared bottom en coordenada Y = ry
  - `h_walls[ry+rh]` = pared top
  - `v_walls[rx]` = pared left (nota: `ry+T` a `ry+rh-T` porque las esquinas las cubren las h_walls)
  - `v_walls[rx+rw-T]` = pared right (empezando en `rw-T` porque la pared tiene 4" de grosor hacia adentro)

#### `dedup_walls` (lineas 132-152)

```python
def dedup_walls(v_walls):
    T = THICKNESS
    sorted_x = sorted(v_walls.keys())
    to_remove = set()
    for i in range(len(sorted_x) - 1):
        x1 = sorted_x[i]
        x2 = sorted_x[i + 1]
        if x2 - x1 == T and x1 not in to_remove:
            spans1 = [(s, e) for s, e, _ in v_walls[x1]]
            spans2 = [(s, e) for s, e, _ in v_walls[x2]]
            if any(s1 < e2 and s2 < e1 for s1, e1 in spans1 for s2, e2 in spans2):
                v_walls[x2].extend(v_walls[x1])
                to_remove.add(x1)
    for x in to_remove:
        del v_walls[x]
    return v_walls
```

**Phase 1b**, resuelve el problema de paredes dobles:

Cuando BED1 (`x=0, w=190`) esta al lado de BED2 (`x=190, w=190`):
- BED1.right -> v_wall en `x=186` (190-4)
- BED2.left -> v_wall en `x=190`
- Diferencia = 4 = THICKNESS -> son la misma pared vista desde dos rooms

El algoritmo: ordena todas las X, busca pares donde `x2 - x1 == 4`, verifica que los Y-spans se solapan (no son paredes en pisos diferentes), y fusiona ambas en una sola en la posicion `x2`.

#### `draw_all_walls` (lineas 155-163)

```python
def draw_all_walls(msp, h_walls, v_walls):
    for y, spans in h_walls.items():
        for x1, x2, merged_gaps in merge_spans(spans):
            draw_wall_h(msp, x1, x2, y, gaps=merged_gaps)

    for x, spans in v_walls.items():
        for y1, y2, merged_gaps in merge_spans(spans):
            draw_wall_v(msp, x, y1, y2, gaps=merged_gaps)
```

**Phase 2**: recorre cada pared, llama `merge_spans` para combinar segmentos solapados, y dibuja con `draw_wall_h`/`draw_wall_v`.

---

## 4. DOORS — `scripts/components/doors.py`

### Standards (lineas 19-21)

```python
SLAB_THICKNESS = 1.5   # inches
SWING_ANGLE = 90       # degrees
LAYER = "DOORS"
```

### `draw_door` (lineas 26-48)

```python
def draw_door(msp, hx, hy, width, direction="up"):
    DS = SLAB_THICKNESS
    if direction == "up":
        add_line(msp, hx,      hy, hx,      hy + width, LAYER)
        add_line(msp, hx + DS, hy, hx + DS, hy + width, LAYER)
        add_arc(msp, hx, hy, width, 0, 90, LAYER)
    elif direction == "down":
        add_line(msp, hx,      hy, hx,      hy - width, LAYER)
        add_line(msp, hx + DS, hy, hx + DS, hy - width, LAYER)
        add_arc(msp, hx, hy, width, 270, 360, LAYER)
    elif direction == "right":
        add_line(msp, hx, hy,      hx + width, hy,      LAYER)
        add_line(msp, hx, hy + DS, hx + width, hy + DS, LAYER)
        add_arc(msp, hx, hy, width, 0, 90, LAYER)
    elif direction == "left":
        add_line(msp, hx, hy,      hx - width, hy,      LAYER)
        add_line(msp, hx, hy + DS, hx - width, hy + DS, LAYER)
        add_arc(msp, hx, hy, width, 90, 180, LAYER)
```

Puerta completa:
- `hx, hy` = punto de bisagra (donde la puerta esta fijada a la pared)
- 2 lineas paralelas separadas 1.5" = la hoja de la puerta
- 1 arco de 90 grados = el swing (el recorrido que hace al abrirse)

4 direcciones:
- `up`: puerta en pared bottom, se abre hacia arriba (arco 0->90)
- `down`: puerta en pared top, se abre hacia abajo (arco 270->360)
- `right`: puerta en pared left, se abre hacia derecha (arco 0->90)
- `left`: puerta en pared right, se abre hacia izquierda (arco 90->180)

### `draw_doors_for_room` (lineas 53-71)

```python
def draw_doors_for_room(msp, room):
    T = THICKNESS
    rx, ry, rw, rh = room["x"], room["y"], room["w"], room["h"]

    for d in room.get("doors", []):
        off  = d["offset"]
        w    = d["width"]
        wall = d["wall"]
        if d.get("type") == "garage":
            continue
        if wall == "bottom":
            draw_door(msp, rx + off, ry + T, w, "up")
        elif wall == "top":
            draw_door(msp, rx + off, ry + rh - T, w, "down")
        elif wall == "left":
            draw_door(msp, rx + T, ry + off, w, "right")
        elif wall == "right":
            draw_door(msp, rx + rw - T, ry + off, w, "left")
```

Convierte el JSON del room a llamadas `draw_door`:
- Puertas `type: "garage"` se **SALTAN** (solo dejan el hueco en la pared)
- Calcula el punto de bisagra desde el offset:
  - `bottom`: bisagra en `(rx+offset, ry+T)` — T=4 porque la bisagra esta en la cara interior
  - `top`: bisagra en `(rx+offset, ry+rh-T)` — cara interior del top
  - `left`: bisagra en `(rx+T, ry+offset)` — cara interior del left
  - `right`: bisagra en `(rx+rw-T, ry+offset)` — cara interior del right

---

## 5. WINDOWS — `scripts/components/windows.py`

### Standards (lineas 20-23)

```python
LAYER = "WINS"
H_SILL_OFFSET = 5     # inches — horizontal exterior sill distance
V_SILL_OUT = 1         # inches — vertical exterior sill distance
V_SILL_IN = 6          # inches — vertical interior sill distance
```

### Patron Seminole 2000

Cada ventana tiene 6 lineas:

1. **Sill exterior** — linea alejada de la pared (la repisa exterior)
2. **Cara exterior** — la linea de la pared donde esta el vidrio
3. **Linea +1"** — 1 pulgada hacia afuera
4. **Linea +2"** — 2 pulgadas hacia afuera (las 3 lineas = el vidrio doble)
5. **End cap izquierdo** — tapa de 1" conectando lineas +1 y +2
6. **End cap derecho** — tapa de 1" conectando lineas +1 y +2

La regla clave: las 3 lineas SIEMPRE miran hacia AFUERA (hacia el exterior de la casa).

### `draw_window_h` (lineas 28-46)

```python
def draw_window_h(msp, x, y, width, side="bottom"):
    L = LAYER
    if side == "bottom":
        add_line(msp, x, y-5,   x+width, y-5,   L)   # sill exterior
        add_line(msp, x, y,     x+width, y,     L)   # cara exterior
        add_line(msp, x, y-1,   x+width, y-1,   L)   # -1" (hacia afuera)
        add_line(msp, x, y-2,   x+width, y-2,   L)   # -2" (hacia afuera)
        add_line(msp, x,       y-1, x,       y-2, L)  # end cap izq
        add_line(msp, x+width, y-1, x+width, y-2, L)  # end cap der
    else:  # top
        add_line(msp, x, y+5,   x+width, y+5,   L)   # sill exterior
        add_line(msp, x, y,     x+width, y,     L)   # cara exterior
        add_line(msp, x, y+1,   x+width, y+1,   L)   # +1" (hacia afuera)
        add_line(msp, x, y+2,   x+width, y+2,   L)   # +2" (hacia afuera)
        add_line(msp, x,       y+1, x,       y+2, L)  # end cap izq
        add_line(msp, x+width, y+1, x+width, y+2, L)  # end cap der
```

- `side="bottom"`: exterior = abajo -> lineas van hacia -Y (y, y-1, y-2), sill en y-5
- `side="top"`: exterior = arriba -> lineas van hacia +Y (y, y+1, y+2), sill en y+5

### `draw_window_v` (lineas 49-66)

```python
def draw_window_v(msp, x, y, width, side="left"):
    L = LAYER
    T = THICKNESS
    if side == "left":
        add_line(msp, x-1, y,        x-1, y+width, L)  # sill exterior 1" afuera
        add_line(msp, x,   y,        x,   y+width, L)  # cara exterior
        add_line(msp, x+1, y,        x+1, y+width, L)  # +1"
        add_line(msp, x+6, y,        x+6, y+width, L)  # sill interior
        add_line(msp, x-1, y,        x,   y,       L)  # end cap bottom
        add_line(msp, x-1, y+width,  x,   y+width, L)  # end cap top
    else:  # right
        add_line(msp, x+T+1, y,       x+T+1, y+width, L)  # sill exterior 1" afuera
        add_line(msp, x+T,   y,       x+T,   y+width, L)  # cara exterior
        add_line(msp, x+T-1, y,       x+T-1, y+width, L)  # -1"
        add_line(msp, x-2,   y,       x-2,   y+width, L)  # sill interior
        add_line(msp, x+T,   y,       x+T+1, y,       L)  # end cap bottom
        add_line(msp, x+T,   y+width, x+T+1, y+width, L)  # end cap top
```

- `side="left"`: exterior = izquierda -> lineas en x-1, x, x+1, sill exterior en x-1, sill interior en x+6
- `side="right"`: exterior = derecha -> lineas en x+T+1, x+T, x+T-1, sill interior en x-2

### `draw_windows_for_room` (lineas 71-83)

```python
def draw_windows_for_room(msp, room):
    T = THICKNESS
    rx, ry, rw, rh = room["x"], room["y"], room["w"], room["h"]

    for wn in room.get("windows", []):
        off  = wn["offset"]
        w    = wn["width"]
        wall = wn["wall"]
        if wall == "bottom":   draw_window_h(msp, rx + off, ry, w, side="bottom")
        elif wall == "top":    draw_window_h(msp, rx + off, ry + rh, w, side="top")
        elif wall == "left":   draw_window_v(msp, rx, ry + off, w, side="left")
        elif wall == "right":  draw_window_v(msp, rx + rw - T, ry + off, w, side="right")
```

Convierte JSON a llamadas `draw_window`:
- `bottom` -> `draw_window_h(x=rx+offset, y=ry, side="bottom")`
- `top` -> `draw_window_h(x=rx+offset, y=ry+rh, side="top")`
- `left` -> `draw_window_v(x=rx, y=ry+offset, side="left")`
- `right` -> `draw_window_v(x=rx+rw-T, y=ry+offset, side="right")`

---

## 6. LABELS — `scripts/components/labels.py`

El mas simple. Texto centrado con el nombre del cuarto.

```python
ROOM_LABEL_HEIGHT = 9  # inches
DIM_TEXT_HEIGHT = 6     # inches
LAYER = "ROOM LBLS"

def draw_label(msp, cx, cy, name):
    add_text(msp, cx, cy, name, ROOM_LABEL_HEIGHT, LAYER)
```

- `ROOM_LABEL_HEIGHT = 9` — 9 pulgadas de alto (legible en un plano a escala)
- `draw_label(msp, cx, cy, name)` — pone el texto en el centro del room

---

## 7. `__init__.py` — `scripts/components/__init__.py`

```python
from .layers import setup_doc, LAYERS
from .walls import (
    collect_walls, dedup_walls, draw_all_walls,
    draw_wall_h, draw_wall_v, THICKNESS,
)
from .doors import draw_door, draw_doors_for_room
from .windows import draw_window_h, draw_window_v, draw_windows_for_room
from .labels import draw_label
```

Re-exporta todo para que desde afuera puedas hacer `from components import setup_doc, draw_label` sin saber en que archivo vive cada cosa.

---

## 8. GENERATOR — `scripts/generator.py`

El orquestador. ~95 lineas, casi todo es el `TEST_HOUSE` de prueba.

### `generate()` (lineas 18-36)

```python
def generate(floor_plan: dict, out_path: str):
    doc, msp = setup_doc()

    # Phase 1: Collect + deduplicate walls
    h_walls, v_walls = collect_walls(floor_plan["rooms"])
    v_walls = dedup_walls(v_walls)

    # Phase 2: Draw walls
    draw_all_walls(msp, h_walls, v_walls)

    # Phase 3: Doors, windows, labels
    for room in floor_plan["rooms"]:
        draw_doors_for_room(msp, room)
        draw_windows_for_room(msp, room)
        draw_label(msp, room["x"] + room["w"] / 2, room["y"] + room["h"] / 2, room["name"])

    doc.saveas(out_path)
    print(f"Saved: {out_path}")
```

Pipeline:
1. `setup_doc()` — crea DXF vacio con layers
2. `collect_walls()` — registra paredes de cada room
3. `dedup_walls()` — elimina paredes dobles entre rooms adyacentes
4. `draw_all_walls()` — dibuja las paredes con gaps
5. Loop por cada room — dibuja puertas, ventanas, labels
6. `doc.saveas()` — guarda el .dxf

### `TEST_HOUSE` (lineas 41-85)

```python
TEST_HOUSE = {
    "model": "Test House",
    "rooms": [
        {"name": "GARAGE 1", "x": 0, "y": 0, "w": 380, "h": 248,
         "doors": [{"wall": "bottom", "offset": 40, "width": 144, "type": "garage"}]},
        {"name": "GARAGE 2", "x": 380, "y": 0, "w": 380, "h": 248,
         "doors": [{"wall": "bottom", "offset": 40, "width": 144, "type": "garage"}]},
        {"name": "LIVING", "x": 0, "y": 248, "w": 760, "h": 252,
         "doors": [{"wall": "bottom", "offset": 160, "width": 36}],
         "windows": [{"wall": "right", "offset": 80, "width": 60}]},
        {"name": "BED 1", "x": 0, "y": 500, "w": 190, "h": 204, ...},
        {"name": "BED 2", "x": 190, "y": 500, "w": 190, "h": 204, ...},
        {"name": "BED 3", "x": 380, "y": 500, "w": 190, "h": 204, ...},
        {"name": "BED 4", "x": 570, "y": 500, "w": 190, "h": 204, ...},
    ]
}
```

JSON de prueba con 7 rooms: 2 garages, 1 living, 4 bedrooms. Sirve para testear sin Claude.

### CLI (lineas 87-95)

`python generator.py` -> genera DXF con TEST_HOUSE.
`python generator.py input.json output.dxf` -> genera desde archivo JSON.

---

## 9. WEB BACKEND — `web/app.py`

FastAPI server con 3 endpoints.

### Setup (lineas 7-35)

- Linea 24: agrega `scripts/` al Python path para poder hacer `from generator import generate`
- Linea 30-31: crea carpeta temporal para guardar los DXF generados
- Linea 35: monta `web/static/` para servir archivos estaticos

### Models (lineas 40-47)

```python
class GenerateRequest(BaseModel):
    prompt: str
    image: Optional[str] = None  # base64 encoded image

class GenerateResponse(BaseModel):
    dxf_url: str
    plan: dict
```

### System Prompt (lineas 52-112)

El prompt que le da contexto a Claude para que genere el JSON correcto. Incluye:
- Reglas: medidas en pulgadas, wall thickness 4", naming en CAPS
- Schema JSON exacto que debe devolver
- Un ejemplo completo de prompt -> JSON

### Endpoints

**`GET /`** (lineas 117-119) — sirve el HTML del frontend.

**`POST /api/generate`** (lineas 122-188) — el endpoint principal:

```python
@app.post("/api/generate", response_model=GenerateResponse)
async def api_generate(req: GenerateRequest):
    content = []

    if req.image:
        # Detect media type, decode base64
        content.append({"type": "image", "source": {...}})

    content.append({"type": "text", "text": req.prompt})

    # Call Claude (claude-sonnet-4-6)
    client = anthropic.Anthropic(...)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    # Parse JSON, strip code fences if present
    plan = json.loads(response_text)

    # Generate DXF
    filename = f"{uuid.uuid4().hex[:12]}.dxf"
    generate(plan, str(DXF_DIR / filename))

    return GenerateResponse(dxf_url=f"/downloads/{filename}", plan=plan)
```

Flujo:
1. Construye el mensaje para Claude. Si hay imagen, la decodifica del base64
2. Llama la API de Claude (claude-sonnet-4-6) con el system prompt
3. Parsea la respuesta JSON (limpia code fences si Claude los agrega)
4. Llama `generate(plan, out_path)` para crear el DXF
5. Devuelve URL de descarga + plan JSON

**`GET /downloads/{filename}`** (lineas 191-200) — sirve el DXF generado como archivo descargable.

---

## 10. FRONTEND — `web/static/index.html`

Single page, vanilla HTML/CSS/JS. Sin React, sin build step.

### HTML (lineas 143-167)

- Textarea para el prompt
- Input file para subir imagen (opcional)
- Boton "Generate Floor Plan"
- Div resultado con link de descarga + preview JSON colapsable

### CSS (lineas 7-141)

Dark theme (`#0a0a0a` fondo), boton azul (`#4a9eff`), boton download verde (`#2ecc71`).

### JavaScript (lineas 169-256)

**`generate()`** (lineas 190-238):
1. Lee el prompt del textarea
2. Si hay imagen, la convierte a base64 con `fileToBase64()`
3. Hace `fetch('/api/generate', {method: 'POST', body: {prompt, image}})` al backend
4. Si OK: muestra link de descarga + JSON preview
5. Si error: muestra el mensaje de error

**`fileToBase64()`** (lineas 240-247) — usa `FileReader.readAsDataURL()` que genera `data:image/png;base64,XXXXXX`. El backend despues lo split por la coma.

**`Ctrl+Enter`** (lineas 250-255) — atajo para generar sin tocar el mouse.

---

## Flujo Completo Ejemplo

```
1. Usuario escribe: "3 bedroom house with garage"
2. Frontend -> POST /api/generate {prompt: "3 bedroom house with garage"}
3. Backend envia a Claude: system_prompt + user_prompt
4. Claude responde: {"model":"3BR","rooms":[{...},{...},...]}
5. Backend parsea JSON -> llama generate(plan, "/tmp/pointai_dxf/abc123.dxf")
6. generator.py:
   a. setup_doc()         -> DXF con 15 layers
   b. collect_walls()     -> registra 4 paredes x N rooms
   c. dedup_walls()       -> elimina duplicadas entre rooms vecinos
   d. draw_all_walls()    -> dibuja paredes con huecos para puertas/ventanas
   e. loop rooms          -> draw_doors + draw_windows + draw_label
   f. saveas()            -> archivo .dxf en disco
7. Backend responde: {dxf_url: "/downloads/abc123.dxf", plan: {...}}
8. Frontend muestra boton "Download DXF"
9. Usuario descarga -> abre en AutoCAD -> plano profesional
```

---

## Convenios CAD Pointe Homes

| Parametro | Valor |
|-----------|-------|
| Unidades | 1 AutoCAD unit = 1 inch (INSUNITS=2) |
| Wall thickness | 4 inches (lineas dobles paralelas) |
| Door slab | 1.5 inches |
| Door swing | 90 grados |
| Room label height | 9 inches |
| DXF format | R2018 (AutoCAD 2018) |

### Layers

| Layer | Color | Lineweight | Uso |
|-------|-------|-----------|-----|
| WALLS | 7 (blanco) | 0.60mm | Paredes |
| DOORS | 157 (violeta) | 0.09mm | Puertas |
| WINS | 121 (verde) | default | Ventanas |
| ROOM LBLS | 253 (gris) | 0.30mm | Nombres de cuartos |
| HATCH | 123 | 0 | Relleno solido |
| DIMS | 137 | 0.15mm | Dimensiones |
| FIXTURES | 2 (amarillo) | 0.15mm | Fixtures |
| TEXT LBLS | 81 | 0.18mm | Text labels |
| TEXT | 7 (blanco) | default | Texto general |
| DOORTEXT | 253 | 0.20mm | Texto de puertas |
| CABS-FLOORPLAN | 4 (cyan) | default | Gabinetes |
| HEADERS | 7 (blanco) | 0.50mm | Headers |
| ELECTRICAL | 164 | default | Electrico |
| ELECTRICAL WALLS | 65 | 0.09mm | Paredes electricas |
| MISC | 3 (verde) | 0.30mm | Miscelaneo |

### JSON Schema de Entrada

```json
{
  "model": "nombre del plano",
  "rooms": [
    {
      "name": "ROOM NAME",
      "x": 0, "y": 0, "w": 300, "h": 200,
      "doors": [
        {"wall": "bottom|top|left|right", "offset": 20, "width": 36, "type": "normal|garage|sliding"}
      ],
      "windows": [
        {"wall": "bottom|top|left|right", "offset": 60, "width": 48}
      ]
    }
  ]
}
```

---

## Estructura de Archivos

```
Point.ai/
  scripts/
    generator.py              <- Orquestador principal
    components/
      __init__.py             <- Re-exports
      primitives.py           <- Wrappers ezdxf (add_line, add_arc, add_text, add_hatch_rect)
      layers.py               <- 15 layers + setup_doc()
      walls.py                <- Standards + draw + collect + dedup + merge
      doors.py                <- Standards + draw_door + draw_doors_for_room
      windows.py              <- Standards + draw_window_h/v + draw_windows_for_room
      labels.py               <- Standards + draw_label
  web/
    app.py                    <- FastAPI backend (Claude API + generator)
    static/
      index.html              <- Frontend (vanilla HTML/CSS/JS)
```
