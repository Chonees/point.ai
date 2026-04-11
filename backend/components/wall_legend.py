"""
wall_legend.py — Wall Legend block matching Seminole 2000 CAD standards.

Source: SEMINOLE 2000 FARMHOUSE.dxf wall legend at (62303,-123935)-(62476,-124101).
Structure: LWPOLYLINE border (DIMS), title TEXT (ROOM LBLS h=12.3),
           entries TEXT (TEXT h=5.0 for wall types, h=3.5 for bracing panels).
"""
from typing import Any

# Seminole 2000 legend entries (order: top to bottom)
_ENTRIES = [
    {"text": '2 x 4 WALLS STUDS @ 16" O.C.', "height": 5.0},
    {"text": '2 x 6 WALLS STUDS @ 16" O.C.', "height": 5.0},
]

TITLE_HEIGHT = 12.3
ENTRY_SPACING = 16.0
PADDING = 12.0
BOX_WIDTH = 180.0


def add_wall_legend(
    msp: Any,
    doc: Any,
    origin_x: float,
    origin_y: float,
) -> None:
    """Add a wall legend box at the given origin (top-left corner).

    Matches Seminole 2000 conventions: LWPOLYLINE border on DIMS layer,
    title on ROOM LBLS, entries on TEXT layer.
    """
    for layer_name in ("DIMS", "ROOM LBLS", "TEXT", "HATCH"):
        if layer_name not in doc.layers:
            from .layers import LAYERS
            props = LAYERS.get(layer_name, {"color": 7, "lineweight": -3})
            doc.layers.add(layer_name, color=props["color"])

    x = origin_x
    y = origin_y

    # Title
    y_cursor = y - PADDING
    msp.add_text(
        "WALL LEGEND",
        dxfattribs={
            "layer": "ROOM LBLS",
            "height": TITLE_HEIGHT,
            "insert": (x + PADDING, y_cursor),
        },
    )
    y_cursor -= TITLE_HEIGHT + PADDING

    # Hatch samples + text entries
    sample_w = 30.0
    sample_h_4 = 4.0
    sample_h_6 = 6.0
    text_x = x + PADDING + sample_w + 8.0

    from .hatch import add_wall_hatch, ensure_hatch_layer
    ensure_hatch_layer(doc)

    for entry in _ENTRIES:
        is_6 = "2 x 6" in entry["text"]
        sh = sample_h_6 if is_6 else sample_h_4
        thickness = 6.0 if is_6 else 4.0

        # Hatch sample rectangle
        sy_mid = y_cursor - entry["height"] / 2
        sample_pts = [
            (x + PADDING, sy_mid - sh / 2),
            (x + PADDING + sample_w, sy_mid - sh / 2),
            (x + PADDING + sample_w, sy_mid + sh / 2),
            (x + PADDING, sy_mid + sh / 2),
            (x + PADDING, sy_mid - sh / 2),
        ]
        poly = msp.add_lwpolyline(
            sample_pts,
            dxfattribs={"layer": "WALLS", "color": 7},
        )
        poly.close()
        add_wall_hatch(msp, doc, sample_pts, thickness)

        # Label text
        msp.add_text(
            entry["text"],
            dxfattribs={
                "layer": "TEXT",
                "height": entry["height"],
                "color": 7,
                "insert": (text_x, y_cursor - entry["height"]),
            },
        )
        y_cursor -= ENTRY_SPACING

    # Border box
    box_h = abs(y - y_cursor) + PADDING
    border_pts = [
        (x, y),
        (x + BOX_WIDTH, y),
        (x + BOX_WIDTH, y - box_h),
        (x, y - box_h),
        (x, y),
    ]
    msp.add_lwpolyline(
        border_pts,
        dxfattribs={"layer": "DIMS"},
    )
