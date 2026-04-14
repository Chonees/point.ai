"""
Pure computation of dimension annotations from wall/opening data.

Does NOT touch any DXF objects. Returns plain dicts that travel
in auto_annotations and get rendered by the frontend editor AND
exported to DXF as DIMLINEAR entities.

Companion to exterior.py / generator.py which historically drew
straight to msp. This module is the "compute" half of a split that
turns dimensions into first-class, user-editable annotations.
"""
from __future__ import annotations

import uuid
from typing import Any

from .exterior import (
    _assign_windows_to_segments,
    _building_centroid_from_segments,
    _classify_annotations,
    _find_exterior_walls,
    _opening_centerline,
    _wall_extent,
    _wall_orientation,
)
from .formatting import _fmt_inches


# Offsets (pixels) between the wall and the dimension line.
# Window-chain dimensions sit closer to the wall; full exterior-wall
# dimensions sit further out to avoid overlapping the chain.
_WINDOW_OFFSET_PX = 40.0
_WALL_OFFSET_PX = 80.0


def compute_dimension_annotations(
    annotations: list[dict],
    scale_ipp: float,
    image_shape: tuple[int, int],
) -> list[dict[str, Any]]:
    """Compute dimension annotations from walls + windows + scale.

    Pure data function — does not draw to DXF. Returns a list of dicts
    with ``type='dimension'`` ready to be appended to ``auto_annotations``
    and consumed by both the frontend editor and the DXF writer.

    Each annotation shape::

        {
            id: uuid,
            type: "dimension",
            subtype: "exterior" | "window_chain",
            x1, y1, x2, y2: endpoints of the measured span (image pixels),
            offset_px: distance from the wall to the dim line (positive),
            orientation: "H" | "V",
            outward: 1 | -1,
            value_inches: float,
            value_text: "5'-8\"",
            wall_ids: [id, ...],
            window_ids: [id, ...]  # only for subtype="window_chain"
        }
    """
    if scale_ipp <= 0 or not annotations:
        return []

    classified = _classify_annotations(annotations)
    walls = classified["wall"]
    windows = classified["window"]

    if not walls:
        return []

    exterior_segments = _annotation_exterior_segments_with_ids(walls)
    if not exterior_segments:
        return []

    centroid_px = _building_centroid_from_segments(exterior_segments)
    windows_by_segment = _assign_windows_to_segments(windows, exterior_segments)

    dimensions: list[dict[str, Any]] = []

    for index, segment in enumerate(exterior_segments):
        orientation = str(segment["orientation"])
        wall_start = float(segment["start"])
        wall_end = float(segment["end"])
        wall_coord = float(segment["coord"])
        wall_ids: list[str] = [wid for wid in segment.get("wall_ids", []) if wid]

        if orientation == "H":
            outward = -1 if wall_coord > centroid_px[1] else 1
        else:
            outward = 1 if wall_coord > centroid_px[0] else -1

        wall_length_px = abs(wall_end - wall_start)
        if wall_length_px < 3:
            continue
        wall_length_in = wall_length_px * scale_ipp

        if orientation == "H":
            ex1, ey1, ex2, ey2 = wall_start, wall_coord, wall_end, wall_coord
        else:
            ex1, ey1, ex2, ey2 = wall_coord, wall_start, wall_coord, wall_end

        dimensions.append({
            "id": str(uuid.uuid4()),
            "type": "dimension",
            "subtype": "exterior",
            "x1": round(ex1, 2),
            "y1": round(ey1, 2),
            "x2": round(ex2, 2),
            "y2": round(ey2, 2),
            "offset_px": _WALL_OFFSET_PX,
            "orientation": orientation,
            "outward": outward,
            "value_inches": round(wall_length_in, 4),
            "value_text": _fmt_inches(wall_length_in),
            "wall_ids": wall_ids,
        })

        windows_on_wall = windows_by_segment.get(index, [])
        if not windows_on_wall:
            continue

        window_centers: list[tuple[float, str | None]] = sorted(
            ((_opening_centerline(win, orientation), win.get("id"))
             for win in windows_on_wall),
            key=lambda t: t[0],
        )
        chain_points: list[tuple[float, str | None]] = (
            [(wall_start, None)] + window_centers + [(wall_end, None)]
        )

        for i in range(len(chain_points) - 1):
            p1, id1 = chain_points[i]
            p2, id2 = chain_points[i + 1]
            segment_px = abs(p2 - p1)
            if segment_px < 2:
                continue
            segment_in = segment_px * scale_ipp

            if orientation == "H":
                sx1, sy1, sx2, sy2 = p1, wall_coord, p2, wall_coord
            else:
                sx1, sy1, sx2, sy2 = wall_coord, p1, wall_coord, p2

            window_ids = [wid for wid in (id1, id2) if wid]

            dimensions.append({
                "id": str(uuid.uuid4()),
                "type": "dimension",
                "subtype": "window_chain",
                "x1": round(sx1, 2),
                "y1": round(sy1, 2),
                "x2": round(sx2, 2),
                "y2": round(sy2, 2),
                "offset_px": _WINDOW_OFFSET_PX,
                "orientation": orientation,
                "outward": outward,
                "value_inches": round(segment_in, 4),
                "value_text": _fmt_inches(segment_in),
                "wall_ids": wall_ids,
                "window_ids": window_ids,
            })

    return dimensions


