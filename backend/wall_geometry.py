from __future__ import annotations

from typing import Any


def wall_annotation_orientation(annotation: dict[str, Any]) -> str:
    orientation = annotation.get("orientation")
    if orientation in {"horizontal", "vertical", "diagonal"}:
        return str(orientation)

    x1 = float(annotation.get("x1", 0.0))
    y1 = float(annotation.get("y1", 0.0))
    x2 = float(annotation.get("x2", 0.0))
    y2 = float(annotation.get("y2", 0.0))
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    if dx > 0.0 and dy > 0.0 and abs(dx - dy) > 1e-6:
        return "horizontal" if dx >= dy else "vertical"
    if dx > 0.0 and dy > 0.0:
        return "diagonal"
    return "horizontal" if dx >= dy else "vertical"


def wall_annotation_polygon(annotation: dict[str, Any]) -> list[dict[str, float]]:
    polygon = [
        {"x": float(point.get("x", 0.0)), "y": float(point.get("y", 0.0))}
        for point in (annotation.get("polygon") or [])
    ]
    if len(polygon) >= 3:
        return polygon

    x1 = float(annotation.get("x1", 0.0))
    y1 = float(annotation.get("y1", 0.0))
    x2 = float(annotation.get("x2", 0.0))
    y2 = float(annotation.get("y2", 0.0))
    thickness = float(annotation.get("thickness", 1.0) or 1.0)
    half = max(thickness / 2.0, 0.5)
    orientation = wall_annotation_orientation(annotation)
    if orientation == "vertical":
        lo_y, hi_y = sorted((y1, y2))
        return [
            {"x": x1 - half, "y": lo_y},
            {"x": x1 + half, "y": lo_y},
            {"x": x1 + half, "y": hi_y},
            {"x": x1 - half, "y": hi_y},
        ]

    lo_x, hi_x = sorted((x1, x2))
    return [
        {"x": lo_x, "y": y1 - half},
        {"x": hi_x, "y": y1 - half},
        {"x": hi_x, "y": y1 + half},
        {"x": lo_x, "y": y1 + half},
    ]


def wall_annotation_to_structure_wall(
    annotation: dict[str, Any],
    *,
    default_id: str | None = None,
) -> dict[str, Any]:
    x1 = float(annotation.get("x1", 0.0))
    y1 = float(annotation.get("y1", 0.0))
    x2 = float(annotation.get("x2", 0.0))
    y2 = float(annotation.get("y2", 0.0))
    return {
        "id": str(annotation.get("id") or default_id or "wall"),
        "orientation": wall_annotation_orientation(annotation),
        "polyline": [{"x": x1, "y": y1}, {"x": x2, "y": y2}],
        "polygon": wall_annotation_polygon(annotation),
        "thickness": float(annotation.get("thickness", 1.0) or 1.0),
        "is_exterior": bool(annotation.get("is_exterior", False)),
        "confidence": float(annotation.get("confidence", 1.0) or 1.0),
        "side": annotation.get("side"),
    }


def wall_annotation_to_entity(
    annotation: dict[str, Any],
    *,
    layer: str = "WALLS",
) -> dict[str, Any]:
    polygon = wall_annotation_polygon(annotation)
    if len(polygon) >= 3:
        points = [{"x": float(point["x"]), "y": float(point["y"])} for point in polygon]
        if points[0] != points[-1]:
            points.append(dict(points[0]))
        return {
            "type": "polyline",
            "layer": layer,
            "closed": True,
            "width": float(annotation.get("thickness", 0.0) or 0.0),
            "points": points,
        }

    return {
        "type": "line",
        "layer": layer,
        "start": {"x": float(annotation.get("x1", 0.0)), "y": float(annotation.get("y1", 0.0))},
        "end": {"x": float(annotation.get("x2", 0.0)), "y": float(annotation.get("y2", 0.0))},
        "width": float(annotation.get("thickness", 0.0) or 0.0),
    }
