"""
quality_gate.py
Minimal structural quality gate for the v2 pipeline.
"""
from __future__ import annotations

from typing import Any

EPSILON = 1e-6
# Tolerance for bbox-side membership: walls end up on snapped cluster coords
# which may differ from the true min/max by a small float residual.
_BBOX_SNAP_TOL = 4.0  # matches default SNAP_TOLERANCE in structure_postprocess
MIN_EXTERIOR_WALLS = 2
MIN_BBOX_SIDE_COVERAGE = 0.6
MIN_BBOX_SIDES_COVERED = 3
MIN_BBOX_AVG_SIDE_COVERAGE = 0.7

_REASON_MESSAGES = {
    "no_walls_detected": "Quality gate: no walls detected.",
    "no_openings_detected": "Quality gate: no openings detected.",
    "anomalous_exterior_wall_count": "Quality gate: exterior wall count is too low.",
    "footprint_not_reasonably_closed": "Quality gate: exterior shell does not close reasonably.",
}


def apply_quality_gate(
    structure: dict[str, Any],
    quality_metrics: dict[str, Any],
    review_flags: list[str],
) -> tuple[dict[str, Any], list[str]]:
    """Return updated quality metrics and review flags after structural checks."""
    metrics = dict(quality_metrics)
    flags = list(review_flags)

    gate_reasons: list[str] = []
    walls = structure.get("walls", [])
    openings = structure.get("openings", [])
    opening_detection_disabled = _opening_detection_disabled(structure)

    if not walls:
        gate_reasons.append("no_walls_detected")

    if not openings and not opening_detection_disabled:
        gate_reasons.append("no_openings_detected")

    exterior_wall_count = int(metrics.get("exterior_wall_count", 0))
    if exterior_wall_count < MIN_EXTERIOR_WALLS:
        gate_reasons.append("anomalous_exterior_wall_count")

    shell_metrics = _compute_bbox_shell_metrics(walls)
    metrics.update(shell_metrics)
    if shell_metrics["bbox_sides_covered"] < MIN_BBOX_SIDES_COVERED or (
        shell_metrics["bbox_avg_side_coverage"] < MIN_BBOX_AVG_SIDE_COVERAGE
    ):
        gate_reasons.append("footprint_not_reasonably_closed")

    metrics["quality_gate_passed"] = len(gate_reasons) == 0
    metrics["quality_gate_reasons"] = gate_reasons
    metrics["quality_gate_reason_count"] = len(gate_reasons)
    metrics["opening_detection_disabled"] = opening_detection_disabled

    for reason in gate_reasons:
        message = _REASON_MESSAGES[reason]
        if message not in flags:
            flags.append(message)

    return metrics, flags


def _opening_detection_disabled(structure: dict[str, Any]) -> bool:
    structure_meta = structure.get("structure_meta") or {}
    inference_debug = structure.get("inference_debug") or {}
    return (
        structure_meta.get("opening_detection_mode") == "disabled"
        or bool(inference_debug.get("opening_detection_disabled"))
    )


def _compute_bbox_shell_metrics(walls: list[dict[str, Any]]) -> dict[str, float | int]:
    if not walls:
        return {
            "bbox_sides_covered": 0,
            "bbox_min_side_coverage": 0.0,
            "bbox_avg_side_coverage": 0.0,
        }

    points = [point for wall in walls for point in wall.get("polyline", [])]
    if not points:
        return {
            "bbox_sides_covered": 0,
            "bbox_min_side_coverage": 0.0,
            "bbox_avg_side_coverage": 0.0,
        }

    min_x = min(float(point["x"]) for point in points)
    max_x = max(float(point["x"]) for point in points)
    min_y = min(float(point["y"]) for point in points)
    max_y = max(float(point["y"]) for point in points)

    bbox_width = max(max_x - min_x, 1.0)
    bbox_height = max(max_y - min_y, 1.0)

    coverage = {"top": 0.0, "bottom": 0.0, "left": 0.0, "right": 0.0}
    for wall in walls:
        polyline = wall.get("polyline") or []
        if len(polyline) != 2:
            continue
        start, end = polyline
        orientation = wall.get("orientation")
        if orientation == "horizontal":
            span = abs(float(end["x"]) - float(start["x"])) / bbox_width
            y = float(start["y"])
            if abs(y - min_y) <= _BBOX_SNAP_TOL:
                coverage["bottom"] = max(coverage["bottom"], span)
            if abs(y - max_y) <= _BBOX_SNAP_TOL:
                coverage["top"] = max(coverage["top"], span)
        elif orientation == "vertical":
            span = abs(float(end["y"]) - float(start["y"])) / bbox_height
            x = float(start["x"])
            if abs(x - min_x) <= _BBOX_SNAP_TOL:
                coverage["left"] = max(coverage["left"], span)
            if abs(x - max_x) <= _BBOX_SNAP_TOL:
                coverage["right"] = max(coverage["right"], span)

    covered_count = sum(1 for value in coverage.values() if value >= MIN_BBOX_SIDE_COVERAGE)
    min_coverage = min(coverage.values())
    avg_coverage = sum(coverage.values()) / len(coverage)

    return {
        "bbox_sides_covered": covered_count,
        "bbox_min_side_coverage": round(min_coverage, 4),
        "bbox_avg_side_coverage": round(avg_coverage, 4),
    }
