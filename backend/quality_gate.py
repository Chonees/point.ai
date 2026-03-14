"""
quality_gate.py
Minimal structural quality gate for the v2 pipeline.
"""
from __future__ import annotations

from typing import Any

EPSILON = 1e-6
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

    if not walls:
        gate_reasons.append("no_walls_detected")

    if not openings:
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

    for reason in gate_reasons:
        message = _REASON_MESSAGES[reason]
        if message not in flags:
            flags.append(message)

    return metrics, flags


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
            if abs(y - min_y) <= EPSILON:
                coverage["bottom"] = max(coverage["bottom"], span)
            if abs(y - max_y) <= EPSILON:
                coverage["top"] = max(coverage["top"], span)
        elif orientation == "vertical":
            span = abs(float(end["y"]) - float(start["y"])) / bbox_height
            x = float(start["x"])
            if abs(x - min_x) <= EPSILON:
                coverage["left"] = max(coverage["left"], span)
            if abs(x - max_x) <= EPSILON:
                coverage["right"] = max(coverage["right"], span)

    covered_count = sum(1 for value in coverage.values() if value >= MIN_BBOX_SIDE_COVERAGE)
    min_coverage = min(coverage.values())
    avg_coverage = sum(coverage.values()) / len(coverage)

    return {
        "bbox_sides_covered": covered_count,
        "bbox_min_side_coverage": round(min_coverage, 4),
        "bbox_avg_side_coverage": round(avg_coverage, 4),
    }
