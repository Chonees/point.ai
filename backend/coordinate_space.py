from __future__ import annotations

import copy
from typing import Any

IMAGE_COORDINATE_SPACE = "image_y_down"
DXF_COORDINATE_SPACE = "dxf_y_up"

_LEGACY_DXF_SOURCES = {"mitunet_local", "ensemble_local"}


def structure_coordinate_space(structure: dict[str, Any]) -> str:
    meta = structure.get("structure_meta") or {}
    declared = meta.get("coordinate_space")
    if declared in {IMAGE_COORDINATE_SPACE, DXF_COORDINATE_SPACE}:
        return str(declared)

    source = str(structure.get("source") or "")
    if source in _LEGACY_DXF_SOURCES and _structure_image_height(structure) is not None:
        return DXF_COORDINATE_SPACE

    return IMAGE_COORDINATE_SPACE


def structure_to_image_space(
    structure: dict[str, Any],
    *,
    image_height: int | None = None,
) -> dict[str, Any]:
    preview_structure = copy.deepcopy(structure)
    current_space = structure_coordinate_space(preview_structure)

    meta = preview_structure.setdefault("structure_meta", {})
    if current_space == IMAGE_COORDINATE_SPACE:
        meta.setdefault("coordinate_space", IMAGE_COORDINATE_SPACE)
        return preview_structure

    resolved_height = image_height or _structure_image_height(preview_structure)
    if resolved_height is None or resolved_height <= 0:
        meta.setdefault("coordinate_space", current_space)
        return preview_structure

    for wall in preview_structure.get("walls", []) or []:
        polyline = wall.get("polyline") or []
        if len(polyline) != 2:
            continue
        wall["polyline"] = [_point_to_image_space(point, resolved_height) for point in polyline]

    for opening in preview_structure.get("openings", []) or []:
        position = opening.get("position")
        if position is not None:
            opening["position"] = _point_to_image_space(position, resolved_height)

    for junction in preview_structure.get("junctions", []) or []:
        point = junction.get("point")
        if point is not None:
            junction["point"] = _point_to_image_space(point, resolved_height)

    meta["coordinate_space"] = IMAGE_COORDINATE_SPACE
    return preview_structure


def dxf_point_to_image_space(
    dx: float,
    dy: float,
    *,
    image_shape: tuple[int, int],
    transform: dict[str, Any],
) -> dict[str, float]:
    height, _ = image_shape
    scale = float(transform.get("scale", 1.0) or 1.0)
    offset_x = float(transform.get("offset_x", 0.0) or 0.0)
    offset_y = float(transform.get("offset_y", 0.0) or 0.0)
    ix = (float(dx) - offset_x) / scale
    iy = float(height) - ((float(dy) - offset_y) / scale)
    return {"x": ix, "y": iy}


def image_point_to_dxf_space(
    ix: float,
    iy: float,
    *,
    image_shape: tuple[int, int],
    transform: dict[str, Any],
) -> tuple[float, float]:
    height, _ = image_shape
    dx = float(ix) * float(transform.get("scale", 1.0) or 1.0) + float(transform.get("offset_x", 0.0) or 0.0)
    dy = (float(height) - float(iy)) * float(transform.get("scale", 1.0) or 1.0) + float(transform.get("offset_y", 0.0) or 0.0)
    return dx, dy


def entities_to_image_space(
    entities: list[dict[str, Any]],
    *,
    image_shape: tuple[int, int],
    transform: dict[str, Any],
) -> list[dict[str, Any]]:
    height, width = image_shape
    if height <= 0 or width <= 0:
        return entities

    scale = max(float(transform.get("scale", 1.0) or 1.0), 1e-6)
    projected: list[dict[str, Any]] = []
    for entity in entities:
        width_px = float(entity.get("width", 0.0) or 0.0) / scale
        if entity.get("type") == "polyline":
            projected.append(
                {
                    **entity,
                    "width": width_px,
                    "points": [
                        dxf_point_to_image_space(
                            float(point.get("x", 0.0)),
                            float(point.get("y", 0.0)),
                            image_shape=image_shape,
                            transform=transform,
                        )
                        for point in (entity.get("points") or [])
                    ],
                }
            )
            continue

        start = entity.get("start") or {}
        end = entity.get("end") or {}
        projected.append(
            {
                **entity,
                "width": width_px,
                "start": dxf_point_to_image_space(
                    float(start.get("x", 0.0)),
                    float(start.get("y", 0.0)),
                    image_shape=image_shape,
                    transform=transform,
                ),
                "end": dxf_point_to_image_space(
                    float(end.get("x", 0.0)),
                    float(end.get("y", 0.0)),
                    image_shape=image_shape,
                    transform=transform,
                ),
            }
        )
    return projected


def _structure_image_height(structure: dict[str, Any]) -> int | None:
    meta = structure.get("structure_meta") or {}
    image_size = meta.get("image_size")
    if isinstance(image_size, dict):
        height = image_size.get("height")
        if height is not None:
            return int(height)

    image_shape = structure.get("_image_shape")
    if isinstance(image_shape, (list, tuple)) and len(image_shape) >= 1:
        return int(image_shape[0])

    return None


def _point_to_image_space(raw_point: dict[str, Any] | list[Any] | tuple[Any, ...], image_height: int) -> dict[str, float]:
    if isinstance(raw_point, dict):
        x = float(raw_point.get("x", 0.0))
        y = float(raw_point.get("y", 0.0))
    elif isinstance(raw_point, (list, tuple)) and len(raw_point) >= 2:
        x = float(raw_point[0])
        y = float(raw_point[1])
    else:
        return {"x": 0.0, "y": float(image_height)}

    return {
        "x": x,
        "y": float(image_height) - y,
    }
