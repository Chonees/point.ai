from backend.structure_postprocess import anchor_openings_to_walls
from backend.ensemble_inference import _openings_to_annotations


def _sample_walls() -> list[dict]:
    return [
        {
            "id": "wall-top",
            "orientation": "horizontal",
            "polyline": [{"x": 20.0, "y": 20.0}, {"x": 200.0, "y": 20.0}],
            "thickness": 8.0,
            "confidence": 0.95,
            "is_exterior": True,
            "side": "top",
        },
        {
            "id": "wall-interior",
            "orientation": "vertical",
            "polyline": [{"x": 110.0, "y": 20.0}, {"x": 110.0, "y": 140.0}],
            "thickness": 8.0,
            "confidence": 0.92,
            "is_exterior": False,
            "side": "right",
        },
    ]


def test_anchor_openings_to_walls_assigns_best_wall_and_offset():
    openings = [
        {
            "id": "window-top",
            "kind": "window",
            "position": {"x": 151.0, "y": 24.0},
            "span": 30.0,
            "orientation": "horizontal",
            "confidence": 0.9,
        },
        {
            "id": "door-interior",
            "kind": "door",
            "position": {"x": 108.0, "y": 74.0},
            "span": 28.0,
            "orientation": "vertical",
            "confidence": 0.88,
            "door_type": "normal",
        },
    ]

    anchored, metrics = anchor_openings_to_walls(
        openings,
        _sample_walls(),
        structure_meta={"image_size": {"width": 220, "height": 160}, "unit": "pixel"},
    )

    assert len(anchored) == 2
    by_id = {opening["id"]: opening for opening in anchored}

    assert by_id["window-top"]["wall_id"] == "wall-top"
    assert by_id["window-top"]["orientation"] == "horizontal"
    assert by_id["window-top"]["side"] == "top"
    assert by_id["window-top"]["offset"] == 116.0

    assert by_id["door-interior"]["wall_id"] == "wall-interior"
    assert by_id["door-interior"]["orientation"] == "vertical"
    assert by_id["door-interior"]["side"] == "right"
    assert by_id["door-interior"]["offset"] == 40.0
    assert by_id["door-interior"]["swing"] == "left"

    assert metrics["filtered_opening_count"] == 0
    assert metrics["review_flags"] == []


def test_anchor_openings_to_walls_filters_far_hallucinations():
    openings = [
        {
            "id": "floating-window",
            "kind": "window",
            "position": {"x": 400.0, "y": 400.0},
            "span": 24.0,
            "orientation": "horizontal",
            "confidence": 0.5,
        }
    ]

    anchored, metrics = anchor_openings_to_walls(
        openings,
        _sample_walls(),
        structure_meta={"image_size": {"width": 220, "height": 160}, "unit": "pixel"},
    )

    assert anchored == []
    assert metrics["filtered_opening_count"] == 1
    assert any("no compatible wall found" in flag for flag in metrics["review_flags"])


def test_openings_to_annotations_preserves_side_and_door_metadata():
    annotations = _openings_to_annotations(
        [
            {
                "id": "door-1",
                "kind": "door",
                "wall_id": "wall-a",
                "position": {"x": 50.0, "y": 80.0},
                "span": 20.0,
                "orientation": "horizontal",
                "side": "top",
                "swing": "down",
                "door_type": "normal",
            },
            {
                "id": "window-1",
                "kind": "window",
                "wall_id": "wall-b",
                "position": {"x": 100.0, "y": 40.0},
                "span": 24.0,
                "orientation": "vertical",
                "side": "left",
            },
        ],
        image_height=160,
    )

    by_type = {ann["type"]: ann for ann in annotations}
    assert by_type["door"]["wall_id"] == "wall-a"
    assert by_type["door"]["side"] == "top"
    assert by_type["door"]["swing"] == "down"
    assert by_type["door"]["door_type"] == "normal"
    assert by_type["window"]["wall_id"] == "wall-b"
    assert by_type["window"]["side"] == "left"
