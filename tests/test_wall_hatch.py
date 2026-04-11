"""Tests for wall hatch pattern selection based on thickness."""
import ezdxf

from backend.components.hatch import (
    add_wall_hatch,
    ensure_hatch_layer,
    LAYER,
    LAYER_COLOR,
)


def _make_doc():
    doc = ezdxf.new()
    msp = doc.modelspace()
    return doc, msp


def _square_pts(size=10.0):
    return [(0, 0), (size, 0), (size, size), (0, size), (0, 0)]


def test_4_inch_wall_uses_ansi31_bylayer():
    doc, msp = _make_doc()
    add_wall_hatch(msp, doc, _square_pts(), thickness=4.0)

    hatches = list(msp.query("HATCH"))
    assert len(hatches) == 1
    h = hatches[0]
    assert h.dxf.layer == LAYER
    assert h.dxf.pattern_name == "ANSI31"
    assert h.dxf.pattern_scale == 6.0


def test_6_inch_wall_uses_solid_color_9():
    doc, msp = _make_doc()
    add_wall_hatch(msp, doc, _square_pts(), thickness=6.0)

    hatches = list(msp.query("HATCH"))
    assert len(hatches) == 1
    h = hatches[0]
    assert h.dxf.layer == LAYER
    assert h.dxf.pattern_name == "SOLID"
    assert h.dxf.color == 9


def test_hatch_layer_color_123():
    doc, _ = _make_doc()
    ensure_hatch_layer(doc)
    assert doc.layers.get(LAYER).color == LAYER_COLOR


def test_threshold_boundary_5_goes_to_solid():
    doc, msp = _make_doc()
    add_wall_hatch(msp, doc, _square_pts(), thickness=5.0)
    assert list(msp.query("HATCH"))[0].dxf.pattern_name == "SOLID"


def test_threshold_below_5_goes_to_ansi31():
    doc, msp = _make_doc()
    add_wall_hatch(msp, doc, _square_pts(), thickness=4.9)
    assert list(msp.query("HATCH"))[0].dxf.pattern_name == "ANSI31"


def test_both_on_same_layer():
    doc, msp = _make_doc()
    add_wall_hatch(msp, doc, _square_pts(), thickness=4.0)
    add_wall_hatch(msp, doc, _square_pts(20), thickness=6.0)
    hatches = list(msp.query("HATCH"))
    assert len(hatches) == 2
    assert all(h.dxf.layer == LAYER for h in hatches)


def test_ensure_hatch_layer_idempotent():
    doc, _ = _make_doc()
    ensure_hatch_layer(doc)
    ensure_hatch_layer(doc)
    assert LAYER in doc.layers


# --- Junction trim tests ---

def _hatch_bounds(hatch):
    """Extract (y_lo, y_hi) or (x_lo, x_hi) from hatch polyline path."""
    path = list(hatch.paths)[0]
    verts = list(path.vertices)
    ys = [v[1] for v in verts]
    return min(ys), max(ys)


def _make_l_junction_dxf():
    """Create an L junction: horizontal wall + vertical wall meeting at corner.

    Horizontal: (0, 50) to (100, 50), 4" thick → edges at y=48..52
    Vertical: (0, 0) to (0, 50), 4" thick → should trim to y_hi=48 (stop at h-wall inner edge)
    """
    from backend.mitunet.annotations import _draw_mitunet_annotations_from_region_plan

    doc = ezdxf.new()
    msp = doc.modelspace()
    doc.layers.add("WALLS", color=7)

    annotations = [
        {"type": "wall", "x1": 0, "y1": 50, "x2": 100, "y2": 50},  # horizontal
        {"type": "wall", "x1": 0, "y1": 0, "x2": 0, "y2": 50},     # vertical
    ]
    # Identity transform (no scaling/offset)
    _draw_mitunet_annotations_from_region_plan(
        msp, doc, annotations,
        image_shape=(200, 200),
        transform={"scale": 1.0, "offset_x": 0.0, "offset_y": 0.0},
        wall_thickness=4.0,
        regions=[],
    )
    return doc, msp


def test_l_junction_no_hatch_overlap():
    """At L junction, vertical hatch must not extend into horizontal hatch zone."""
    doc, msp = _make_l_junction_dxf()
    hatches = list(msp.query("HATCH"))
    assert len(hatches) == 2

    # Find both hatches and check they don't overlap in Y
    hatch_bounds = []
    for h in hatches:
        path = list(h.paths)[0]
        verts = list(path.vertices)
        xs = [v[0] for v in verts]
        ys = [v[1] for v in verts]
        hatch_bounds.append((min(xs), max(xs), min(ys), max(ys)))

    # The two hatches should share an edge (y boundary), not overlap
    # One is horizontal (wider in x), one is vertical (taller in y)
    h_bounds = sorted(hatch_bounds, key=lambda b: b[1] - b[0], reverse=True)
    horiz = h_bounds[0]  # wider in x
    vert = h_bounds[1]   # taller in y

    # Vertical hatch must not extend into horizontal hatch Y range
    h_y_lo, h_y_hi = horiz[2], horiz[3]
    v_y_lo, v_y_hi = vert[2], vert[3]

    # The vertical's closest Y edge to the horizontal should be at or past the horizontal's edge
    # (they share an edge, not overlap)
    overlap = min(v_y_hi, h_y_hi) - max(v_y_lo, h_y_lo)
    assert overlap <= 0.1, f"Hatch overlap={overlap:.2f} — vertical hatch bleeds into horizontal"


def test_horizontal_hatch_not_trimmed():
    """Horizontal wall hatch spans full length at junctions."""
    doc, msp = _make_l_junction_dxf()
    hatches = list(msp.query("HATCH"))

    for h in hatches:
        path = list(h.paths)[0]
        verts = list(path.vertices)
        xs = [v[0] for v in verts]
        ys = [v[1] for v in verts]
        x_range = max(xs) - min(xs)
        y_range = max(ys) - min(ys)
        if x_range > y_range:
            assert x_range >= 90, f"Horizontal hatch x_range={x_range} was trimmed"
