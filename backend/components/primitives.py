"""
primitives.py — Thin ezdxf wrappers for basic drawing operations.
No standards, no business logic — just convenience functions.
"""
from ezdxf import colors
from ezdxf.enums import TextEntityAlignment


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
