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

from .image_utils import decode_image, encode_png_data


def build_dxf_preview(
    dxf_path: str,
    *,
    image_b64: str | None = None,
    region_plan: dict[str, Any] | None = None,
) -> np.ndarray | None:
    """Build a preview image from the actual DXF entities.

    For mask_regions mode (MitUNet/ensemble), converts DXF coords back to
    image-pixel space using the region_plan transform.
    """
    path = Path(dxf_path)
    if not path.exists():
        return None

    wall_entities = _read_dxf_entities(path, layer="WALLS")
    door_entities = _read_dxf_entities(path, layer="DOORS")
    window_entities = _read_dxf_entities(path, layer="WINS")

    if region_plan:
        meta = region_plan.get("meta") or {}
        image_shape_meta = meta.get("image_shape") or {}
        image_shape = (
            int(image_shape_meta.get("height", 0)),
            int(image_shape_meta.get("width", 0)),
        )
        transform = meta.get("transform") or {}
        if image_shape[0] > 0 and image_shape[1] > 0:
            bounds = _region_plan_bounds(region_plan)
            wall_entities = _filter_entities_to_bounds(wall_entities, bounds, margin=24.0)
            door_entities = _filter_entities_to_bounds(door_entities, bounds, margin=24.0)
            window_entities = _filter_entities_to_bounds(window_entities, bounds, margin=24.0)
            wall_entities = _entities_to_image_space(wall_entities, image_shape=image_shape, transform=transform)
            door_entities = _entities_to_image_space(door_entities, image_shape=image_shape, transform=transform)
            window_entities = _entities_to_image_space(window_entities, image_shape=image_shape, transform=transform)

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
        entities.append({"start": {"x": float(s.x), "y": float(s.y)}, "end": {"x": float(e.x), "y": float(e.y)}})

    for entity in doc.modelspace().query(f'LWPOLYLINE[layer=="{layer}"]'):
        points = [(float(p[0]), float(p[1])) for p in entity.get_points("xy")]
        if len(points) < 2:
            continue
        limit = len(points) if entity.closed else len(points) - 1
        for i in range(limit):
            s, e = points[i], points[(i + 1) % len(points)]
            entities.append({"start": {"x": s[0], "y": s[1]}, "end": {"x": e[0], "y": e[1]}})

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
                "start": {"x": cx + r * math.cos(a1), "y": cy + r * math.sin(a1)},
                "end": {"x": cx + r * math.cos(a2), "y": cy + r * math.sin(a2)},
            })

    return entities


# ---------------------------------------------------------------------------
# Coordinate transforms (DXF → image space)
# ---------------------------------------------------------------------------

def _dxf_to_image_point(
    dx: float, dy: float, *, image_shape: tuple[int, int], transform: dict[str, Any],
) -> dict[str, float]:
    height, _ = image_shape
    scale = float(transform.get("scale", 1.0) or 1.0)
    offset_x = float(transform.get("offset_x", 0.0) or 0.0)
    offset_y = float(transform.get("offset_y", 0.0) or 0.0)
    ix = (dx - offset_x) / scale
    iy = float(height) - ((dy - offset_y) / scale)
    return {"x": ix, "y": iy}


def _entities_to_image_space(
    entities: list[dict[str, Any]], *, image_shape: tuple[int, int], transform: dict[str, Any],
) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    for e in entities:
        s, end = e.get("start") or {}, e.get("end") or {}
        projected.append({
            **e,
            "start": _dxf_to_image_point(float(s.get("x", 0)), float(s.get("y", 0)), image_shape=image_shape, transform=transform),
            "end": _dxf_to_image_point(float(end.get("x", 0)), float(end.get("y", 0)), image_shape=image_shape, transform=transform),
        })
    return projected


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


def _filter_entities_to_bounds(
    entities: list[dict[str, Any]], bounds: dict[str, float], *, margin: float = 0.0,
) -> list[dict[str, Any]]:
    lo_x, lo_y = bounds["min_x"] - margin, bounds["min_y"] - margin
    hi_x, hi_y = bounds["max_x"] + margin, bounds["max_y"] + margin
    return [
        e for e in entities
        if lo_x <= float((e.get("start") or {}).get("x", 0)) <= hi_x
        and lo_y <= float((e.get("start") or {}).get("y", 0)) <= hi_y
        and lo_x <= float((e.get("end") or {}).get("x", 0)) <= hi_x
        and lo_y <= float((e.get("end") or {}).get("y", 0)) <= hi_y
    ]


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
        s, end = e.get("start") or {}, e.get("end") or {}
        cv2.line(
            canvas,
            (int(round(float(s.get("x", 0)))), int(round(float(s.get("y", 0))))),
            (int(round(float(end.get("x", 0)))), int(round(float(end.get("y", 0))))),
            color, thickness, cv2.LINE_AA,
        )


def _blank_canvas(entities: list[dict[str, Any]]) -> tuple[np.ndarray, dict[str, float]]:
    xs = [float((e.get("start") or {}).get("x", 0)) for e in entities] + [float((e.get("end") or {}).get("x", 0)) for e in entities]
    ys = [float((e.get("start") or {}).get("y", 0)) for e in entities] + [float((e.get("end") or {}).get("y", 0)) for e in entities]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    w = max(256, int(max_x - min_x + 80))
    h = max(256, int(max_y - min_y + 80))
    canvas = np.full((h, w, 3), 255, dtype=np.uint8)
    return canvas, {"x": 40 - min_x, "y": 40 - min_y}


def _offset_entities(entities: list[dict[str, Any]], offset: dict[str, float]) -> list[dict[str, Any]]:
    ox, oy = offset["x"], offset["y"]
    return [
        {**e, "start": {"x": float((e["start"] or {}).get("x", 0)) + ox, "y": float((e["start"] or {}).get("y", 0)) + oy},
               "end": {"x": float((e["end"] or {}).get("x", 0)) + ox, "y": float((e["end"] or {}).get("y", 0)) + oy}}
        for e in entities
    ]
