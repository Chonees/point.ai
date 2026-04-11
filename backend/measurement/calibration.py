"""
scale_calibrator — Calculate inches-per-pixel scale from labeled floor-plan regions.

Supported calibration modes:
1. total_area_sqft + room labels (preferred)
2. legacy per-room sqft labels (fallback)
"""
from __future__ import annotations

import math
import sys

import numpy as np

from .flood_fill import _build_closed_mask
from .room_analysis import analyze_labeled_rooms


def inches_to_feet_inches(inches: float) -> str:
    """68.0 → 5'-8\""""
    feet = int(inches) // 12
    remaining = round(inches - feet * 12)
    if remaining == 12:
        feet += 1
        remaining = 0
    return f"{feet}'-{remaining}\""


def _log_event(event: str, **kwargs) -> None:
    sc = sys.modules.get("backend.scale_calibrator")
    if sc is not None and hasattr(sc, "log_event"):
        sc.log_event(event, **kwargs)
    else:
        from ..observability import log_event
        log_event(event, **kwargs)


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
        _log_event("scale_calibration_skipped", reason="no_labels")
        return None

    closed_mask = _build_closed_mask(annotations, wall_mask, image_shape)
    calibration_mode = "total_area" if total_area_sqft is not None else "label_sqft"
    _log_event(
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
        _log_event("scale_calibration_failed", reason="no_valid_room_regions", calibration_mode=calibration_mode)
        return None

    if total_area_sqft is not None:
        total_area_sqft = float(total_area_sqft)
        if total_area_sqft <= 0:
            _log_event("scale_calibration_failed", reason="non_positive_total_area", total_area_sqft=total_area_sqft)
            return None
        union_area_px = int(room_analysis["union_area_px"])
        if union_area_px < 100:
            _log_event(
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

        _log_event(
            "scale_calibration_total_area",
            total_area_sqft=round(total_area_sqft, 4),
            union_area_px=union_area_px,
            raw_labeled_area_px=int(room_analysis["raw_labeled_area_px"]),
            overlap_area_px=int(room_analysis["overlap_area_px"]),
            duplicated_region_count=int(room_analysis["duplicated_region_count"]),
            overlapping_label_count=int(room_analysis["overlapping_label_count"]),
            scale_ipp=round(scale_ipp, 6),
        )
        _log_event(
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
        _log_event(
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
            _log_event(
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
        _log_event(
            "scale_calibration_label",
            index=room["index"],
            room_name=room["room_name"],
            sqft=sqft,
            seed={"x": room["seed"][0], "y": room["seed"][1]},
            area_pixels=int(room["area_px"]),
            scale_ipp=round(scale, 6),
        )

    if not scales:
        _log_event("scale_calibration_failed", reason="no_valid_scales", calibration_mode="label_sqft")
        return None

    scales.sort()
    mid = len(scales) // 2
    final_scale = scales[mid] if len(scales) % 2 else (scales[mid - 1] + scales[mid]) / 2
    for room in valid_rooms:
        room["computed_sqft"] = (float(room["area_px"]) * (final_scale**2)) / 144.0

    _log_event(
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
    _log_event(
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
