import pytest

from backend.coordinate_space import (
    dxf_point_to_image_space,
    entities_to_image_space,
    image_point_to_dxf_space,
)


def test_region_transform_round_trips_between_image_and_dxf_space():
    image_shape = (160, 220)
    transform = {"scale": 2.5, "offset_x": 100.0, "offset_y": 40.0}

    dx, dy = image_point_to_dxf_space(
        32.0,
        44.0,
        image_shape=image_shape,
        transform=transform,
    )
    projected = dxf_point_to_image_space(
        dx,
        dy,
        image_shape=image_shape,
        transform=transform,
    )

    assert projected["x"] == pytest.approx(32.0)
    assert projected["y"] == pytest.approx(44.0)


def test_entities_to_image_space_projects_lines_and_polygons_and_scales_width():
    image_shape = (160, 220)
    transform = {"scale": 2.0, "offset_x": 100.0, "offset_y": 40.0}
    entities = [
        {
            "type": "line",
            "layer": "WALLS",
            "start": {"x": 140.0, "y": 320.0},
            "end": {"x": 220.0, "y": 320.0},
            "width": 8.0,
        },
        {
            "type": "polyline",
            "layer": "WALLS",
            "closed": True,
            "width": 10.0,
            "points": [
                {"x": 100.0, "y": 360.0},
                {"x": 180.0, "y": 360.0},
                {"x": 180.0, "y": 320.0},
                {"x": 100.0, "y": 320.0},
                {"x": 100.0, "y": 360.0},
            ],
        },
    ]

    projected = entities_to_image_space(
        entities,
        image_shape=image_shape,
        transform=transform,
    )

    line, poly = projected
    assert line["start"] == {"x": 20.0, "y": 20.0}
    assert line["end"] == {"x": 60.0, "y": 20.0}
    assert line["width"] == pytest.approx(4.0)

    assert poly["closed"] is True
    assert poly["width"] == pytest.approx(5.0)
    assert poly["points"] == [
        {"x": 0.0, "y": 0.0},
        {"x": 40.0, "y": 0.0},
        {"x": 40.0, "y": 20.0},
        {"x": 0.0, "y": 20.0},
        {"x": 0.0, "y": 0.0},
    ]
