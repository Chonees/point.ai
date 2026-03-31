"""
walls.py — Pointe Homes Wall Standards + Drawing Logic
Source: Seminole 2000 FARMHOUSE floorplan.dxf, verified 2026-03-11.

Standards:
  - Double-line walls, 4" thickness
  - End caps at every opening (door/window gap)
  - Lineweight: 0.60mm, Color: 7 (white)
  - 1 AutoCAD unit = 1 inch
"""
from collections import defaultdict
from .primitives import add_line

# === STANDARDS ===
THICKNESS = 4      # inches — two parallel LINEs 4" apart
LINEWEIGHT = 60    # 0.60mm
COLOR = 7
LAYER = "WALLS"


# === DRAWING ===

def draw_wall_h(msp, x1, x2, y, gaps=None, thickness=THICKNESS):
    """
    Pared horizontal doble con end caps en cada abertura.
    gaps: lista de (gx1, gx2) para puertas/ventanas.
    """
    resolved_gaps = gaps or []
    segments = split_segments(x1, x2, resolved_gaps)
    for sx1, sx2 in segments:
        add_line(msp, sx1, y,            sx2, y,            LAYER)
        add_line(msp, sx1, y + thickness, sx2, y + thickness, LAYER)
    for gx1, gx2 in resolved_gaps:
        add_line(msp, gx1, y, gx1, y + thickness, LAYER)
        add_line(msp, gx2, y, gx2, y + thickness, LAYER)


def draw_wall_v(msp, x, y1, y2, gaps=None, thickness=THICKNESS):
    """
    Pared vertical doble con end caps en cada abertura.
    gaps: lista de (gy1, gy2).
    """
    resolved_gaps = gaps or []
    segments = split_segments(y1, y2, resolved_gaps)
    for sy1, sy2 in segments:
        add_line(msp, x,             sy1, x,             sy2, LAYER)
        add_line(msp, x + thickness, sy1, x + thickness, sy2, LAYER)
    for gy1, gy2 in resolved_gaps:
        add_line(msp, x, gy1, x + thickness, gy1, LAYER)
        add_line(msp, x, gy2, x + thickness, gy2, LAYER)


# === UTILITIES ===

def split_segments(start, end, gaps):
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


def merge_spans(spans_with_gaps):
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


# === ORCHESTRATOR HELPERS ===

def collect_walls(rooms):
    """
    Phase 1: Build wall registries from room list.
    Returns (h_walls, v_walls) where:
      h_walls[y] = [(x1, x2, gaps)]
      v_walls[x] = [(y1, y2, gaps)]
    """
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


def dedup_walls(v_walls):
    """
    Phase 1b: When room1.right (at rx+rw-T) touches room2.left (at rx),
    they are THICKNESS apart. Merge into a single shared wall.
    Returns the deduplicated v_walls dict.
    """
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


def draw_all_walls(msp, h_walls, v_walls):
    """Phase 2: Draw each unique wall segment once (merged gaps)."""
    for y, spans in h_walls.items():
        for x1, x2, merged_gaps in merge_spans(spans):
            draw_wall_h(msp, x1, x2, y, gaps=merged_gaps)

    for x, spans in v_walls.items():
        for y1, y2, merged_gaps in merge_spans(spans):
            draw_wall_v(msp, x, y1, y2, gaps=merged_gaps)
