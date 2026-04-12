"""
junctions.py — Shared wall junction logic for 2D editor and DXF writer.

Both the canvas overlay annotations (pixel space) and the DXF polyline/hatch
writer (inch space) need the same logic to resolve how perpendicular walls
connect at L-corners, T-junctions, and X-crosses.

This module provides a single source of truth for that logic.
"""
from __future__ import annotations

from typing import Any


def resolve_wall_junctions(
    walls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Adjust wall spans so perpendicular walls connect cleanly.

    Each wall dict must have:
        orientation: "horizontal" | "vertical"
        mid:         centerline on the perpendicular axis (y for H, x for V)
        span_lo:     start on parallel axis
        span_hi:     end on parallel axis
        half_lw:     half of visual line width (pixels or inches)

    Returns a new list of wall dicts with adjusted span_lo / span_hi.
    Original dicts are NOT mutated.

    Junction rules:
    - **L-corner** (both walls end at same point):
        Horizontal extends to vertical's outer edge (covers corner square).
        Vertical trims to horizontal's inner edge.
    - **T-junction** (one wall ends, other continues through):
        The ending wall extends THROUGH the continuing wall to its far edge,
        so it visually covers the junction point.
    - **X-cross** (both walls pass through): no adjustment.
    """
    if len(walls) < 2:
        return [dict(w) for w in walls]

    h_walls = [(i, w) for i, w in enumerate(walls) if w["orientation"] == "horizontal"]
    v_walls = [(i, w) for i, w in enumerate(walls) if w["orientation"] == "vertical"]

    # Tolerance: 2x the largest half_lw, minimum 6
    max_hlw = max((w["half_lw"] for w in walls), default=4)
    NEAR = max(6, max_hlw * 3)

    result = [dict(w) for w in walls]

    def _endpoint_of(wall: dict, coord: float, axis: str) -> bool:
        """Check if coord is near either end of the wall's span."""
        return (abs(wall["span_lo"] - coord) <= NEAR
                or abs(wall["span_hi"] - coord) <= NEAR)

    # --- Vertical walls meeting horizontal walls ---
    for vi, vw in v_walls:
        for end in ("lo", "hi"):
            v_span_key = f"span_{end}"
            v_span_val = vw[v_span_key]
            for _hi, hw in h_walls:
                hw_hlw = hw["half_lw"]
                # Is this V endpoint near the H wall's centerline?
                if abs(v_span_val - hw["mid"]) > NEAR:
                    continue
                # Is the V wall's mid (x) within the H wall's span?
                if vw["mid"] < hw["span_lo"] - NEAR or vw["mid"] > hw["span_hi"] + NEAR:
                    continue

                # Determine direction: which side is the body of V?
                body_toward_lo = (end == "hi")  # if adjusting hi, body is toward lo
                is_l_corner = _endpoint_of(hw, vw["mid"], "x")

                if is_l_corner:
                    # L-corner: V trims to H's inner edge
                    if body_toward_lo:
                        result[vi]["span_hi"] = hw["mid"] - hw_hlw
                    else:
                        result[vi]["span_lo"] = hw["mid"] + hw_hlw
                else:
                    # T-junction: V extends THROUGH H to far edge
                    if body_toward_lo:
                        result[vi]["span_hi"] = hw["mid"] + hw_hlw
                    else:
                        result[vi]["span_lo"] = hw["mid"] - hw_hlw
                break

    # --- Horizontal walls meeting vertical walls ---
    for hi, hw in h_walls:
        for end in ("lo", "hi"):
            h_span_key = f"span_{end}"
            h_span_val = hw[h_span_key]
            for _vi, vw in v_walls:
                vw_hlw = vw["half_lw"]
                if abs(h_span_val - vw["mid"]) > NEAR:
                    continue
                if hw["mid"] < vw["span_lo"] - NEAR or hw["mid"] > vw["span_hi"] + NEAR:
                    continue

                body_toward_lo = (end == "hi")
                is_l_corner = _endpoint_of(vw, hw["mid"], "y")

                if is_l_corner:
                    # L-corner: H extends to V's outer edge
                    if body_toward_lo:
                        result[hi]["span_hi"] = vw["mid"] + vw_hlw
                    else:
                        result[hi]["span_lo"] = vw["mid"] - vw_hlw
                else:
                    # T-junction: H extends THROUGH V to far edge
                    if body_toward_lo:
                        result[hi]["span_hi"] = vw["mid"] + vw_hlw
                    else:
                        result[hi]["span_lo"] = vw["mid"] - vw_hlw
                break

    return result
