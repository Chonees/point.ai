"""
doors.py — Pointe Homes Door Standards + Drawing Logic
Source: Seminole 2000 FARMHOUSE floorplan.dxf, verified 2026-03-11.

Standards:
  - Two parallel lines (door slab) + 90 degree arc swing
  - Slab thickness: 1.5"
  - Layer: DOORS (color 157, lineweight 9)
  - Swing conventions (verified vs Seminole):
      up    — bottom wall, room above: slab up + arc 0->90
      down  — top wall, room below:    slab down + arc 270->360
      right — left wall, room right:   slab right + arc 0->90
      left  — right wall, room left:   slab left + arc 90->180
"""
from .primitives import add_line, add_arc
from .walls import THICKNESS

# === STANDARDS ===
SLAB_THICKNESS = 1.5   # inches
SWING_ANGLE = 90       # degrees
LAYER = "DOORS"


# === DRAWING ===

def draw_door(msp, hx, hy, width, direction="up"):
    """
    Puerta: dos lineas paralelas (tablero) + arc swing.
    hx, hy = punto de bisagra (inner face de la pared).
    direction: 'up','down','left','right'
    """
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


def draw_garage_door(msp, x, y, width, orientation="horizontal"):
    """
    Garage door: dashed centerline across the opening.
    No swing, just a visual indicator of the garage opening.
    """
    DASH_LEN = 4.0
    GAP_LEN = 3.0
    if orientation == "horizontal":
        cx = x
        while cx < x + width:
            seg_end = min(cx + DASH_LEN, x + width)
            add_line(msp, cx, y, seg_end, y, LAYER)
            cx = seg_end + GAP_LEN
    else:
        cy = y
        while cy < y + width:
            seg_end = min(cy + DASH_LEN, y + width)
            add_line(msp, x, cy, x, seg_end, LAYER)
            cy = seg_end + GAP_LEN


def draw_sliding_door(msp, x, y, width, orientation="horizontal"):
    """
    Sliding door: two parallel offset lines (panels) with arrows.
    Each panel is half the opening width, overlapping in the center.
    """
    DS = SLAB_THICKNESS
    half = width / 2.0
    arrow_len = min(6.0, half * 0.3)

    if orientation == "horizontal":
        # Panel 1: left half, offset up
        add_line(msp, x, y + DS, x + half + arrow_len, y + DS, LAYER)
        # Panel 2: right half, offset down
        add_line(msp, x + half - arrow_len, y - DS, x + width, y - DS, LAYER)
        # Arrow heads (small tick marks)
        add_line(msp, x + half + arrow_len, y + DS - 1, x + half + arrow_len, y + DS + 1, LAYER)
        add_line(msp, x + half - arrow_len, y - DS - 1, x + half - arrow_len, y - DS + 1, LAYER)
    else:
        # Panel 1: bottom half, offset right
        add_line(msp, x + DS, y, x + DS, y + half + arrow_len, LAYER)
        # Panel 2: top half, offset left
        add_line(msp, x - DS, y + half - arrow_len, x - DS, y + width, LAYER)
        # Arrow heads
        add_line(msp, x + DS - 1, y + half + arrow_len, x + DS + 1, y + half + arrow_len, LAYER)
        add_line(msp, x - DS - 1, y + half - arrow_len, x - DS + 1, y + half - arrow_len, LAYER)


# === ROOM HELPER ===

def draw_doors_for_room(msp, room):
    """Draw all doors for a room, handling wall-offset-to-hinge-point math."""
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
