"""
scale_calibrator.py — Calculate inches-per-pixel scale from labeled floor-plan regions.

Supported calibration modes:
1. total_area_sqft + room labels (preferred)
2. legacy per-room sqft labels (fallback)
"""
from __future__ import annotations

import math

import cv2
import numpy as np

from .observability import log_event


def calibrate_scale(
    annotations: list[dict],
    wall_mask: np.ndarray,
    image_shape: tuple[int, int],
    *,
    total_area_sqft: float | None = None,
) -> dict[str, object] | None:
    """Compute scale + room-region context for dimension rendering."""
    labels = [a for a in annotations if a.get("type") == "label"]
    if not labels:
        log_event("scale_calibration_skipped", reason="no_labels")
        return None

    closed_mask = _build_closed_mask(annotations, wall_mask, image_shape)
    calibration_mode = "total_area" if total_area_sqft is not None else "label_sqft"
    log_event(
        "scale_calibration_start",
        image_shape={"height": image_shape[0], "width": image_shape[1]},
        label_count=len(labels),
        calibration_mode=calibration_mode,
        total_area_sqft=round(float(total_area_sqft), 4) if total_area_sqft is not None else None,
    )

    room_analysis = analyze_labeled_rooms(
        annotations,
        wall_mask,
        image_shape,
        labels=labels,
        closed_mask=closed_mask,
    )
    valid_rooms = [room for room in room_analysis["rooms"] if room["region"] is not None]
    if not valid_rooms:
        log_event("scale_calibration_failed", reason="no_valid_room_regions", calibration_mode=calibration_mode)
        return None

    if total_area_sqft is not None:
        total_area_sqft = float(total_area_sqft)
        if total_area_sqft <= 0:
            log_event("scale_calibration_failed", reason="non_positive_total_area", total_area_sqft=total_area_sqft)
            return None
        union_area_px = int(room_analysis["union_area_px"])
        if union_area_px < 100:
            log_event(
                "scale_calibration_failed",
                reason="total_area_region_too_small",
                total_area_sqft=total_area_sqft,
                union_area_px=union_area_px,
            )
            return None

        scale_ipp = math.sqrt(total_area_sqft * 144.0 / union_area_px)
        for room in valid_rooms:
            room["computed_sqft"] = (float(room["area_px"]) * (scale_ipp**2)) / 144.0

        raw_sum_sqft = sum(float(room["computed_sqft"]) for room in valid_rooms)
        union_sum_sqft = (union_area_px * (scale_ipp**2)) / 144.0
        total_delta_sqft = raw_sum_sqft - total_area_sqft
        total_delta_pct = (total_delta_sqft / total_area_sqft * 100.0) if total_area_sqft else 0.0

        log_event(
            "scale_calibration_total_area",
            total_area_sqft=round(total_area_sqft, 4),
            union_area_px=union_area_px,
            raw_labeled_area_px=int(room_analysis["raw_labeled_area_px"]),
            overlap_area_px=int(room_analysis["overlap_area_px"]),
            duplicated_region_count=int(room_analysis["duplicated_region_count"]),
            overlapping_label_count=int(room_analysis["overlapping_label_count"]),
            scale_ipp=round(scale_ipp, 6),
        )
        log_event(
            "room_area_audit_summary",
            calibration_mode="total_area",
            labeled_room_count=len(labels),
            valid_room_regions=len(valid_rooms),
            duplicated_region_count=int(room_analysis["duplicated_region_count"]),
            overlapping_label_count=int(room_analysis["overlapping_label_count"]),
            union_area_px=union_area_px,
            raw_labeled_area_px=int(room_analysis["raw_labeled_area_px"]),
            overlap_area_px=int(room_analysis["overlap_area_px"]),
            total_area_sqft=round(total_area_sqft, 4),
            union_sum_sqft=round(union_sum_sqft, 4),
            raw_sum_sqft=round(raw_sum_sqft, 4),
            total_delta_sqft=round(total_delta_sqft, 4),
            total_delta_pct=round(total_delta_pct, 4),
        )
        log_event(
            "scale_calibration_done",
            calibration_mode="total_area",
            sample_count=1,
            scales=[round(scale_ipp, 6)],
            final_scale_ipp=round(scale_ipp, 6),
        )
        return {
            "scale_ipp": scale_ipp,
            "calibration_mode": "total_area",
            "room_analysis": room_analysis,
            "total_area_sqft": total_area_sqft,
        }

    scales: list[float] = []
    for room in valid_rooms:
        label_sqft = room["label"].get("sqft")
        if label_sqft is None:
            continue

        sqft = float(label_sqft)
        if sqft <= 0:
            log_event(
                "scale_calibration_label_skipped",
                index=room["index"],
                reason="non_positive_sqft",
                room_name=room["room_name"],
                sqft=sqft,
            )
            continue

        scale = math.sqrt(sqft * 144.0 / float(room["area_px"]))
        room["source_sqft"] = sqft
        room["computed_scale_ipp"] = scale
        scales.append(scale)
        log_event(
            "scale_calibration_label",
            index=room["index"],
            room_name=room["room_name"],
            sqft=sqft,
            seed={"x": room["seed"][0], "y": room["seed"][1]},
            area_pixels=int(room["area_px"]),
            scale_ipp=round(scale, 6),
        )

    if not scales:
        log_event("scale_calibration_failed", reason="no_valid_scales", calibration_mode="label_sqft")
        return None

    scales.sort()
    mid = len(scales) // 2
    final_scale = scales[mid] if len(scales) % 2 else (scales[mid - 1] + scales[mid]) / 2
    for room in valid_rooms:
        room["computed_sqft"] = (float(room["area_px"]) * (final_scale**2)) / 144.0

    log_event(
        "room_area_audit_summary",
        calibration_mode="label_sqft",
        labeled_room_count=len(labels),
        valid_room_regions=len(valid_rooms),
        duplicated_region_count=int(room_analysis["duplicated_region_count"]),
        overlapping_label_count=int(room_analysis["overlapping_label_count"]),
        union_area_px=int(room_analysis["union_area_px"]),
        raw_labeled_area_px=int(room_analysis["raw_labeled_area_px"]),
        overlap_area_px=int(room_analysis["overlap_area_px"]),
    )
    log_event(
        "scale_calibration_done",
        calibration_mode="label_sqft",
        sample_count=len(scales),
        scales=[round(scale, 6) for scale in scales],
        final_scale_ipp=round(final_scale, 6),
    )
    return {
        "scale_ipp": final_scale,
        "calibration_mode": "label_sqft",
        "room_analysis": room_analysis,
        "total_area_sqft": None,
    }


