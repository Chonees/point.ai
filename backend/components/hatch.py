"""
hatch.py — Wall hatch patterns following Pointe Homes CAD standards.
Source: Seminole 2000 FARMHOUSE floorplan.dxf, verified 2026-04-06.

Standards (from HATCH layer analysis):
  - Layer HATCH, color 123 (light cyan)
  - 4" walls: ANSI31 pattern, color 256 (bylayer → 123), scale 6.0
  - 6" walls: SOLID,_O pattern, color 9 (gray, entity override)
"""
from typing import Any

from ezdxf import colors

LAYER = "HATCH"
LAYER_COLOR = 123
THRESHOLD = 5.0
ANSI31_SCALE = 0.3


def ensure_hatch_layer(doc: Any) -> None:
    if LAYER not in doc.layers:
        doc.layers.add(LAYER, color=LAYER_COLOR, dxfattribs={"lineweight": 0})
    else:
        doc.layers.get(LAYER).dxf.lineweight = 0


def add_wall_hatch(msp: Any, doc: Any, pts: list, thickness: float) -> None:
    """Add a hatch to a wall polygon. Matches Seminole 2000 conventions.

    4" (< THRESHOLD) → ANSI31, color bylayer (123 cyan), scale 6.0
    6" (>= THRESHOLD) → SOLID, color 9 (gray entity override)
    """
    ensure_hatch_layer(doc)

    hatch = msp.add_hatch(dxfattribs={"layer": LAYER})

    if thickness >= THRESHOLD:
        hatch.set_pattern_fill("SOLID")
    else:
        hatch.set_pattern_fill("ANSI31", scale=ANSI31_SCALE)

    hatch.paths.add_polyline_path(pts, is_closed=True)

    # Color MUST be set after pattern_fill — set_pattern_fill resets it
    if thickness >= THRESHOLD:
        hatch.dxf.unprotected_set("color", 9)
    else:
        hatch.dxf.unprotected_set("color", colors.BYLAYER)

