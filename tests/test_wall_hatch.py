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
