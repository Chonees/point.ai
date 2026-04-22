from __future__ import annotations

from typing import Any

from .coordinate_space import dxf_point_to_image_space
from .mitunet_inference import regions_to_wall_annotations
from .structure_postprocess import build_junction_graph
from .wall_geometry import wall_annotation_to_entity, wall_annotation_to_structure_wall


def region_plan_image_shape(region_plan: dict[str, Any]) -> tuple[int, int]:
    meta = region_plan.get("meta") or {}
    image_shape = meta.get("image_shape") or {}
    return (
        int(image_shape.get("height", 0)),
        int(image_shape.get("width", 0)),
    )


def region_plan_image_wall_annotations(region_plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(annotation)
        for annotation in (regions_to_wall_annotations(region_plan) or [])
        if annotation.get("type") == "wall"
    ]


def region_plan_to_image_wall_entities(region_plan: dict[str, Any]) -> list[dict[str, Any]]:
    annotation_walls = region_plan_image_wall_annotations(region_plan)
    if annotation_walls:
        return [wall_annotation_to_entity(annotation, layer="WALLS") for annotation in annotation_walls]

    entities: list[dict[str, Any]] = []
    for region in region_plan.get("regions", []):
        bounds = region.get("bounds") or {}
        x1 = float(bounds.get("x1", 0.0))
        y1 = float(bounds.get("y1", 0.0))
        x2 = float(bounds.get("x2", 0.0))
        y2 = float(bounds.get("y2", 0.0))
        entities.append(
            {
                "type": "polyline",
                "layer": "WALLS",
                "closed": True,
                "points": [
                    {"x": x1, "y": y1},
                    {"x": x2, "y": y1},
                    {"x": x2, "y": y2},
                    {"x": x1, "y": y2},
                    {"x": x1, "y": y1},
                ],
            }
        )
    return entities


def region_plan_to_short_wall_entities(region_plan: dict[str, Any]) -> list[dict[str, Any]]:
    if not region_plan:
        return []

    image_shape = region_plan_image_shape(region_plan)
    transform = (region_plan.get("meta") or {}).get("transform") or {}

    short_regions = [
        region
        for region in (region_plan.get("regions", []) or [])
        if region.get("source_stage") == "short_branch"
    ]
    entities: list[dict[str, Any]] = []
    for region in short_regions:
        bounds = region.get("bounds") or {}
        dxf_x1 = float(bounds.get("x1", 0.0))
        dxf_y1 = float(bounds.get("y1", 0.0))
        dxf_x2 = float(bounds.get("x2", 0.0))
        dxf_y2 = float(bounds.get("y2", 0.0))
        point_a = dxf_point_to_image_space(
            dxf_x1,
            dxf_y1,
            image_shape=image_shape,
            transform=transform,
        )
        point_b = dxf_point_to_image_space(
            dxf_x2,
            dxf_y2,
            image_shape=image_shape,
            transform=transform,
        )
        x1 = min(float(point_a["x"]), float(point_b["x"]))
        y1 = min(float(point_a["y"]), float(point_b["y"]))
        x2 = max(float(point_a["x"]), float(point_b["x"]))
        y2 = max(float(point_a["y"]), float(point_b["y"]))
        entities.append(
            {
                "type": "polyline",
                "layer": "WALLS",
                "closed": True,
                "points": [
                    {"x": x1, "y": y1},
                    {"x": x2, "y": y1},
                    {"x": x2, "y": y2},
                    {"x": x1, "y": y2},
                    {"x": x1, "y": y1},
                ],
            }
        )
    return entities


def region_plan_to_structure(region_plan: dict[str, Any], reference_structure: dict[str, Any]) -> dict[str, Any]:
    annotation_walls = region_plan_image_wall_annotations(region_plan)
    if annotation_walls:
        walls = [
            wall_annotation_to_structure_wall(annotation, default_id=f"region-wall-{index:04d}")
            for index, annotation in enumerate(annotation_walls, start=1)
        ]
    else:
        walls = []
        for index, region in enumerate(region_plan.get("regions", []), start=1):
            bounds = region.get("bounds") or {}
            x1 = float(bounds.get("x1", 0.0))
            y1 = float(bounds.get("y1", 0.0))
            x2 = float(bounds.get("x2", 0.0))
            y2 = float(bounds.get("y2", 0.0))
            orientation = region.get("orientation", "horizontal")
            if orientation == "horizontal":
                polyline = [{"x": x1, "y": (y1 + y2) / 2.0}, {"x": x2, "y": (y1 + y2) / 2.0}]
                thickness = max(1.0, y2 - y1)
            else:
                polyline = [{"x": (x1 + x2) / 2.0, "y": y1}, {"x": (x1 + x2) / 2.0, "y": y2}]
                thickness = max(1.0, x2 - x1)
            walls.append(
                {
                    "id": region.get("id", f"region-wall-{index:04d}"),
                    "orientation": orientation,
                    "polyline": polyline,
                    "polygon": [
                        {"x": x1, "y": y1},
                        {"x": x2, "y": y1},
                        {"x": x2, "y": y2},
                        {"x": x1, "y": y2},
                    ],
                    "thickness": float(thickness),
                    "is_exterior": False,
                    "confidence": 1.0,
                }
            )

    return {
        "model": "MitUNet Region Plan",
        "source": "benchmark_region_plan",
        "walls": walls,
        "openings": [],
        "junctions": build_junction_graph(walls),
        "structure_meta": reference_structure.get("structure_meta", {}),
    }
