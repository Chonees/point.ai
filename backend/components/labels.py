"""
labels.py — Pointe Homes Room Label Standards + Drawing Logic
Source: Seminole 2000 FARMHOUSE floorplan.dxf, verified 2026-03-11.

Standards:
  - Room labels: centered TEXT in ROOM LBLS layer
  - Height: 9" for room names, 6" for dimension text
"""
from .primitives import add_text

# === STANDARDS ===
ROOM_LABEL_HEIGHT = 9  # inches
DIM_TEXT_HEIGHT = 6     # inches
LAYER = "ROOM LBLS"


# === DRAWING ===

def draw_label(msp, cx, cy, name):
    """Room label centered at (cx, cy)."""
    add_text(msp, cx, cy, name, ROOM_LABEL_HEIGHT, LAYER)
