"""
dwg_generator.py — Pointe Homes DWG Generator
Recibe floor plan JSON → produce .dxf profesional con standards Pointe Homes.
Uso: python dwg_generator.py input.json output.dxf
"""
import ezdxf
from ezdxf import colors
from ezdxf.enums import TextEntityAlignment
import json, sys, math, os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from cad_standards import LAYERS, WALL, DOOR, WINDOW, TEXT

T = WALL["thickness"]  # 4"
DS = 1.5  # door slab thickness (inches) — Seminole uses ~0.67-2"


# ─── SETUP ────────────────────────────────────────────────────────────────────

def setup_doc():
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


# ─── PRIMITIVES ───────────────────────────────────────────────────────────────

def add_line(msp, x1, y1, x2, y2, layer):
    msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": layer})

def add_arc(msp, cx, cy, radius, start_angle, end_angle, layer):
    msp.add_arc(
        center=(cx, cy),
        radius=radius,
        start_angle=start_angle,
        end_angle=end_angle,
        dxfattribs={"layer": layer}
    )

def add_text(msp, x, y, text, height, layer):
    t = msp.add_text(text, dxfattribs={"layer": layer, "height": height})
    t.set_placement((x, y), align=TextEntityAlignment.MIDDLE_CENTER)

def add_hatch_rect(msp, x1, y1, x2, y2):
    """Relleno SOLID entre dos caras de pared (rectangulo)."""
    hatch = msp.add_hatch(color=colors.BYLAYER, dxfattribs={"layer": "HATCH"})
    hatch.set_pattern_fill("SOLID")
    hatch.paths.add_polyline_path(
        [(x1, y1), (x2, y1), (x2, y2), (x1, y2)],
        is_closed=True
    )


# ─── WALL BUILDERS ────────────────────────────────────────────────────────────

def draw_wall_h(msp, x1, x2, y, gaps=None):
    """
    Pared horizontal doble con end caps en cada abertura.
    gaps: lista de (gx1, gx2) para puertas/ventanas.
    """
    resolved_gaps = gaps or []
    segments = _split_segments(x1, x2, resolved_gaps)
    for sx1, sx2 in segments:
        add_line(msp, sx1, y,   sx2, y,   "WALLS")
        add_line(msp, sx1, y+T, sx2, y+T, "WALLS")
    # End caps en cada lado de cada abertura
    for gx1, gx2 in resolved_gaps:
        add_line(msp, gx1, y, gx1, y+T, "WALLS")
        add_line(msp, gx2, y, gx2, y+T, "WALLS")

def draw_wall_v(msp, x, y1, y2, gaps=None):
    """
    Pared vertical doble con end caps en cada abertura.
    gaps: lista de (gy1, gy2).
    """
    resolved_gaps = gaps or []
    segments = _split_segments(y1, y2, resolved_gaps)
    for sy1, sy2 in segments:
        add_line(msp, x,   sy1, x,   sy2, "WALLS")
        add_line(msp, x+T, sy1, x+T, sy2, "WALLS")
    # End caps en cada lado de cada abertura
    for gy1, gy2 in resolved_gaps:
        add_line(msp, x, gy1, x+T, gy1, "WALLS")
        add_line(msp, x, gy2, x+T, gy2, "WALLS")

def _split_segments(start, end, gaps):
    """Divide un segmento en partes evitando los gaps."""
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


def _merge_spans(spans_with_gaps):
    """
    Mergea spans solapados y combina sus gaps.
    spans_with_gaps: lista de (start, end, gaps_list)
    Retorna: lista de (merged_start, merged_end, merged_gaps)
    """
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


# ─── DOOR ─────────────────────────────────────────────────────────────────────

def draw_door(msp, hx, hy, width, direction="up"):
    """
    Puerta: dos lineas paralelas (tablero, estilo Seminole) + arc swing.
    hx, hy = punto de bisagra (inner face de la pared)
    direction: 'up','down','left','right'

    Convencion (verificado vs floorplan.dxf Seminole):
      up    — pared horizontal inferior, cuarto arriba
              tablero perpendicular (sube) + arc 0→90
      down  — pared horizontal superior, cuarto abajo
              tablero perpendicular (baja) + arc 270→360
      right — pared vertical izquierda, cuarto derecha
              tablero perpendicular (va derecha) + arc 0→90
      left  — pared vertical derecha, cuarto izquierda
              tablero perpendicular (va izquierda) + arc 90→180
    """
    layer = "DOORS"
    if direction == "up":
        add_line(msp, hx,      hy, hx,      hy + width, layer)
        add_line(msp, hx + DS, hy, hx + DS, hy + width, layer)
        add_arc(msp, hx, hy, width, 0, 90, layer)
    elif direction == "down":
        add_line(msp, hx,      hy, hx,      hy - width, layer)
        add_line(msp, hx + DS, hy, hx + DS, hy - width, layer)
        add_arc(msp, hx, hy, width, 270, 360, layer)
    elif direction == "right":
        add_line(msp, hx, hy,      hx + width, hy,      layer)
        add_line(msp, hx, hy + DS, hx + width, hy + DS, layer)
        add_arc(msp, hx, hy, width, 0, 90, layer)
    elif direction == "left":
        add_line(msp, hx, hy,      hx - width, hy,      layer)
        add_line(msp, hx, hy + DS, hx - width, hy + DS, layer)
        add_arc(msp, hx, hy, width, 90, 180, layer)


# ─── WINDOW ───────────────────────────────────────────────────────────────────

def draw_window_h(msp, x, y, width):
    """Ventana en pared horizontal: linea perpendicular en el centro del hueco."""
    mid = x + width / 2
    add_line(msp, mid, y - 4, mid, y + T + 4, "WINS")

