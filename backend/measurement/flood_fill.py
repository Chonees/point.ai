from __future__ import annotations

import cv2
import numpy as np

from ..observability import log_event


def flood_fill_bbox(
    annotations: list[dict],
    wall_mask: np.ndarray,
    image_shape: tuple[int, int],
    seed_x: int,
    seed_y: int,
) -> tuple[int, int, int, int, int] | None:
    """Flood fill from seed, return (x1, y1, x2, y2, area_px) or None."""
    region = flood_fill_room_region(annotations, wall_mask, image_shape, seed_x, seed_y)
    if not region:
        return None
    x1, y1, x2, y2 = region["bbox"]
    return x1, y1, x2, y2, int(region["area_px"])


def flood_fill_room_region(
    annotations: list[dict],
    wall_mask: np.ndarray,
    image_shape: tuple[int, int],
    seed_x: int,
    seed_y: int,
    *,
    closed_mask: np.ndarray | None = None,
) -> dict[str, object] | None:
    """Flood fill from seed, return mask/bbox/area/adjusted seed for the detected room."""
    if closed_mask is None:
        closed_mask = _build_closed_mask(annotations, wall_mask, image_shape)
    h, w = image_shape
    seed_x = max(0, min(seed_x, w - 1))
    seed_y = max(0, min(seed_y, h - 1))

    if closed_mask[seed_y, seed_x] != 0:
        seed_x, seed_y = _find_nearest_open(closed_mask, seed_x, seed_y)
        if seed_x < 0:
            return None

    ff_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
    ff_mask[1:-1, 1:-1] = (closed_mask > 0).astype(np.uint8)
    img = np.zeros((h, w), dtype=np.uint8)
    cv2.floodFill(img, ff_mask, (seed_x, seed_y), 128)

    filled = img == 128
    area = int(filled.sum())
    if area < 50:
        return None

    ys, xs = np.where(filled)
    return {
        "mask": filled,
        "bbox": (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())),
        "area_px": area,
        "seed": (int(seed_x), int(seed_y)),
    }


def _build_closed_mask(
    annotations: list[dict],
    wall_mask: np.ndarray,
    image_shape: tuple[int, int],
) -> np.ndarray:
    """Wall mask with door/window gaps painted closed."""
    h, w = image_shape
    closed = np.zeros((h, w), dtype=np.uint8)
    resized = cv2.resize(wall_mask, (w, h), interpolation=cv2.INTER_NEAREST) if wall_mask.shape[:2] != (h, w) else wall_mask
    closed[resized > 127] = 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(closed, cv2.MORPH_CLOSE, kernel, iterations=2)

    for ann in annotations:
        atype = ann.get("type")
        if atype in ("wall", "door", "window", "separator"):
            x1, y1 = int(ann.get("x1", 0)), int(ann.get("y1", 0))
            x2, y2 = int(ann.get("x2", 0)), int(ann.get("y2", 0))
            # Walls and separators thicker to guarantee sealing
            thickness = 14 if atype in ("wall", "separator") else 6
            cv2.line(closed, (x1, y1), (x2, y2), 255, thickness=thickness)

    return closed


def _flood_fill_area(mask: np.ndarray, seed_x: int, seed_y: int) -> int:
    h, w = mask.shape[:2]
    ff_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
    ff_mask[1:-1, 1:-1] = (mask > 0).astype(np.uint8)
    img = np.zeros((h, w), dtype=np.uint8)
    cv2.floodFill(img, ff_mask, (seed_x, seed_y), 128)
    return int((img == 128).sum())


def _find_nearest_open(mask: np.ndarray, x: int, y: int, radius: int = 20) -> tuple[int, int]:
    h, w = mask.shape[:2]
    for r in range(1, radius + 1):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and mask[ny, nx] == 0:
                    return nx, ny
    return -1, -1
