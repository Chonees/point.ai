"""
artifacts.py
Artifact storage for v2 debug outputs.
"""
from __future__ import annotations

import json
import base64
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .coordinate_space import structure_to_image_space
from .image_utils import decode_image, encode_png_data
from .structural_generator import build_render_plan

ARTIFACT_DIR = Path(tempfile.gettempdir()) / "pointai_artifacts"
ARTIFACT_DIR.mkdir(exist_ok=True)


def save_structure_artifacts(
    *,
    request_id: str,
    structure: dict[str, Any],
    quality_metrics: dict[str, Any],
    image_b64: str | None = None,
    debug_overlay_b64: str | None = None,
    auto_annotations: list[dict[str, Any]] | None = None,
    dxf_preview: np.ndarray | None = None,
) -> dict[str, str]:
    run_dir = ARTIFACT_DIR / request_id
    run_dir.mkdir(parents=True, exist_ok=True)

    structure_path = run_dir / "structure.json"
    metrics_path = run_dir / "quality.json"
    preview_path = run_dir / "preview.png"
    structure_preview_path = run_dir / "structure_preview.png"
    worker_overlay_path = run_dir / "worker_overlay.png"
    region_plan_path = run_dir / "dxf_region_plan.json"
    region_debug_path = run_dir / "mitunet_region_debug.json"
    provenance_path = run_dir / "provenance.json"

    structure_path.write_text(json.dumps(structure, indent=2), encoding="utf-8")
    metrics_path.write_text(json.dumps(quality_metrics, indent=2), encoding="utf-8")

    structure_preview = build_preview_image(structure, image_b64=image_b64, auto_annotations=auto_annotations)
    structure_preview_path.write_bytes(encode_png_data(structure_preview))

    # Use DXF preview (actual DXF output) as main preview when available
    if dxf_preview is not None:
        preview_path.write_bytes(encode_png_data(dxf_preview))
    elif debug_overlay_b64:
        worker_overlay_path.write_bytes(_decode_overlay(debug_overlay_b64))
        preview_path.write_bytes(worker_overlay_path.read_bytes())
    else:
        preview_path.write_bytes(structure_preview_path.read_bytes())

    worker_overlay_url = None
    if debug_overlay_b64:
        if not worker_overlay_path.exists():
            worker_overlay_path.write_bytes(_decode_overlay(debug_overlay_b64))
        worker_overlay_url = f"/artifacts/{request_id}/worker_overlay.png"

    artifact_urls = {
        "preview_url": f"/artifacts/{request_id}/preview.png",
        "structure_url": f"/artifacts/{request_id}/structure.json",
        "quality_url": f"/artifacts/{request_id}/quality.json",
        "structure_preview_url": f"/artifacts/{request_id}/structure_preview.png",
    }
    structure_meta = structure.get("structure_meta", {})
    if structure_meta.get("dxf_region_plan") is not None:
        region_plan_path.write_text(json.dumps(structure_meta["dxf_region_plan"], indent=2), encoding="utf-8")
        artifact_urls["dxf_region_plan_url"] = f"/artifacts/{request_id}/dxf_region_plan.json"
    if structure_meta.get("mitunet_region_debug") is not None:
        region_debug_path.write_text(json.dumps(structure_meta["mitunet_region_debug"], indent=2), encoding="utf-8")
        artifact_urls["mitunet_region_debug_url"] = f"/artifacts/{request_id}/mitunet_region_debug.json"
    if structure_meta.get("provenance") is not None:
        provenance_path.write_text(json.dumps(structure_meta["provenance"], indent=2), encoding="utf-8")
        artifact_urls["provenance_url"] = f"/artifacts/{request_id}/provenance.json"
    if worker_overlay_url is not None:
        artifact_urls["worker_overlay_url"] = worker_overlay_url
    return artifact_urls


