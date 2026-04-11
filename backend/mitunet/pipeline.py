from __future__ import annotations

import base64
import time
from typing import Any

import cv2
import numpy as np

from .model import MITUNET_BACKEND
from .preprocess import _predict_wall_mask
from .wall_mask import _extract_walls_from_mask


def infer_mitunet(image_b64: str, **kwargs) -> dict[str, Any]:
    """Run MitUNet inference on a base64-encoded image."""
    t0 = time.time()

    # Decode image (strip data URI prefix if present)
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]
    # Fix padding
    missing_padding = len(image_b64) % 4
    if missing_padding:
        image_b64 += "=" * (4 - missing_padding)
    raw = base64.b64decode(image_b64)
    arr = np.frombuffer(raw, dtype=np.uint8)
    image_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise ValueError("Could not decode image")

    h, w = image_bgr.shape[:2]

    # Get wall mask
    t_model = time.time()
    wall_mask = _predict_wall_mask(image_bgr)
    t_model = time.time() - t_model

    # Generate overlay from mask (image coordinates, before any flip)
    overlay = image_bgr.copy()
    overlay[wall_mask > 127] = [0, 0, 200]  # dark red on walls
    blended = cv2.addWeighted(image_bgr, 0.6, overlay, 0.4, 0)
    _, overlay_png = cv2.imencode(".png", blended)
    overlay_b64 = base64.b64encode(overlay_png.tobytes()).decode("ascii")

    # Extract wall segments (with Y-flip for DXF)
    t_post = time.time()
    walls = _extract_walls_from_mask(wall_mask, h, w)
    t_post = time.time() - t_post

    total = time.time() - t0
    wall_pct = (wall_mask > 127).sum() / (h * w) * 100
    print(f"[MitUNet] model={t_model:.2f}s post={t_post:.2f}s total={total:.2f}s walls={len(walls)} ({wall_pct:.1f}% pixels)")

    return {
        "walls": walls,
        "openings": [],
        "rooms": [],
        "source": MITUNET_BACKEND,
        "inference_debug": {
            "backend": MITUNET_BACKEND,
            "debug_overlay_b64": f"data:image/png;base64,{overlay_b64}",
            "model_variant": "mitunet",
            "wall_pixel_pct": round(wall_pct, 1),
        },
        "_wall_mask": wall_mask,
        "_image_shape": (h, w),
    }
