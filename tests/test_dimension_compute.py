"""
Tests for compute_dimension_annotations — the pure data function that
replaces the old DXF-side dimension generation.

We lock in behavior that matters for the refactor:
- Exterior dimensions are emitted for each exterior wall segment.
- Window chains are broken at window centerlines.
- Dimensions carry wall_ids so the frontend can recompute them when a
  user moves the anchoring wall.
- User-supplied dimensions in the pipeline override recomputation
  (verified indirectly via the service-level edit-preservation test).
- No scale → no dimensions.
"""
from __future__ import annotations

from backend.components.dimensions import compute_dimension_annotations


def _rect_walls_with_ids() -> list[dict]:
    return [
        {"id": "w-top",    "type": "wall", "x1": 20,  "y1": 20,  "x2": 120, "y2": 20},
        {"id": "w-bot",    "type": "wall", "x1": 20,  "y1": 100, "x2": 120, "y2": 100},
        {"id": "w-left",   "type": "wall", "x1": 20,  "y1": 20,  "x2": 20,  "y2": 100},
        {"id": "w-right",  "type": "wall", "x1": 120, "y1": 20,  "x2": 120, "y2": 100},
    ]


def test_compute_emits_exterior_dims_for_rectangle():
    walls = _rect_walls_with_ids()
    dims = compute_dimension_annotations(
        walls + [{"id": "L1", "type": "label", "x1": 60, "y1": 60, "x2": 60, "y2": 60}],
        scale_ipp=1.0,
        image_shape=(140, 140),
    )
    exteriors = [d for d in dims if d["subtype"] == "exterior"]
    assert len(exteriors) == 4, f"Expected 4 exterior dims, got {len(exteriors)}"

    orientations = sorted(d["orientation"] for d in exteriors)
    assert orientations == ["H", "H", "V", "V"]


def test_compute_dimensions_carry_wall_ids():
    walls = _rect_walls_with_ids()
    dims = compute_dimension_annotations(
        walls + [{"id": "L1", "type": "label", "x1": 60, "y1": 60, "x2": 60, "y2": 60}],
        scale_ipp=1.0,
        image_shape=(140, 140),
    )
    assert dims, "Expected at least one dimension"
    known_ids = {w["id"] for w in walls}
    for d in dims:
        assert d.get("wall_ids"), f"Dimension {d} lacks wall_ids"
        for wid in d["wall_ids"]:
            assert wid in known_ids, f"Unknown wall id {wid} in dimension"


def test_compute_assigns_uuid_to_each_dimension():
    walls = _rect_walls_with_ids()
    dims = compute_dimension_annotations(
        walls + [{"id": "L1", "type": "label", "x1": 60, "y1": 60, "x2": 60, "y2": 60}],
        scale_ipp=1.0,
        image_shape=(140, 140),
    )
    ids = [d["id"] for d in dims]
    assert len(ids) == len(set(ids)), "Dimension ids must be unique"
    assert all(isinstance(i, str) and len(i) > 0 for i in ids)


def test_compute_value_text_uses_architectural_format():
    walls = _rect_walls_with_ids()
    # 100 px * 1.0 in/px = 100" = 8'-4"
    dims = compute_dimension_annotations(
        walls + [{"id": "L1", "type": "label", "x1": 60, "y1": 60, "x2": 60, "y2": 60}],
        scale_ipp=1.0,
        image_shape=(140, 140),
    )
    exteriors = [d for d in dims if d["subtype"] == "exterior"]
    values = {d["value_text"] for d in exteriors}
    assert "8'-4\"" in values, f"Expected 8'-4\" in {values}"


def test_compute_emits_window_chain_on_wall_with_window():
    walls = _rect_walls_with_ids()
    annotations = walls + [
        {"id": "win-1", "type": "window", "x1": 50, "y1": 20, "x2": 70, "y2": 20},
        {"id": "L1", "type": "label", "x1": 60, "y1": 60, "x2": 60, "y2": 60},
    ]
    dims = compute_dimension_annotations(
        annotations, scale_ipp=1.0, image_shape=(140, 140),
    )
    chains = [d for d in dims if d["subtype"] == "window_chain"]
    # Expect 2 chain segments: wall_start→window_center, window_center→wall_end
    assert len(chains) == 2, f"Expected 2 window chain segments, got {len(chains)}"

    # Each chain must carry wall_ids (which wall it's measured against)
    for c in chains:
        assert c.get("wall_ids"), "Window chain missing wall_ids"


def test_compute_returns_empty_when_no_walls():
    dims = compute_dimension_annotations(
        [{"id": "L1", "type": "label", "x1": 0, "y1": 0, "x2": 0, "y2": 0}],
        scale_ipp=1.0,
        image_shape=(100, 100),
    )
    assert dims == []


def test_compute_returns_empty_when_scale_zero():
    walls = _rect_walls_with_ids()
    dims = compute_dimension_annotations(
        walls, scale_ipp=0.0, image_shape=(140, 140),
    )
    assert dims == []


def test_compute_outward_direction_points_away_from_centroid():
    """outward is in DXF-convention (y flipped), mirrors generator.py.

    For horizontal walls: sign is inverted vs image y — a wall ABOVE the
    centroid in image coords is BELOW the centroid after DXF's y-flip, so
    outward for the top wall is +1 (still "away from center" in DXF).
    """
    walls = _rect_walls_with_ids()
    dims = compute_dimension_annotations(
        walls + [{"id": "L1", "type": "label", "x1": 60, "y1": 60, "x2": 60, "y2": 60}],
        scale_ipp=1.0,
        image_shape=(140, 140),
    )
    top = next(d for d in dims if d["subtype"] == "exterior" and d["orientation"] == "H" and d["y1"] == 20)
    bot = next(d for d in dims if d["subtype"] == "exterior" and d["orientation"] == "H" and d["y1"] == 100)
    assert top["outward"] == 1
    assert bot["outward"] == -1

    left = next(d for d in dims if d["subtype"] == "exterior" and d["orientation"] == "V" and d["x1"] == 20)
    right = next(d for d in dims if d["subtype"] == "exterior" and d["orientation"] == "V" and d["x1"] == 120)
    assert left["outward"] == -1
    assert right["outward"] == 1
