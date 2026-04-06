import numpy as np

from backend.cubicasa_inference import _polygons_to_structure


def test_cubicasa_adapter_maps_icon_openings_to_v2_contract():
    polygons = np.array(
        [
            [[10, 10], [50, 10], [50, 18], [10, 18]],   # wall
            [[24, 10], [36, 10], [36, 18], [24, 18]],   # window opening
            [[10, 24], [18, 24], [18, 40], [10, 40]],   # door opening
        ],
        dtype=np.int32,
    )
    types = [
        {"type": "wall", "class": 2},
        {"type": "icon", "class": 1},
        {"type": "icon", "class": 2},
    ]

    walls, openings = _polygons_to_structure(polygons, types, image_height=64)

    assert len(walls) == 1
    assert len(openings) == 2
    assert {opening["kind"] for opening in openings} == {"door", "window"}
    assert all(opening["wall_id"] == walls[0]["id"] for opening in openings)
