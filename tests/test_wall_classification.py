"""Ray-casting wall classifier: enforce exterior=2x6, interior=2x4.

Every wall in every plan shape MUST be classified correctly so that the DXF
draw thickness rule (exterior -> 6", interior -> 4") is always respected.
"""
from backend.components.walls import (
    EXTERIOR_THICKNESS,
    INTERIOR_THICKNESS,
    resolve_wall_thickness,
)
from backend.structure_postprocess import _classify_walls_with_junctions


def _wall(wid: str, orientation: str, x1: float, y1: float, x2: float, y2: float):
    return {
        "id": wid,
        "orientation": orientation,
        "polyline": [{"x": x1, "y": y1}, {"x": x2, "y": y2}],
        "thickness": 4.0,
        "confidence": 0.9,
        "is_exterior": False,
        "side": None,
    }


def _ext_ids(classified):
    return {w["id"] for w in classified if w["is_exterior"]}


def test_rectangular_house_all_4_walls_exterior():
    walls = [
        _wall("bottom", "horizontal", 0, 0, 100, 0),
        _wall("top",    "horizontal", 0, 100, 100, 100),
        _wall("left",   "vertical",   0, 0, 0, 100),
        _wall("right",  "vertical",   100, 0, 100, 100),
    ]

    classified = _classify_walls_with_junctions(walls, junctions=[])

    assert _ext_ids(classified) == {"bottom", "top", "left", "right"}
    for w in classified:
        assert resolve_wall_thickness(w["is_exterior"]) == EXTERIOR_THICKNESS


def test_rectangular_with_interior_split_wall_is_interior():
    """Box with one interior horizontal wall splitting it into two rooms."""
    walls = [
        _wall("bottom", "horizontal", 0, 0, 100, 0),
        _wall("top",    "horizontal", 0, 100, 100, 100),
        _wall("left",   "vertical",   0, 0, 0, 100),
        _wall("right",  "vertical",   100, 0, 100, 100),
        _wall("mid",    "horizontal", 0, 50, 100, 50),
    ]

    classified = _classify_walls_with_junctions(walls, junctions=[])

    assert _ext_ids(classified) == {"bottom", "top", "left", "right"}
    mid = next(w for w in classified if w["id"] == "mid")
    assert mid["is_exterior"] is False
    assert resolve_wall_thickness(mid["is_exterior"]) == INTERIOR_THICKNESS


def test_l_shape_all_perimeter_walls_exterior():
    """L-shape: 6 exterior walls including two short walls at the inner corner.

        y=100  +---+
               | A |
        y=60   |   +-----+
               |         |
        y=0    +---------+
               x=0 x=50 x=100

    The two short walls (top-of-bumpout y=60 x=50..100, side-of-A x=50 y=60..100)
    are EXTERIOR — both face outside on at least one side. The 70%-coverage
    classifier would have missed them.
    """
    walls = [
        _wall("bottom",     "horizontal", 0, 0, 100, 0),       # full bottom
        _wall("top_a",      "horizontal", 0, 100, 50, 100),    # top of A (short)
        _wall("top_bump",   "horizontal", 50, 60, 100, 60),    # top of bumpout (short, inner corner)
        _wall("left",       "vertical",   0, 0, 0, 100),       # full left
        _wall("right_a",    "vertical",   50, 60, 50, 100),    # right side of A (short, inner corner)
        _wall("right_bump", "vertical",   100, 0, 100, 60),    # right side of bumpout
    ]

    classified = _classify_walls_with_junctions(walls, junctions=[])

    expected_exterior = {"bottom", "top_a", "top_bump", "left", "right_a", "right_bump"}
    assert _ext_ids(classified) == expected_exterior, (
        f"All 6 perimeter walls must be exterior; got {_ext_ids(classified)}"
    )


def test_l_shape_interior_wall_stays_interior():
    """Same L-shape, plus an interior wall splitting room A in half."""
    walls = [
        _wall("bottom",     "horizontal", 0, 0, 100, 0),
        _wall("top_a",      "horizontal", 0, 100, 50, 100),
        _wall("top_bump",   "horizontal", 50, 60, 100, 60),
        _wall("left",       "vertical",   0, 0, 0, 100),
        _wall("right_a",    "vertical",   50, 60, 50, 100),
        _wall("right_bump", "vertical",   100, 0, 100, 60),
        # interior wall splitting room A horizontally
        _wall("interior",   "horizontal", 0, 80, 50, 80),
    ]

    classified = _classify_walls_with_junctions(walls, junctions=[])

    interior = next(w for w in classified if w["id"] == "interior")
    assert interior["is_exterior"] is False
    assert resolve_wall_thickness(interior["is_exterior"]) == INTERIOR_THICKNESS


def test_u_shape_all_perimeter_walls_exterior():
    """U-shape with 8 perimeter walls.

        +----+      +----+
        |    |      |    |
        |    +------+    |
        |                |
        +----------------+
    """
    walls = [
        _wall("bottom",   "horizontal", 0, 0, 200, 0),
        _wall("left",     "vertical",   0, 0, 0, 100),
        _wall("right",    "vertical",   200, 0, 200, 100),
        _wall("top_left", "horizontal", 0, 100, 60, 100),
        _wall("top_right","horizontal", 140, 100, 200, 100),
        _wall("u_left_v", "vertical",   60, 50, 60, 100),
        _wall("u_bottom", "horizontal", 60, 50, 140, 50),
        _wall("u_right_v","vertical",   140, 50, 140, 100),
    ]

    classified = _classify_walls_with_junctions(walls, junctions=[])

    assert _ext_ids(classified) == {w["id"] for w in walls}, (
        f"All 8 perimeter walls of U-shape must be exterior; got {_ext_ids(classified)}"
    )


def test_rule_invariant_holds_for_classified_walls():
    """Sanity: for any classified wall, the rule maps cleanly to 4\" or 6\"."""
    walls = [
        _wall("bottom", "horizontal", 0, 0, 100, 0),
        _wall("top",    "horizontal", 0, 100, 100, 100),
        _wall("left",   "vertical",   0, 0, 0, 100),
        _wall("right",  "vertical",   100, 0, 100, 100),
        _wall("mid",    "horizontal", 0, 50, 100, 50),
    ]

    classified = _classify_walls_with_junctions(walls, junctions=[])

    for wall in classified:
        thickness = resolve_wall_thickness(wall["is_exterior"])
        assert thickness in (INTERIOR_THICKNESS, EXTERIOR_THICKNESS)
        if wall["is_exterior"]:
            assert thickness == EXTERIOR_THICKNESS == 6.0
        else:
            assert thickness == INTERIOR_THICKNESS == 4.0
