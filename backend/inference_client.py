"""
inference_client.py
Local heuristic inference adapter for the v2 image pipeline.

Supports both color-coded synthetic images and real grayscale floor plans.
Detection strategy:
  - Walls: morphological H/V line extraction on binarized image
  - Doors: color hint (synthetic) or arc/gap detection (real plans)
  - Windows: color hint (synthetic) or triple-line gap detection (real plans)
"""
from __future__ import annotations

import os
from typing import Any

import cv2
import numpy as np

from .image_utils import decode_image

HEURISTIC_BACKEND = "heuristic_local"
MIN_SEGMENT_LENGTH = 20
MIN_WALL_THICKNESS = 2   # minimum rows (H) or cols (V) for a valid wall segment

# Thresholds for color-coded synthetic images
_GREEN_DOOR = dict(g_min=140, r_max=130, b_max=130)
_BLUE_WIN = dict(b_min=140, g_max=150, r_max=130)


def infer_structure(image_b64: str) -> dict[str, Any]:
    backend = os.getenv("POINTAI_INFERENCE_BACKEND", HEURISTIC_BACKEND)
    if backend != HEURISTIC_BACKEND:
        raise ValueError(f"Unsupported inference backend: {backend}")
    return infer_heuristic_structure(image_b64)


def infer_heuristic_structure(image_b64: str) -> dict[str, Any]:
    image = decode_image(image_b64)
    height, width = image.shape[:2]

    is_color_coded = _is_color_coded(image)

    if is_color_coded:
        door_mask = _color_door_mask(image)
        window_mask = _color_window_mask(image)
    else:
        door_mask = np.zeros((height, width), dtype=np.uint8)
        window_mask = np.zeros((height, width), dtype=np.uint8)

    opening_mask = cv2.bitwise_or(door_mask, window_mask)
    binary = _binarize(image)
    wall_binary = _remove_openings(binary, opening_mask)

    horizontal_segments = _extract_h_segments(wall_binary)
    vertical_segments = _extract_v_segments(wall_binary)
    walls = _segments_to_walls(horizontal_segments, vertical_segments)

    if is_color_coded:
        openings = _extract_color_openings(door_mask, window_mask)
    else:
        openings = _extract_real_openings(binary, horizontal_segments, vertical_segments)

    return {
        "model": "Heuristic Image Structure",
        "source": HEURISTIC_BACKEND,
        "walls": walls,
        "openings": openings,
        "structure_meta": {
            "image_size": {"width": width, "height": height},
            "scale_status": "unverified",
            "unit": "pixel",
        },
        "inference_debug": {
            "raw_wall_fragments": len(walls),
            "raw_opening_detections": len(openings),
            "color_coded": is_color_coded,
        },
    }


# ---------------------------------------------------------------------------
# Image mode detection
# ---------------------------------------------------------------------------

def _is_color_coded(image: np.ndarray) -> bool:
    """Return True if the image has synthetic color-coded doors/windows."""
    if len(image.shape) < 3 or image.shape[2] < 3:
        return False
    b, g, r = cv2.split(image)
    green_pixels = int(np.sum((g > 140) & (r < 130) & (b < 130)))
    blue_pixels = int(np.sum((b > 140) & (g < 150) & (r < 130)))
    return (green_pixels + blue_pixels) > 50


# ---------------------------------------------------------------------------
# Binarization — works on both color and grayscale input
# ---------------------------------------------------------------------------

def _binarize(image: np.ndarray) -> np.ndarray:
    """Return a binary mask where walls are white (255)."""
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    # Gaussian blur to suppress noise and thin lines (text, hatching)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)

    # Otsu threshold — works on clean plans; adaptive for scanned plans
    _, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # If very little dark content, the plan may be inverted or light-background
    dark_ratio = np.sum(otsu > 0) / otsu.size
    if dark_ratio > 0.5:
        # Too much "dark" — invert
        otsu = cv2.bitwise_not(otsu)

    # Morphological open to remove isolated noise pixels
    kernel_noise = np.ones((2, 2), dtype=np.uint8)
    clean = cv2.morphologyEx(otsu, cv2.MORPH_OPEN, kernel_noise)
    return clean


def _remove_openings(binary: np.ndarray, opening_mask: np.ndarray) -> np.ndarray:
    if np.any(opening_mask > 0):
        inv = cv2.bitwise_not(opening_mask)
        return cv2.bitwise_and(binary, inv)
    return binary


# ---------------------------------------------------------------------------
# Color-coded door/window masks (synthetic images)
# ---------------------------------------------------------------------------

