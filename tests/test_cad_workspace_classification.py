from backend.cad_workspace.models import ExtractedCadEntity
from backend.cad_workspace.classification import (
    assign_floor_and_site_clusters,
    is_floor_candidate_geometry_entity,
)


def test_is_floor_candidate_geometry_entity_ignores_dimension_origin():
    dimension_line = ExtractedCadEntity(
        type="line",
        layer="0",
        origin="DIMENSION",
        bbox={"x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 0.0, "width": 10.0, "height": 0.0},
        start={"x": 0.0, "y": 0.0},
        end={"x": 10.0, "y": 0.0},
    )
    plan_line = ExtractedCadEntity(
        type="line",
        layer="PLAN",
        bbox={"x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 0.0, "width": 10.0, "height": 0.0},
        start={"x": 0.0, "y": 0.0},
        end={"x": 10.0, "y": 0.0},
    )

    assert is_floor_candidate_geometry_entity(dimension_line) is False
    assert is_floor_candidate_geometry_entity(plan_line) is True


def test_assign_floor_and_site_clusters_uses_geometry_and_support_clusters():
    floor_geometry = [
        ExtractedCadEntity(
            type="line",
            layer="PLAN",
            bbox={"x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 0.0, "width": 100.0, "height": 0.0},
            start={"x": 0.0, "y": 0.0},
            end={"x": 100.0, "y": 0.0},
        ),
    ]
    floor_support = [
        ExtractedCadEntity(
            type="text",
            layer="DIMS",
            origin="DIMENSION",
            text="39'-0\"",
            position={"x": 40.0, "y": 120.0},
            bbox={"x1": 40.0, "y1": 120.0, "x2": 40.0, "y2": 120.0, "width": 0.0, "height": 0.0},
        ),
    ]
    site_geometry = [
        ExtractedCadEntity(
            type="polyline",
            layer="SETBACKS",
            bbox={"x1": 200.0, "y1": 0.0, "x2": 300.0, "y2": 100.0, "width": 100.0, "height": 100.0},
            points=(
                {"x": 200.0, "y": 0.0},
                {"x": 300.0, "y": 0.0},
                {"x": 300.0, "y": 100.0},
                {"x": 200.0, "y": 100.0},
                {"x": 200.0, "y": 0.0},
            ),
        ),
    ]

    floor_cluster, site_cluster, assignment_mode = assign_floor_and_site_clusters(
        [floor_geometry, floor_support, site_geometry],
        parse_dimension_text=lambda text: 1.0 if "'" in text else None,
        is_room_label_entity=lambda entity: entity.layer == "ROOM LBLS",
    )

    assert assignment_mode == "semantic_layer_split"
    assert {entity.layer for entity in floor_cluster} == {"PLAN", "DIMS"}
    assert {entity.layer for entity in site_cluster} == {"SETBACKS"}
