from backend.region_plan_geometry import (
    region_plan_to_image_wall_entities,
    region_plan_to_short_wall_entities,
    region_plan_to_structure,
)
from backend.mitunet_inference import build_mitunet_region_plan
from backend.benchmark import _rasterize_structure_walls_to_shape, _wall_entities_iou_vs_mask, _wall_entities_to_mask
from tests.helpers import build_mitunet_infer_result


def test_region_plan_geometry_projects_entities_back_to_image_space():
    infer_result = build_mitunet_infer_result()
    region_plan = build_mitunet_region_plan(infer_result)

    region_entities = region_plan_to_image_wall_entities(region_plan)
    wall_mask = infer_result["_wall_mask"] > 0

    assert _wall_entities_iou_vs_mask(region_entities, wall_mask) > 0.85


def test_region_plan_geometry_structure_matches_projected_entities():
    infer_result = build_mitunet_infer_result()
    region_plan = build_mitunet_region_plan(infer_result)

    projected_structure = region_plan_to_structure(region_plan, infer_result)
    projected_entities = region_plan_to_image_wall_entities(region_plan)

    structure_mask = _rasterize_structure_walls_to_shape(projected_structure, infer_result["_image_shape"])
    entity_mask = _wall_entities_to_mask(
        projected_entities,
        infer_result["_image_shape"],
        fill_polygons=True,
    ) > 0

    intersection = (structure_mask & entity_mask).sum()
    union = (structure_mask | entity_mask).sum()

    assert union > 0
    assert intersection / union > 0.9


def test_region_plan_geometry_projects_short_branch_entities_back_to_image_space():
    region_plan = {
        "regions": [
            {
                "id": "short-branch-1",
                "source_stage": "short_branch",
                "orientation": "horizontal",
                "bounds": {
                    "x1": 10.0,
                    "y1": 40.0,
                    "x2": 26.0,
                    "y2": 44.0,
                },
            }
        ],
        "meta": {
            "image_shape": {"height": 120, "width": 120},
            "transform": {"scale": 1.0, "offset_x": 0.0, "offset_y": 0.0},
        },
    }

    entities = region_plan_to_short_wall_entities(region_plan)

    assert len(entities) == 1
    xs = [float(point["x"]) for point in entities[0]["points"]]
    ys = [float(point["y"]) for point in entities[0]["points"]]
    assert min(xs) == 10.0
    assert max(xs) == 26.0
    assert min(ys) == 76.0
    assert max(ys) == 80.0
