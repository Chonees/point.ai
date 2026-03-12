"""
windows.py — Pointe Homes Window Standards + Drawing Logic
Source: Seminole 2000 FARMHOUSE floorplan.dxf, verified 2026-03-11.

Standards:
  - 3 parallel lines in opening + 2 end caps (1") + 1 sill
  - Lines ALWAYS face outward (toward exterior)
  - Layer: WINS (color 121, lineweight -3/default)

Pattern by wall side:
  Horizontal bottom: sill at y-5, lines at y, y-1, y-2, end caps between y-1/y-2
  Horizontal top:    sill at y+5, lines at y, y+1, y+2, end caps between y+1/y+2
  Vertical left:     lines at x-1, x, x+1, sill at x+6, end caps between x-1/x
  Vertical right:    lines at x+T, x+T+1, x+T-1, sill at x-2, end caps between x+T/x+T+1
"""
from .primitives import add_line
from .walls import THICKNESS

# === STANDARDS ===
LAYER = "WINS"
H_SILL_OFFSET = 5     # inches — horizontal exterior sill distance
V_SILL_OUT = 1         # inches — vertical exterior sill distance
V_SILL_IN = 6          # inches — vertical interior sill distance


# === DRAWING ===

def draw_window_h(msp, x, y, width, side="bottom"):
    """Ventana horizontal — 3 lineas paralelas + end caps + sill exterior."""
    L = LAYER
    if side == "bottom":
        # exterior = abajo (-y), 3 lineas miran hacia afuera (-y)
        add_line(msp, x, y-5,   x+width, y-5,   L)   # sill exterior
        add_line(msp, x, y,     x+width, y,     L)   # cara exterior
        add_line(msp, x, y-1,   x+width, y-1,   L)   # -1" (hacia afuera)
        add_line(msp, x, y-2,   x+width, y-2,   L)   # -2" (hacia afuera)
        add_line(msp, x,       y-1, x,       y-2, L)  # end cap izq
        add_line(msp, x+width, y-1, x+width, y-2, L)  # end cap der
    else:  # top
        # exterior = arriba (+y), 3 lineas miran hacia afuera (+y)
        add_line(msp, x, y+5,   x+width, y+5,   L)   # sill exterior
        add_line(msp, x, y,     x+width, y,     L)   # cara exterior
        add_line(msp, x, y+1,   x+width, y+1,   L)   # +1" (hacia afuera)
        add_line(msp, x, y+2,   x+width, y+2,   L)   # +2" (hacia afuera)
        add_line(msp, x,       y+1, x,       y+2, L)  # end cap izq
        add_line(msp, x+width, y+1, x+width, y+2, L)  # end cap der


def draw_window_v(msp, x, y, width, side="left"):
    """Ventana vertical — 3 lineas paralelas + end caps + sill exterior."""
    L = LAYER
    T = THICKNESS
    if side == "left":
        add_line(msp, x-1, y,        x-1, y+width, L)  # sill exterior 1" afuera
        add_line(msp, x,   y,        x,   y+width, L)  # cara exterior
        add_line(msp, x+1, y,        x+1, y+width, L)  # +1"
        add_line(msp, x+6, y,        x+6, y+width, L)  # sill interior
        add_line(msp, x-1, y,        x,   y,       L)  # end cap bottom
        add_line(msp, x-1, y+width,  x,   y+width, L)  # end cap top
    else:  # right — x es la cara interior, cara exterior en x+T
        add_line(msp, x+T+1, y,       x+T+1, y+width, L)  # sill exterior 1" afuera
        add_line(msp, x+T,   y,       x+T,   y+width, L)  # cara exterior
        add_line(msp, x+T-1, y,       x+T-1, y+width, L)  # -1"
        add_line(msp, x-2,   y,       x-2,   y+width, L)  # sill interior
        add_line(msp, x+T,   y,       x+T+1, y,       L)  # end cap bottom
        add_line(msp, x+T,   y+width, x+T+1, y+width, L)  # end cap top


# === ROOM HELPER ===

def draw_windows_for_room(msp, room):
    """Draw all windows for a room."""
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
