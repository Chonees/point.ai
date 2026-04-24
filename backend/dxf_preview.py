"""
dxf_preview.py — Generate a preview image from the actual DXF output.

Reads the generated DXF, extracts wall/door/window entities, converts them
back to image-pixel coordinates, and draws them over the original image.
This gives the user a preview of what the DXF actually contains, not
just the postprocessed inference.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cv2
import ezdxf
import numpy as np

from .coordinate_space import entities_to_image_space, image_point_to_dxf_space
from .image_utils import decode_image, encode_png_data
from .mitunet_inference import regions_to_wall_annotations


def build_dxf_preview(
    dxf_path: str,
    *,
    image_b64: str | None = None,
    region_plan: dict[str, Any] | None = None,
    include_openings: bool = True,
) -> np.ndarray | None:
    """Build a preview image from the actual DXF entities.

    For mask_regions mode (MitUNet/ensemble), converts DXF coords back to
    image-pixel space using the region_plan transform.
    """
    path = Path(dxf_path)
    if not path.exists():
        return None

    wall_entities = _read_dxf_entities(path, layer="WALLS")
    door_entities = _read_dxf_entities(path, layer="DOORS") if include_openings else []
    window_entities = _read_dxf_entities(path, layer="WINS") if include_openings else []

    if region_plan:
        meta = region_plan.get("meta") or {}
        image_shape_meta = meta.get("image_shape") or {}
        image_shape = (
            int(image_shape_meta.get("height", 0)),
            int(image_shape_meta.get("width", 0)),
        )
        transform = meta.get("transform") or {}
        if image_shape[0] > 0 and image_shape[1] > 0:
            bounds = _merge_preview_bounds(
                _region_plan_bounds(region_plan),
                _annotation_wall_bounds_in_dxf_space(region_plan),
            )
            wall_entities = _filter_entities_to_bounds(wall_entities, bounds, margin=24.0)
            door_entities = _filter_entities_to_bounds(door_entities, bounds, margin=24.0)
            window_entities = _filter_entities_to_bounds(window_entities, bounds, margin=24.0)
            wall_entities = entities_to_image_space(wall_entities, image_shape=image_shape, transform=transform)
            door_entities = entities_to_image_space(door_entities, image_shape=image_shape, transform=transform)
            window_entities = entities_to_image_space(window_entities, image_shape=image_shape, transform=transform)

    if image_b64:
        canvas = decode_image(image_b64).copy()
    else:
        all_entities = wall_entities + door_entities + window_entities
        if not all_entities:
            return None
        canvas, offset = _blank_canvas(all_entities)
        wall_entities = _offset_entities(wall_entities, offset)
        door_entities = _offset_entities(door_entities, offset)
        window_entities = _offset_entities(window_entities, offset)

    _draw_entities(canvas, wall_entities, color=(0, 0, 200), thickness=2)
    _draw_entities(canvas, door_entities, color=(0, 180, 0), thickness=2)
    _draw_entities(canvas, window_entities, color=(200, 100, 0), thickness=2)

    return canvas


# ---------------------------------------------------------------------------
# DXF reading
# ---------------------------------------------------------------------------

def _read_dxf_entities(path: Path, *, layer: str) -> list[dict[str, Any]]:
    doc = ezdxf.readfile(str(path))
    entities: list[dict[str, Any]] = []

    for entity in doc.modelspace().query(f'LINE[layer=="{layer}"]'):
        s, e = entity.dxf.start, entity.dxf.end
        entities.append({
            "type": "line",
            "start": {"x": float(s.x), "y": float(s.y)},
            "end": {"x": float(e.x), "y": float(e.y)},
        })

    for entity in doc.modelspace().query(f'LWPOLYLINE[layer=="{layer}"]'):
        points = [(float(p[0]), float(p[1])) for p in entity.get_points("xy")]
        if len(points) < 2:
            continue
        default_width = float(getattr(entity.dxf, "const_width", 0.0) or 0.0)
        if entity.closed and len(points) >= 3:
            entities.append({
                "type": "polyline",
                "points": [{"x": x, "y": y} for x, y in points],
                "closed": True,
                "width": default_width,
            })
            continue
        limit = len(points) if entity.closed else len(points) - 1
        for i in range(limit):
            s, e = points[i], points[(i + 1) % len(points)]
            entities.append({
                "type": "line",
                "start": {"x": s[0], "y": s[1]},
                "end": {"x": e[0], "y": e[1]},
                "width": default_width,
            })

    for entity in doc.modelspace().query(f'ARC[layer=="{layer}"]'):
        cx, cy = float(entity.dxf.center.x), float(entity.dxf.center.y)
        r = float(entity.dxf.radius)
        sa, ea = float(entity.dxf.start_angle), float(entity.dxf.end_angle)
        # Sample arc as line segments
        if ea < sa:
            ea += 360.0
        steps = max(8, int((ea - sa) / 5))
        for j in range(steps):
            a1 = math.radians(sa + (ea - sa) * j / steps)
            a2 = math.radians(sa + (ea - sa) * (j + 1) / steps)
            entities.append({
                "type": "line",
                "start": {"x": cx + r * math.cos(a1), "y": cy + r * math.sin(a1)},
                "end": {"x": cx + r * math.cos(a2), "y": cy + r * math.sin(a2)},
            })

    return entities


# ---------------------------------------------------------------------------
# Coordinate transforms (DXF → image space)
# ---------------------------------------------------------------------------

def _region_plan_bounds(region_plan: dict[str, Any]) -> dict[str, float]:
    points: list[tuple[float, float]] = []
    for region in region_plan.get("regions", []):
        b = region.get("bounds") or {}
        points.extend([(float(b.get("x1", 0)), float(b.get("y1", 0))), (float(b.get("x2", 0)), float(b.get("y2", 0)))])
    if not points:
        return {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0}
    return {
        "min_x": min(p[0] for p in points), "min_y": min(p[1] for p in points),
        "max_x": max(p[0] for p in points), "max_y": max(p[1] for p in points),
    }


def _annotation_wall_bounds_in_dxf_space(region_plan: dict[str, Any]) -> dict[str, float] | None:
    annotations = regions_to_wall_annotations(region_plan)
    if not annotations:
        return None

    meta = region_plan.get("meta") or {}
    image_shape_meta = meta.get("image_shape") or {}
    image_shape = (
        int(image_shape_meta.get("height", 0)),
        int(image_shape_meta.get("width", 0)),
    )
    if image_shape[0] <= 0 or image_shape[1] <= 0:
        return None
    transform = meta.get("transform") or {}

    points: list[tuple[float, float]] = []
    for annotation in annotations:
        if annotation.get("type") != "wall":
            continue

        polygon = annotation.get("polygon") or []
        if polygon:
            for point in polygon:
                dx, dy = image_point_to_dxf_space(
                    float(point.get("x", 0.0)),
                    float(point.get("y", 0.0)),
                    image_shape=image_shape,
                    transform=transform,
                )
                points.append((dx, dy))
            continue

        dx1, dy1 = image_point_to_dxf_space(
            float(annotation.get("x1", 0.0)),
            float(annotation.get("y1", 0.0)),
            image_shape=image_shape,
            transform=transform,
        )
        dx2, dy2 = image_point_to_dxf_space(
            float(annotation.get("x2", 0.0)),
            float(annotation.get("y2", 0.0)),
            image_shape=image_shape,
            transform=transform,
        )
        points.extend(((dx1, dy1), (dx2, dy2)))

    if not points:
        return None

    return {
        "min_x": min(point[0] for point in points),
        "min_y": min(point[1] for point in points),
        "max_x": max(point[0] for point in points),
        "max_y": max(point[1] for point in points),
    }


def _bounds_have_area(bounds: dict[str, float] | None) -> bool:
    if not bounds:
        return False
    return (
        float(bounds.get("max_x", 0.0)) > float(bounds.get("min_x", 0.0))
        or float(bounds.get("max_y", 0.0)) > float(bounds.get("min_y", 0.0))
    )


def _merge_preview_bounds(
    region_bounds: dict[str, float],
    annotation_bounds: dict[str, float] | None,
) -> dict[str, float]:
    if not _bounds_have_area(annotation_bounds):
        return region_bounds
    if not _bounds_have_area(region_bounds):
        return dict(annotation_bounds)
    return {
        "min_x": min(float(region_bounds["min_x"]), float(annotation_bounds["min_x"])),
        "min_y": min(float(region_bounds["min_y"]), float(annotation_bounds["min_y"])),
        "max_x": max(float(region_bounds["max_x"]), float(annotation_bounds["max_x"])),
        "max_y": max(float(region_bounds["max_y"]), float(annotation_bounds["max_y"])),
    }


def _filter_entities_to_bounds(
    entities: list[dict[str, Any]], bounds: dict[str, float], *, margin: float = 0.0,
) -> list[dict[str, Any]]:
    lo_x, lo_y = bounds["min_x"] - margin, bounds["min_y"] - margin
    hi_x, hi_y = bounds["max_x"] + margin, bounds["max_y"] + margin
    filtered: list[dict[str, Any]] = []
    for e in entities:
        if e.get("closed") and e.get("points"):
            xs = [float(point.get("x", 0.0)) for point in (e.get("points") or [])]
            ys = [float(point.get("y", 0.0)) for point in (e.get("points") or [])]
            if xs and ys and min(xs) >= lo_x and max(xs) <= hi_x and min(ys) >= lo_y and max(ys) <= hi_y:
                filtered.append(e)
            continue
        if (
            lo_x <= float((e.get("start") or {}).get("x", 0)) <= hi_x
            and lo_y <= float((e.get("start") or {}).get("y", 0)) <= hi_y
            and lo_x <= float((e.get("end") or {}).get("x", 0)) <= hi_x
            and lo_y <= float((e.get("end") or {}).get("y", 0)) <= hi_y
        ):
            filtered.append(e)
    return filtered


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def _draw_entities(
    canvas: np.ndarray,
    entities: list[dict[str, Any]],
    *,
    color: tuple[int, int, int] = (0, 0, 200),
    thickness: int = 2,
) -> None:
    for e in entities:
        if e.get("closed") and e.get("points"):
            polygon = np.array(
                [
                    (
                        int(round(float(point.get("x", 0.0)))),
                        int(round(float(point.get("y", 0.0)))),
                    )
                    for point in (e.get("points") or [])
                ],
                dtype=np.int32,
            )
            if polygon.shape[0] >= 3:
                cv2.fillPoly(canvas, [polygon], color)
                cv2.polylines(canvas, [polygon], True, color, thickness, cv2.LINE_AA)
            continue
        s, end = e.get("start") or {}, e.get("end") or {}
        entity_thickness = thickness
        if float(e.get("width", 0.0) or 0.0) > 0.0:
            entity_thickness = max(entity_thickness, int(round(float(e["width"]))))
        cv2.line(
            canvas,
            (int(round(float(s.get("x", 0)))), int(round(float(s.get("y", 0))))),
            (int(round(float(end.get("x", 0)))), int(round(float(end.get("y", 0))))),
            color, entity_thickness, cv2.LINE_AA,
        )


def _blank_canvas(entities: list[dict[str, Any]]) -> tuple[np.ndarray, dict[str, float]]:
    xs: list[float] = []
    ys: list[float] = []
    for e in entities:
        if e.get("closed") and e.get("points"):
            xs.extend(float(point.get("x", 0.0)) for point in (e.get("points") or []))
            ys.extend(float(point.get("y", 0.0)) for point in (e.get("points") or []))
            continue
        xs.extend([
            float((e.get("start") or {}).get("x", 0)),
            float((e.get("end") or {}).get("x", 0)),
        ])
        ys.extend([
            float((e.get("start") or {}).get("y", 0)),
            float((e.get("end") or {}).get("y", 0)),
        ])
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    w = max(256, int(max_x - min_x + 80))
    h = max(256, int(max_y - min_y + 80))
    canvas = np.full((h, w, 3), 255, dtype=np.uint8)
    return canvas, {"x": 40 - min_x, "y": 40 - min_y}


def _offset_entities(entities: list[dict[str, Any]], offset: dict[str, float]) -> list[dict[str, Any]]:
    ox, oy = offset["x"], offset["y"]
    shifted: list[dict[str, Any]] = []
    for e in entities:
        if e.get("closed") and e.get("points"):
            shifted.append({
                **e,
                "points": [
                    {
                        "x": float(point.get("x", 0.0)) + ox,
                        "y": float(point.get("y", 0.0)) + oy,
                    }
                    for point in (e.get("points") or [])
                ],
                "width": float(e.get("width", 0.0) or 0.0),
            })
            continue
        shifted.append(
            {
                **e,
                "start": {
                    "x": float((e["start"] or {}).get("x", 0)) + ox,
                    "y": float((e["start"] or {}).get("y", 0)) + oy,
                },
                "end": {
                    "x": float((e["end"] or {}).get("x", 0)) + ox,
                    "y": float((e["end"] or {}).get("y", 0)) + oy,
                },
                "width": float(e.get("width", 0.0) or 0.0),
            }
        )
    return shifted