def draw_window_v(msp, x, y, width):
    """Ventana en pared vertical."""
    mid = y + width / 2
    add_line(msp, x - 4, mid, x + T + 4, mid, "WINS")


# ─── ROOM LABEL ───────────────────────────────────────────────────────────────

def draw_label(msp, cx, cy, name):
    add_text(msp, cx, cy, name, TEXT["room_label_height"], "ROOM LBLS")


# ─── MAIN GENERATOR ───────────────────────────────────────────────────────────

def generate(floor_plan: dict, out_path: str):
    doc, msp = setup_doc()

    # ── Phase 1: Collect all walls into a registry ─────────────────────────────
    # h_walls[y] = [(x1, x2, gaps)]  — horizontal walls keyed by y
    # v_walls[x] = [(y1, y2, gaps)]  — vertical walls keyed by x
    # Rooms that share a wall (e.g. GARAGE top / LIVING bottom at same y) will
    # both register their segment; _merge_spans combines them so the wall is
    # drawn ONCE with ALL gaps from both sides.
    h_walls: dict = defaultdict(list)
    v_walls: dict = defaultdict(list)

    for room in floor_plan["rooms"]:
        rx = room["x"]
        ry = room["y"]
        rw = room["w"]
        rh = room["h"]

        gaps: dict = {"bottom": [], "top": [], "left": [], "right": []}

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

        h_walls[ry     ].append((rx,       rx + rw,      gaps["bottom"]))
        h_walls[ry + rh].append((rx,       rx + rw,      gaps["top"]))
        v_walls[rx     ].append((ry + T,   ry + rh - T,  gaps["left"]))
        v_walls[rx+rw-T].append((ry + T,   ry + rh - T,  gaps["right"]))

    # ── Phase 2: Draw each unique wall segment once (merged gaps) ──────────────
    for y, spans in h_walls.items():
        for x1, x2, merged_gaps in _merge_spans(spans):
            draw_wall_h(msp, x1, x2, y, gaps=merged_gaps)

    for x, spans in v_walls.items():
        for y1, y2, merged_gaps in _merge_spans(spans):
            draw_wall_v(msp, x, y1, y2, gaps=merged_gaps)

    # ── Phase 3: Draw door/window symbols and room labels ─────────────────────
    for room in floor_plan["rooms"]:
        rx = room["x"]
        ry = room["y"]
        rw = room["w"]
        rh = room["h"]

        for d in room.get("doors", []):
            off  = d["offset"]
            w    = d["width"]
            wall = d["wall"]
            if d.get("type") == "garage":
                continue
            if wall == "bottom":
                draw_door(msp, rx + off, ry + T, w, "up")
            elif wall == "top":
                draw_door(msp, rx + off, ry + rh - T, w, "down")   # inner face
            elif wall == "left":
                draw_door(msp, rx + T, ry + off, w, "right")
            elif wall == "right":
                draw_door(msp, rx + rw - T, ry + off, w, "left")   # inner face

        for wn in room.get("windows", []):
            off  = wn["offset"]
            w    = wn["width"]
            wall = wn["wall"]
            if wall == "bottom": draw_window_h(msp, rx + off, ry, w)
            elif wall == "top":  draw_window_h(msp, rx + off, ry + rh, w)
            elif wall == "left": draw_window_v(msp, rx, ry + off, w)
            elif wall == "right":draw_window_v(msp, rx + rw - T, ry + off, w)

        draw_label(msp, rx + rw / 2, ry + rh / 2, room["name"])

    doc.saveas(out_path)
    print(f"Saved: {out_path}")


# ─── TEST HOUSE ───────────────────────────────────────────────────────────────

TEST_HOUSE = {
    "model": "Test House",
    "rooms": [
        {
            "name": "GARAGE 1",
            "x": 0, "y": 0, "w": 380, "h": 248,
            "doors": [{"wall": "bottom", "offset": 40, "width": 144, "type": "garage"}],
        },
        {
            "name": "GARAGE 2",
            "x": 380, "y": 0, "w": 380, "h": 248,
            "doors": [{"wall": "bottom", "offset": 40, "width": 144, "type": "garage"}],
        },
        {
            "name": "LIVING",
            "x": 0, "y": 248, "w": 760, "h": 252,
            "doors": [{"wall": "bottom", "offset": 160, "width": 36}],
            "windows": [{"wall": "right", "offset": 80, "width": 60}],
        },
        {
            "name": "BED 1",
            "x": 0, "y": 500, "w": 190, "h": 204,
            "doors": [{"wall": "bottom", "offset": 20, "width": 32}],
            "windows": [{"wall": "top", "offset": 60, "width": 48}],
        },
        {
            "name": "BED 2",
            "x": 190, "y": 500, "w": 190, "h": 204,
            "doors": [{"wall": "bottom", "offset": 20, "width": 32}],
            "windows": [{"wall": "top", "offset": 60, "width": 48}],
        },
        {
            "name": "BED 3",
            "x": 380, "y": 500, "w": 190, "h": 204,
            "doors": [{"wall": "bottom", "offset": 20, "width": 32}],
            "windows": [{"wall": "top", "offset": 60, "width": 48}],
        },
        {
            "name": "BED 4",
            "x": 570, "y": 500, "w": 190, "h": 204,
            "doors": [{"wall": "bottom", "offset": 20, "width": 32}],
            "windows": [{"wall": "top", "offset": 60, "width": 48}],
        },
    ]
}

if __name__ == "__main__":
    if len(sys.argv) == 3:
        with open(sys.argv[1]) as f:
            plan = json.load(f)
        generate(plan, sys.argv[2])
    else:
        out = "C:/temp/test_house5.dxf"
        generate(TEST_HOUSE, out)
        print("Open in AutoCAD to verify.")