def _annotation_exterior_segments_with_ids(
    walls: list[dict],
) -> list[dict[str, Any]]:
    """Exterior segments carrying the wall ids that compose each segment.

    Extends each segment by the wall's visual half-width so the dimension
    measures outer-face-to-outer-face instead of centerline-to-centerline.
    This matches how architects dimension exterior walls (the measurement
    runs to the outer face of the building, not the center of the stud).
    """
    # Visual half-line-width per wall thickness (mirrors frontend WALL_LINE_WIDTH)
    _HALF_LW: dict[int, float] = {4: 2.0, 6: 4.0}

    segments: list[dict[str, Any]] = []
    for wall in _find_exterior_walls(walls):
        orientation = _wall_orientation(wall)
        start, end, coord = _wall_extent(wall, orientation)
        if abs(end - start) < 3:
            continue
        # Extend to outer face of the wall
        half_lw = _HALF_LW.get(int(wall.get("thickness") or 4), 2.0)
        start -= half_lw
        end += half_lw
        wid = wall.get("id")
        segments.append(
            {
                "orientation": orientation,
                "start": float(start),
                "end": float(end),
                "coord": float(coord),
                "source": "annotation_extremes",
                "wall_ids": [wid] if wid else [],
            }
        )
    return _merge_exterior_segments_preserving_ids(segments, coord_tolerance=8.0, gap_tolerance=8.0)


def _merge_exterior_segments_preserving_ids(
    segments: list[dict[str, Any]],
    *,
    coord_tolerance: float = 3.0,
    gap_tolerance: float = 5.0,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for orientation in ("H", "V"):
        oriented = [s for s in segments if s["orientation"] == orientation]
        oriented.sort(key=lambda s: (float(s["coord"]), float(s["start"])))

        current: dict[str, Any] | None = None
        for segment in oriented:
            if current is None:
                current = {**segment, "wall_ids": list(segment.get("wall_ids", []))}
                continue

            same_line = abs(float(segment["coord"]) - float(current["coord"])) <= coord_tolerance
            touches = float(segment["start"]) <= float(current["end"]) + gap_tolerance
            same_source = segment.get("source") == current.get("source")
            if same_line and touches and same_source:
                current["start"] = min(float(current["start"]), float(segment["start"]))
                current["end"] = max(float(current["end"]), float(segment["end"]))
                current["coord"] = (float(current["coord"]) + float(segment["coord"])) / 2
                current["wall_ids"].extend(segment.get("wall_ids", []))
                continue

            merged.append(current)
            current = {**segment, "wall_ids": list(segment.get("wall_ids", []))}

        if current is not None:
            merged.append(current)

    return merged
