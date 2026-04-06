from __future__ import annotations

import numpy as np


ROOM_PALETTE = [
    (66, 133, 244),    # Blue
    (219, 68, 55),     # Red
    (244, 180, 0),     # Yellow
    (15, 157, 88),     # Green
    (171, 71, 188),    # Purple
    (255, 112, 67),    # Orange
    (0, 172, 193),     # Teal
    (255, 167, 38),    # Amber
    (121, 85, 72),     # Brown
    (96, 125, 139),    # Blue Grey
    (233, 30, 99),     # Pink
    (0, 150, 136),     # Teal Dark
    (63, 81, 181),     # Indigo
    (205, 220, 57),    # Lime
    (255, 87, 34),     # Deep Orange
]


def generate_region_overlay(room_analysis: dict, image_shape: tuple[int, int]) -> np.ndarray:
    """Generate an RGBA overlay image with each room painted a unique color."""
    h, w = image_shape
    overlay = np.zeros((h, w, 4), dtype=np.uint8)
    rooms = room_analysis.get("rooms", [])
    for i, room in enumerate(rooms):
        region = room.get("region")
        if region is None:
            continue
        mask = region["mask"]
        r, g, b = ROOM_PALETTE[i % len(ROOM_PALETTE)]
        alpha = 100  # ~40% opacity
        overlay[mask, 0] = r
        overlay[mask, 1] = g
        overlay[mask, 2] = b
        overlay[mask, 3] = alpha
    return overlay


def encode_overlay_png(overlay: np.ndarray) -> str:
    """Encode RGBA overlay to base64 PNG."""
    import base64
    import cv2
    success, buf = cv2.imencode(".png", cv2.cvtColor(overlay, cv2.COLOR_RGBA2BGRA))
    if not success:
        return ""
    return base64.b64encode(buf.tobytes()).decode("ascii")