def analyze_labeled_rooms(
    annotations: list[dict],
    wall_mask: np.ndarray,
    image_shape: tuple[int, int],
    *,
    labels: list[dict] | None = None,
    closed_mask: np.ndarray | None = None,
) -> dict[str, object]:
    """Resolve flood-filled room regions for every label and audit overlaps."""
    if labels is None:
        labels = [a for a in annotations if a.get("type") == "label"]
    if closed_mask is None:
        closed_mask = _build_closed_mask(annotations, wall_mask, image_shape)

    union_mask = np.zeros(image_shape, dtype=bool)
    rooms: list[dict[str, object]] = []
    duplicated_region_count = 0
    overlapping_label_count = 0

    for index, label in enumerate(labels):
        region = flood_fill_room_region(
                annotations,
                wall_mask,
                image_shape,
                int(float(label.get("x1", 0))),
                int(float(label.get("y1", 0))),
                closed_mask=closed_mask,
            )

        if not region:
            log_event(
                "room_region_skipped",
                index=index,
                room_name=label.get("roomName"),
                reason="room_region_not_found",
            )
            rooms.append(
                {
                    "index": index,
                    "label": label,
                    "room_name": label.get("roomName"),
                    "region": None,
                    "area_px": 0,
                    "bbox": None,
                    "seed": (int(float(label.get("x1", 0))), int(float(label.get("y1", 0)))),
                    "duplicate_of_index": None,
                    "overlap_area_px": 0,
                }
            )
            continue

        room_mask = region["mask"]
        bbox = tuple(int(v) for v in region["bbox"])
        area_px = int(region["area_px"])
        seed = tuple(int(v) for v in region["seed"])
        overlap_area_px = int(np.count_nonzero(union_mask & room_mask))
        if overlap_area_px > 0:
            overlapping_label_count += 1

        duplicate_of_index: int | None = None
        for previous in rooms:
            previous_region = previous.get("region")
            if previous_region is None:
                continue
            if int(previous["area_px"]) != area_px or tuple(previous["bbox"]) != bbox:
                continue
            if np.array_equal(previous_region["mask"], room_mask):
                duplicate_of_index = int(previous["index"])
                duplicated_region_count += 1
                break

        union_mask |= room_mask
        log_event(
            "room_region_detected",
            index=index,
            room_name=label.get("roomName"),
            seed={"x": seed[0], "y": seed[1]},
            bbox={"x1": bbox[0], "y1": bbox[1], "x2": bbox[2], "y2": bbox[3]},
            area_pixels=area_px,
            overlap_area_px=overlap_area_px,
            duplicate_of_index=duplicate_of_index,
        )
        rooms.append(
            {
                "index": index,
                "label": label,
                "room_name": label.get("roomName"),
                "region": region,
                "area_px": area_px,
                "bbox": bbox,
                "seed": seed,
                "duplicate_of_index": duplicate_of_index,
                "overlap_area_px": overlap_area_px,
            }
        )

    raw_labeled_area_px = int(sum(int(room["area_px"]) for room in rooms))
    union_area_px = int(np.count_nonzero(union_mask))
    overlap_area_px = raw_labeled_area_px - union_area_px
    return {
        "rooms": rooms,
        "rooms_by_label_id": {id(room["label"]): room for room in rooms},
        "union_area_px": union_area_px,
        "raw_labeled_area_px": raw_labeled_area_px,
        "overlap_area_px": overlap_area_px,
        "overlapping_label_count": overlapping_label_count,
        "duplicated_region_count": duplicated_region_count,
        "closed_mask": closed_mask,
    }


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
        if atype in ("door", "window", "separator"):
            x1, y1 = int(ann.get("x1", 0)), int(ann.get("y1", 0))
            x2, y2 = int(ann.get("x2", 0)), int(ann.get("y2", 0))
            # Separators thicker to guarantee sealing wall-to-wall gaps
            thickness = 14 if atype == "separator" else 6
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
    success, buf = cv2.imencode(".png", cv2.cvtColor(overlay, cv2.COLOR_RGBA2BGRA))
    if not success:
        return ""
    return base64.b64encode(buf.tobytes()).decode("ascii")


def inches_to_feet_inches(inches: float) -> str:
    """68.0 → 5'-8\""""
    feet = int(inches) // 12
    remaining = round(inches - feet * 12)
    if remaining == 12:
        feet += 1
        remaining = 0
    return f"{feet}'-{remaining}\""
