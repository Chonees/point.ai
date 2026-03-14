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

from .image_utils import decode_image, encode_png_data

ARTIFACT_DIR = Path(tempfile.gettempdir()) / "pointai_artifacts"
ARTIFACT_DIR.mkdir(exist_ok=True)


def save_structure_artifacts(
    *,
    request_id: str,
    structure: dict[str, Any],
    quality_metrics: dict[str, Any],
    image_b64: str | None = None,
    debug_overlay_b64: str | None = None,
) -> dict[str, str]:
    run_dir = ARTIFACT_DIR / request_id
    run_dir.mkdir(parents=True, exist_ok=True)

    structure_path = run_dir / "structure.json"
    metrics_path = run_dir / "quality.json"
    preview_path = run_dir / "preview.png"
    structure_preview_path = run_dir / "structure_preview.png"
    worker_overlay_path = run_dir / "worker_overlay.png"

    structure_path.write_text(json.dumps(structure, indent=2), encoding="utf-8")
    metrics_path.write_text(json.dumps(quality_metrics, indent=2), encoding="utf-8")

    structure_preview = build_preview_image(structure, image_b64=image_b64)
    structure_preview_path.write_bytes(encode_png_data(structure_preview))

    worker_overlay_url = None
    if debug_overlay_b64:
        worker_overlay_path.write_bytes(_decode_overlay(debug_overlay_b64))
        preview_path.write_bytes(worker_overlay_path.read_bytes())
        worker_overlay_url = f"/artifacts/{request_id}/worker_overlay.png"
    else:
        preview_path.write_bytes(structure_preview_path.read_bytes())

    artifact_urls = {
        "preview_url": f"/artifacts/{request_id}/preview.png",
        "structure_url": f"/artifacts/{request_id}/structure.json",
        "quality_url": f"/artifacts/{request_id}/quality.json",
        "structure_preview_url": f"/artifacts/{request_id}/structure_preview.png",
    }
    if worker_overlay_url is not None:
        artifact_urls["worker_overlay_url"] = worker_overlay_url
    return artifact_urls


def build_preview_image(structure: dict[str, Any], image_b64: str | None = None) -> np.ndarray:
    offset_x = 0.0
    offset_y = 0.0
    if image_b64:
        canvas = decode_image(image_b64).copy()
    else:
        canvas, offset_x, offset_y = _blank_canvas(structure)

    for wall in structure.get("walls") or []:
        start, end = wall["polyline"]
        cv2.line(
            canvas,
            (round(start["x"] + offset_x), round(start["y"] + offset_y)),
            (round(end["x"] + offset_x), round(end["y"] + offset_y)),
            (0, 0, 255),
            max(2, round(wall.get("thickness", 4) / 3)),
        )

    for opening in structure.get("openings") or []:
        position = opening["position"]
        radius = max(4, round(opening["span"] / 4))
        color = (0, 200, 0) if opening["kind"] == "door" else (255, 0, 0)
        cv2.circle(
            canvas,
            (round(position["x"] + offset_x), round(position["y"] + offset_y)),
            radius,
            color,
            2,
        )

    return canvas


def _blank_canvas(structure: dict[str, Any]) -> tuple[np.ndarray, float, float]:
    points = [point for wall in structure.get("walls") or [] for point in wall["polyline"]]
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
