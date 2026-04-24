from backend.wall_geometry import wall_annotation_to_entity, wall_annotation_to_structure_wall


def test_wall_annotation_to_structure_wall_derives_orientation_and_polygon():
    annotation = {
        "id": "wall-a",
        "type": "wall",
        "x1": 10.0,
        "y1": 30.0,
        "x2": 50.0,
        "y2": 30.0,
        "thickness": 6.0,
        "confidence": 0.9,
        "is_exterior": True,
    }

    wall = wall_annotation_to_structure_wall(annotation)

    assert wall["id"] == "wall-a"
    assert wall["orientation"] == "horizontal"
    assert wall["polyline"] == [{"x": 10.0, "y": 30.0}, {"x": 50.0, "y": 30.0}]
    assert wall["polygon"] == [
        {"x": 10.0, "y": 27.0},
        {"x": 50.0, "y": 27.0},
        {"x": 50.0, "y": 33.0},
        {"x": 10.0, "y": 33.0},
    ]
    assert wall["thickness"] == 6.0
    assert wall["is_exterior"] is True
    assert wall["confidence"] == 0.9


def test_wall_annotation_to_entity_prefers_polygon_and_closes_polyline():
    annotation = {
        "id": "wall-b",
        "type": "wall",
        "x1": 10.0,
        "y1": 20.0,
        "x2": 10.0,
        "y2": 40.0,
        "thickness": 4.0,
        "polygon": [
            {"x": 8.0, "y": 20.0},
            {"x": 12.0, "y": 20.0},
            {"x": 12.0, "y": 40.0},
            {"x": 8.0, "y": 40.0},
        ],
    }

    entity = wall_annotation_to_entity(annotation)

    assert entity["type"] == "polyline"
    assert entity["closed"] is True
    assert entity["width"] == 4.0
    assert entity["points"] == [
        {"x": 8.0, "y": 20.0},
        {"x": 12.0, "y": 20.0},
        {"x": 12.0, "y": 40.0},
        {"x": 8.0, "y": 40.0},
        {"x": 8.0, "y": 20.0},
    ]