def build_preview_image(
    structure: dict[str, Any],
    image_b64: str | None = None,
    auto_annotations: list[dict[str, Any]] | None = None,
) -> np.ndarray:
    preview_structure = structure
    offset_x = 0.0
    offset_y = 0.0
    if image_b64:
        canvas = decode_image(image_b64).copy()
        preview_structure = structure_to_image_space(structure, image_height=canvas.shape[0])
    else:
        preview_structure = structure_to_image_space(structure)
        canvas, offset_x, offset_y = _blank_canvas(preview_structure)

    rendered_opening_ids = _draw_render_plan_preview(
        canvas,
        preview_structure,
        offset_x=offset_x,
        offset_y=offset_y,
    )
    if rendered_opening_ids is None:
        _draw_centerline_fallback(canvas, preview_structure, offset_x=offset_x, offset_y=offset_y)
        rendered_opening_ids = set()

    _draw_unanchored_openings(
        canvas,
        preview_structure,
        rendered_opening_ids=rendered_opening_ids,
        offset_x=offset_x,
        offset_y=offset_y,
    )

    # Draw auto-detected openings from CubiCasa (annotation format)
    for ann in auto_annotations or []:
        ann_type = ann.get("type", "")
        if ann_type not in ("door", "window"):
            continue
        x1 = round(float(ann.get("x1", 0)) + offset_x)
        y1 = round(float(ann.get("y1", 0)) + offset_y)
        x2 = round(float(ann.get("x2", 0)) + offset_x)
        y2 = round(float(ann.get("y2", 0)) + offset_y)
        color = (0, 220, 0) if ann_type == "door" else (255, 100, 0)
        cv2.line(canvas, (x1, y1), (x2, y2), color, 3)
        # Label
        mid_x, mid_y = (x1 + x2) // 2, (y1 + y2) // 2
        label = "D" if ann_type == "door" else "W"
        cv2.putText(canvas, label, (mid_x - 5, mid_y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

    return canvas


def build_render_plan_preview_image(
    render_plan: dict[str, Any],
    *,
    image_b64: str | None = None,
    include_openings: bool = True,
) -> np.ndarray:
    if image_b64:
        canvas = decode_image(image_b64).copy()
        offset_x = 0.0
        offset_y = 0.0
    else:
        canvas, offset_x, offset_y = _blank_canvas_from_render_plan(render_plan)

    _draw_wall_entities(
        canvas,
        render_plan.get("wall_lines") or [],
        offset_x=offset_x,
        offset_y=offset_y,
        color=(0, 0, 255),
        thickness=2,
    )
    if include_openings:
        _draw_render_plan_openings(canvas, render_plan, offset_x=offset_x, offset_y=offset_y)
    return canvas


def _draw_render_plan_preview(
    canvas: np.ndarray,
    structure: dict[str, Any],
    *,
    offset_x: float,
    offset_y: float,
) -> set[str] | None:
    walls = structure.get("walls") or []
    if not walls:
        return set()

    try:
        render_plan = build_render_plan(structure)
    except Exception:
        return None

    _draw_wall_entities(
        canvas,
        render_plan.get("wall_lines") or [],
        offset_x=offset_x,
        offset_y=offset_y,
        color=(0, 0, 255),
        thickness=2,
    )
    return _draw_render_plan_openings(canvas, render_plan, offset_x=offset_x, offset_y=offset_y)


def _draw_centerline_fallback(
    canvas: np.ndarray,
    structure: dict[str, Any],
    *,
    offset_x: float,
    offset_y: float,
) -> None:
    for wall in structure.get("walls") or []:
        polygon = wall.get("polygon") or []
        if len(polygon) >= 3:
            contour = np.array(
                [
                    [
                        round(float(point["x"]) + offset_x),
                        round(float(point["y"]) + offset_y),
                    ]
                    for point in polygon
                ],
                dtype=np.int32,
            )
            cv2.polylines(canvas, [contour], True, (0, 0, 255), 2, cv2.LINE_AA)
            continue
        start, end = wall["polyline"]
        cv2.line(
            canvas,
            (round(start["x"] + offset_x), round(start["y"] + offset_y)),
            (round(end["x"] + offset_x), round(end["y"] + offset_y)),
            (0, 0, 255),
            max(2, round(wall.get("thickness", 4) / 3)),
            cv2.LINE_AA,
        )


def _draw_unanchored_openings(
    canvas: np.ndarray,
    structure: dict[str, Any],
    *,
    rendered_opening_ids: set[str],
    offset_x: float,
    offset_y: float,
) -> None:
    for opening in structure.get("openings") or []:
        opening_id = str(opening.get("id", ""))
        if opening_id and opening_id in rendered_opening_ids:
            continue
        position = opening.get("position") or {}
        radius = max(4, round(float(opening.get("span", 8.0)) / 4))
        color = (0, 200, 0) if opening.get("kind") == "door" else (0, 165, 255)
        cv2.circle(
            canvas,
            (round(float(position.get("x", 0.0)) + offset_x), round(float(position.get("y", 0.0)) + offset_y)),
            radius,
            color,
            2,
            cv2.LINE_AA,
        )


def _draw_wall_entities(
    canvas: np.ndarray,
    wall_entities: list[dict[str, Any]],
    *,
    offset_x: float,
    offset_y: float,
    color: tuple[int, int, int],
    thickness: int,
) -> None:
    for entity in wall_entities:
        start = entity.get("start") or {}
        end = entity.get("end") or {}
        cv2.line(
            canvas,
            (round(float(start.get("x", 0.0)) + offset_x), round(float(start.get("y", 0.0)) + offset_y)),
            (round(float(end.get("x", 0.0)) + offset_x), round(float(end.get("y", 0.0)) + offset_y)),
            color,
            thickness,
            cv2.LINE_AA,
        )


def _draw_render_plan_openings(
    canvas: np.ndarray,
    render_plan: dict[str, Any],
    *,
    offset_x: float,
    offset_y: float,
) -> set[str]:
    wall_map = {
        str(wall.get("id")): wall
        for wall in render_plan.get("wall_geometries") or []
        if wall.get("id") is not None
    }
    rendered: set[str] = set()
    openings_by_wall = render_plan.get("openings_by_wall") or {}
    for wall_id, openings in openings_by_wall.items():
        wall = wall_map.get(str(wall_id))
        if not wall:
            continue
        for opening in openings or []:
            opening_id = str(opening.get("id", ""))
            if opening.get("kind") == "door":
                _draw_door_opening_preview(canvas, wall, opening, offset_x=offset_x, offset_y=offset_y)
            else:
                _draw_window_opening_preview(canvas, wall, opening, offset_x=offset_x, offset_y=offset_y)
            if opening_id:
                rendered.add(opening_id)
    return rendered


def _draw_window_opening_preview(
    canvas: np.ndarray,
    wall: dict[str, Any],
    opening: dict[str, Any],
    *,
    offset_x: float,
    offset_y: float,
) -> None:
    color = (0, 165, 255)
    thickness = max(1.0, float(wall.get("draw_thickness", 4.0)))
    start = float(opening.get("start", 0.0))
    end = float(opening.get("end", start))
    tick = max(2, int(round(thickness / 4.0)))

    if wall.get("orientation") == "horizontal":
        y = float(wall.get("coord", 0.0)) + (thickness / 2.0)
        x1 = int(round(start + offset_x))
        x2 = int(round(end + offset_x))
        cy = int(round(y + offset_y))
        cv2.line(canvas, (x1, cy), (x2, cy), color, 2, cv2.LINE_AA)
        cv2.line(canvas, (x1, cy - tick), (x1, cy + tick), color, 1, cv2.LINE_AA)
        cv2.line(canvas, (x2, cy - tick), (x2, cy + tick), color, 1, cv2.LINE_AA)
        return

    x = float(wall.get("coord", 0.0)) + (thickness / 2.0)
    y1 = int(round(start + offset_y))
    y2 = int(round(end + offset_y))
    cx = int(round(x + offset_x))
    cv2.line(canvas, (cx, y1), (cx, y2), color, 2, cv2.LINE_AA)
    cv2.line(canvas, (cx - tick, y1), (cx + tick, y1), color, 1, cv2.LINE_AA)
    cv2.line(canvas, (cx - tick, y2), (cx + tick, y2), color, 1, cv2.LINE_AA)


def _draw_door_opening_preview(
    canvas: np.ndarray,
    wall: dict[str, Any],
    opening: dict[str, Any],
    *,
    offset_x: float,
    offset_y: float,
) -> None:
    color = (0, 200, 0)
    door_type = str(opening.get("door_type", "normal"))
    wall_thickness = max(1.0, float(wall.get("draw_thickness", 4.0)))
    start = float(opening.get("start", 0.0))
    end = float(opening.get("end", start))
    span = max(1.0, float(opening.get("span", end - start)))
    side = opening.get("side")

    if door_type in {"garage", "sliding"}:
        _draw_window_opening_preview(canvas, wall, opening, offset_x=offset_x, offset_y=offset_y)
        return

    swing = opening.get("swing") or _default_swing(side)
    if wall.get("orientation") == "horizontal":
        hinge_x = start
        hinge_y = float(wall.get("coord", 0.0)) + wall_thickness if side == "bottom" else float(wall.get("coord", 0.0))
        direction = -1.0 if swing == "down" else 1.0
        p1 = (int(round(hinge_x + offset_x)), int(round(hinge_y + offset_y)))
        p2 = (int(round(hinge_x + offset_x)), int(round(hinge_y + (direction * span) + offset_y)))
    else:
        hinge_y = start
        hinge_x = float(wall.get("coord", 0.0)) + wall_thickness if side == "left" else float(wall.get("coord", 0.0))
        direction = -1.0 if swing == "left" else 1.0
        p1 = (int(round(hinge_x + offset_x)), int(round(hinge_y + offset_y)))
        p2 = (int(round(hinge_x + (direction * span) + offset_x)), int(round(hinge_y + offset_y)))

    cv2.circle(canvas, p1, 3, color, -1, cv2.LINE_AA)
    cv2.line(canvas, p1, p2, color, 2, cv2.LINE_AA)


def _blank_canvas_from_render_plan(render_plan: dict[str, Any]) -> tuple[np.ndarray, float, float]:
    points: list[tuple[float, float]] = []
    for entity in render_plan.get("wall_lines") or []:
        start = entity.get("start") or {}
        end = entity.get("end") or {}
        points.append((float(start.get("x", 0.0)), float(start.get("y", 0.0))))
        points.append((float(end.get("x", 0.0)), float(end.get("y", 0.0))))

    if not points:
        return np.full((512, 512, 3), 255, dtype=np.uint8), 0.0, 0.0

    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    width = max(256, round(max_x - min_x + 80))
    height = max(256, round(max_y - min_y + 80))
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    return canvas, 40 - min_x, 40 - min_y


def _default_swing(side: str | None) -> str | None:
    return {
        "bottom": "up",
        "top": "down",
        "left": "right",
        "right": "left",
    }.get(side)


def _blank_canvas(structure: dict[str, Any]) -> tuple[np.ndarray, float, float]:
    points = []
    for wall in structure.get("walls") or []:
        polygon = wall.get("polygon") or []
        if len(polygon) >= 3:
            points.extend(polygon)
            continue
        points.extend(wall.get("polyline") or [])
    if not points:
        return np.full((512, 512, 3), 255, dtype=np.uint8), 0.0, 0.0

    min_x = min(point["x"] for point in points)
    max_x = max(point["x"] for point in points)
    min_y = min(point["y"] for point in points)
    max_y = max(point["y"] for point in points)
    width = max(256, round(max_x - min_x + 80))
    height = max(256, round(max_y - min_y + 80))
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)

    offset_x = 40 - min_x
    offset_y = 40 - min_y
    return canvas, offset_x, offset_y


def _decode_overlay(debug_overlay_b64: str) -> bytes:
    raw = debug_overlay_b64.split(",", 1)[1] if "," in debug_overlay_b64 else debug_overlay_b64
    return base64.b64decode(raw)