def _color_door_mask(image: np.ndarray) -> np.ndarray:
    b, g, r = cv2.split(image)
    return np.where(
        (g > _GREEN_DOOR["g_min"]) & (r < _GREEN_DOOR["r_max"]) & (b < _GREEN_DOOR["b_max"]),
        np.uint8(255), np.uint8(0),
    ).astype(np.uint8)


def _color_window_mask(image: np.ndarray) -> np.ndarray:
    b, g, r = cv2.split(image)
    return np.where(
        (b > _BLUE_WIN["b_min"]) & (g < _BLUE_WIN["g_max"]) & (r < _BLUE_WIN["r_max"]),
        np.uint8(255), np.uint8(0),
    ).astype(np.uint8)


# ---------------------------------------------------------------------------
# Morphological wall segment extraction
# ---------------------------------------------------------------------------

def _extract_h_segments(binary: np.ndarray) -> list[dict[str, float]]:
    """Extract horizontal wall segments via morphological open + connected components.

    Replaces the previous Python pixel-by-pixel RLE: connectedComponentsWithStats
    runs in C and is orders of magnitude faster on large images.
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (MIN_SEGMENT_LENGTH, 1))
    h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    _, _, stats, _ = cv2.connectedComponentsWithStats(h_lines, connectivity=8)
    return [
        {
            "x1": float(s[cv2.CC_STAT_LEFT]),
            "x2": float(s[cv2.CC_STAT_LEFT] + s[cv2.CC_STAT_WIDTH] - 1),
            "y1": float(s[cv2.CC_STAT_TOP]),
            "y2": float(s[cv2.CC_STAT_TOP] + s[cv2.CC_STAT_HEIGHT] - 1),
        }
        for s in stats[1:]  # stats[0] is the background component
        if s[cv2.CC_STAT_WIDTH] >= MIN_SEGMENT_LENGTH and s[cv2.CC_STAT_HEIGHT] >= MIN_WALL_THICKNESS
    ]


def _extract_v_segments(binary: np.ndarray) -> list[dict[str, float]]:
    """Extract vertical wall segments via morphological open + connected components."""
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, MIN_SEGMENT_LENGTH))
    v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    _, _, stats, _ = cv2.connectedComponentsWithStats(v_lines, connectivity=8)
    return [
        {
            "x1": float(s[cv2.CC_STAT_LEFT]),
            "x2": float(s[cv2.CC_STAT_LEFT] + s[cv2.CC_STAT_WIDTH] - 1),
            "y1": float(s[cv2.CC_STAT_TOP]),
            "y2": float(s[cv2.CC_STAT_TOP] + s[cv2.CC_STAT_HEIGHT] - 1),
        }
        for s in stats[1:]
        if s[cv2.CC_STAT_HEIGHT] >= MIN_SEGMENT_LENGTH and s[cv2.CC_STAT_WIDTH] >= MIN_WALL_THICKNESS
    ]


def _segments_to_walls(
    h_segs: list[dict[str, float]],
    v_segs: list[dict[str, float]],
) -> list[dict[str, Any]]:
    walls = []
    counter = 0
    for seg in h_segs:
        counter += 1
        y = (seg["y1"] + seg["y2"]) / 2.0
        walls.append({
            "id": f"raw-wall-{counter:04d}",
            "orientation": "horizontal",
            "polyline": [{"x": seg["x1"], "y": y}, {"x": seg["x2"], "y": y}],
            "thickness": max(1.0, seg["y2"] - seg["y1"] + 1.0),
            "is_exterior": False,
            "confidence": 0.7,
        })
    for seg in v_segs:
        counter += 1
        x = (seg["x1"] + seg["x2"]) / 2.0
        walls.append({
            "id": f"raw-wall-{counter:04d}",
            "orientation": "vertical",
            "polyline": [{"x": x, "y": seg["y1"]}, {"x": x, "y": seg["y2"]}],
            "thickness": max(1.0, seg["x2"] - seg["x1"] + 1.0),
            "is_exterior": False,
            "confidence": 0.7,
        })
    return walls


# ---------------------------------------------------------------------------
# Opening extraction — color-coded (synthetic)
# ---------------------------------------------------------------------------

def _extract_color_openings(
    door_mask: np.ndarray,
    window_mask: np.ndarray,
) -> list[dict[str, Any]]:
    openings = []
    counter = 0
    for kind, mask in (("door", door_mask), ("window", window_mask)):
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if max(w, h) < 4:
                continue
            counter += 1
            openings.append({
                "id": f"raw-opening-{counter:04d}",
                "kind": kind,
                "position": {"x": x + w / 2.0, "y": y + h / 2.0},
                "span": float(max(w, h)),
                "orientation": "horizontal" if w >= h else "vertical",
                "confidence": 0.85 if kind == "door" else 0.9,
            })
    return openings


# ---------------------------------------------------------------------------
# Opening extraction — real floor plans (grayscale)
# ---------------------------------------------------------------------------

def _extract_real_openings(
    binary: np.ndarray,
    h_segs: list[dict[str, float]],
    v_segs: list[dict[str, float]],
) -> list[dict[str, Any]]:
    """Detect openings on real floor plans using two strategies:
    1. Arc detection (quarter-circle door swings) via HoughCircles.
    2. Gap detection in wall segments where the wall has a break.
    """
    openings: list[dict[str, Any]] = []
    counter = 0

    # Strategy 1: HoughCircles to find door arcs
    gray = cv2.bitwise_not(binary)  # dark walls on white background
    blurred = cv2.GaussianBlur(gray, (5, 5), 1)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.5,
        minDist=20,
        param1=60,
        param2=25,
        minRadius=10,
        maxRadius=120,
    )
    if circles is not None:
        for cx, cy, r in np.round(circles[0]).astype(int):
            counter += 1
            openings.append({
                "id": f"raw-opening-{counter:04d}",
                "kind": "door",
                "position": {"x": float(cx), "y": float(cy)},
                "span": float(r * 2),
                "orientation": "horizontal",
                "confidence": 0.75,
            })

    # Strategy 2: Gap detection — look for breaks in horizontal/vertical wall segments
    gap_openings = _detect_wall_gaps(binary, h_segs, v_segs, start_counter=counter)
    counter += len(gap_openings)
    openings.extend(gap_openings)

    return openings


def _detect_wall_gaps(
    binary: np.ndarray,
    h_segs: list[dict[str, float]],
    v_segs: list[dict[str, float]],
    start_counter: int,
) -> list[dict[str, Any]]:
    """Find gaps (white regions) inside the bounding span of detected wall segments.
    Gaps are likely doors or windows.
    """
    openings: list[dict[str, Any]] = []
    counter = start_counter
    height, width = binary.shape

    for seg in h_segs:
        y_center = int((seg["y1"] + seg["y2"]) / 2)
        thickness = max(3, int(seg["y2"] - seg["y1"] + 2))
        y1 = max(0, y_center - thickness)
        y2 = min(height - 1, y_center + thickness)
        x1 = int(seg["x1"])
        x2 = int(seg["x2"])
        if x2 <= x1:
            continue
        row_strip = binary[y1:y2 + 1, x1:x2 + 1]
        # collapse vertically: a column is "wall" if any pixel is dark
        col_present = np.any(row_strip > 0, axis=0).astype(np.uint8) * 255
        gaps = _find_gaps_in_1d(col_present, min_gap=12, min_context=8)
        for gap_start, gap_end in gaps:
            span = gap_end - gap_start
            counter += 1
            openings.append({
                "id": f"raw-opening-{counter:04d}",
                "kind": "window",  # gaps in walls default to window; door has arc
                "position": {"x": float(x1 + gap_start + span / 2), "y": float(y_center)},
                "span": float(span),
                "orientation": "horizontal",
                "confidence": 0.65,
            })

    for seg in v_segs:
        x_center = int((seg["x1"] + seg["x2"]) / 2)
        thickness = max(3, int(seg["x2"] - seg["x1"] + 2))
        x1 = max(0, x_center - thickness)
        x2 = min(width - 1, x_center + thickness)
        y1 = int(seg["y1"])
        y2 = int(seg["y2"])
        if y2 <= y1:
            continue
        col_strip = binary[y1:y2 + 1, x1:x2 + 1]
        row_present = np.any(col_strip > 0, axis=1).astype(np.uint8) * 255
        gaps = _find_gaps_in_1d(row_present, min_gap=12, min_context=8)
        for gap_start, gap_end in gaps:
            span = gap_end - gap_start
            counter += 1
            openings.append({
                "id": f"raw-opening-{counter:04d}",
                "kind": "window",
                "position": {"x": float(x_center), "y": float(y1 + gap_start + span / 2)},
                "span": float(span),
                "orientation": "vertical",
                "confidence": 0.65,
            })

    return openings


def _find_gaps_in_1d(
    presence: np.ndarray,
    min_gap: int,
    min_context: int,
) -> list[tuple[int, int]]:
    """Return (start, end) of gaps in a 1D binary array.
    A gap is a run of zeros with at least min_context pixels of wall on each side.
    """
    n = len(presence)
    gaps: list[tuple[int, int]] = []
    i = 0
    while i < n:
        if presence[i] == 0:
            start = i
            while i < n and presence[i] == 0:
                i += 1
            end = i
            gap_len = end - start
            if gap_len >= min_gap:
                left_context = start >= min_context
                right_context = (n - end) >= min_context
                if left_context and right_context:
                    gaps.append((start, end))
        else:
            i += 1
    return gaps
