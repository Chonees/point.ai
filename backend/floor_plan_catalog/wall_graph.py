from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from backend.floor_plan_catalog.contracts import (
    CatalogCadTrace,
    CatalogPoint,
    CatalogRoomTopology,
    CatalogWallBoundary,
    FloorPlanTopologyV1,
    FloorPlanWallGraphV1,
    WallGraphReadiness,
)


@dataclass(frozen=True)
class _Segment:
    room_id: str
    edge_index: int
    start: CatalogPoint
    end: CatalogPoint


@dataclass(frozen=True)
class _RawTraceSegment:
    trace_id: str
    start: CatalogPoint
    end: CatalogPoint
    orientation: str


@dataclass(frozen=True)
class _Overlap:
    segment_a: _Segment
    segment_b: _Segment
    start: CatalogPoint
    end: CatalogPoint
    interval_a: tuple[float, float]
    interval_b: tuple[float, float]


@dataclass(frozen=True)
class _TraceSupport:
    status: str
    trace_ids: list[str]
    gap: float | None
    start: CatalogPoint
    end: CatalogPoint


def derive_floor_plan_wall_graph(
    topology: FloorPlanTopologyV1,
    cad_traces: list[CatalogCadTrace] | None = None,
    tolerance: float = 3.0,
    bbox_inference_tolerance: float = 10.0,
    minimum_overlap: float = 12.0,
    minimum_shared_wall_length: float = 12.0,
    exact_support_tolerance: float = 0.25,
    snap_support_tolerance: float = 11.0,
    minimum_support_ratio: float = 0.75,
) -> FloorPlanWallGraphV1:
    room_segments = {room.room_id: _room_segments(room.room_id, room.polygon) for room in topology.rooms}
    shared_walls: list[CatalogWallBoundary] = []
    used_intervals: dict[tuple[str, int], list[tuple[float, float]]] = {}
    seen_shared_keys: set[tuple[tuple[str, ...], tuple[float, float, float, float]]] = set()
    exact_pairs: set[tuple[str, str]] = set()

    rooms = topology.rooms
    for index, room in enumerate(rooms):
        for other_room in rooms[index + 1 :]:
            pair_ids = tuple(sorted((room.room_id, other_room.room_id)))
            for segment_a in room_segments[room.room_id]:
                for segment_b in room_segments.get(other_room.room_id, []):
                    overlap = _segment_overlap(segment_a, segment_b, tolerance)
                    if overlap is None:
                        continue
                    overlap_length = _distance(overlap.start, overlap.end)
                    if overlap_length < minimum_shared_wall_length:
                        continue
                    canonical = _canonical_segment(overlap.start, overlap.end)
                    dedupe_key = (pair_ids, canonical)
                    if dedupe_key in seen_shared_keys:
                        continue
                    exact_pairs.add(pair_ids)
                    seen_shared_keys.add(dedupe_key)
                    used_intervals.setdefault((segment_a.room_id, segment_a.edge_index), []).append(overlap.interval_a)
                    used_intervals.setdefault((segment_b.room_id, segment_b.edge_index), []).append(overlap.interval_b)
                    shared_walls.append(
                        CatalogWallBoundary(
                            wall_id=_build_wall_id("shared", pair_ids, overlap.start, overlap.end),
                            start=overlap.start,
                            end=overlap.end,
                            orientation=_orientation(overlap.start, overlap.end, tolerance),
                            length=overlap_length,
                            is_exterior=False,
                            room_ids=list(pair_ids),
                            boundary_kind="shared",
                            owner_room_ids=list(pair_ids),
                            provenance="exact_room_overlap",
                            confidence="geometric_exact",
                        )
                    )

    for index, room in enumerate(rooms):
        for other_room in rooms[index + 1 :]:
            pair_ids = tuple(sorted((room.room_id, other_room.room_id)))
            if pair_ids in exact_pairs:
                continue
            inferred_wall = _bbox_inferred_shared_wall(
                room,
                other_room,
                tolerance=bbox_inference_tolerance,
                minimum_overlap=minimum_overlap,
            )
            if inferred_wall is None:
                continue
            canonical = _canonical_segment(inferred_wall.start, inferred_wall.end)
            dedupe_key = (pair_ids, canonical)
            if dedupe_key in seen_shared_keys:
                continue
            seen_shared_keys.add(dedupe_key)
            shared_walls.append(inferred_wall)

    exterior_walls: list[CatalogWallBoundary] = []
    for room_id, segments in room_segments.items():
        for segment in segments:
            intervals = used_intervals.get((room_id, segment.edge_index), [])
            for interval in _subtract_intervals(intervals):
                start = _point_at(segment.start, segment.end, interval[0])
                end = _point_at(segment.start, segment.end, interval[1])
                if _distance(start, end) <= tolerance:
                    continue
                exterior_walls.append(
                    CatalogWallBoundary(
                        wall_id=_build_wall_id("exterior", (room_id,), start, end),
                        start=start,
                        end=end,
                        orientation=_orientation(start, end, tolerance),
                        length=_distance(start, end),
                        is_exterior=True,
                        room_ids=[room_id],
                        boundary_kind="exterior",
                        owner_room_ids=[room_id],
                        provenance="room_exterior_boundary",
                        confidence="geometric_exact",
                    )
                )

    walls = sorted(shared_walls + exterior_walls, key=lambda wall: wall.wall_id)
    has_trace_context = bool(cad_traces)
    wall_traces = [trace for trace in (cad_traces or []) if trace.trace_kind == "wall"]
    if wall_traces:
        raw_segments = _trace_segments(wall_traces, tolerance)
        walls = [
            _apply_trace_support(
                wall,
                raw_segments,
                tolerance=exact_support_tolerance,
                snap_tolerance=snap_support_tolerance,
                minimum_support_ratio=minimum_support_ratio,
            )
            for wall in walls
        ]
    elif has_trace_context:
        walls = [_mark_trace_support_unsupported(wall) for wall in walls]
    walls = _prune_low_fidelity_shared_walls(
        walls,
        topology,
        minimum_shared_wall_length=minimum_shared_wall_length,
        edge_axis_tolerance=max(bbox_inference_tolerance * 2, 18.0),
        minimum_edge_overlap=max(minimum_overlap, 18.0),
    )

    wall_graph_issues = sorted({issue for wall in walls for issue in wall.issues})
    if has_trace_context and any((not wall.is_exterior) and wall.trace_support_status == "unsupported" for wall in walls):
        wall_graph_issues.append("unsupported_trace_support")
    if not walls:
        wall_graph_issues.append("missing_walls")
    if not any(not wall.is_exterior for wall in walls):
        wall_graph_issues.append("missing_shared_walls")
    if not any(wall.is_exterior for wall in walls):
        wall_graph_issues.append("missing_exterior_walls")
    wall_graph_issues = sorted(set(wall_graph_issues))
    readiness = WallGraphReadiness(
        status="ready_for_wall_graph_review" if not wall_graph_issues else "needs_wall_graph_review",
        issues=wall_graph_issues,
    )

    return FloorPlanWallGraphV1(
        floor_plan_id=topology.floor_plan_id,
        name=topology.name,
        canonical_unit=topology.canonical_unit,
        footprint_bbox=topology.footprint_bbox,
        walls=walls,
        wall_graph_readiness=readiness,
        wall_graph_issues=wall_graph_issues,
    )


def _room_segments(room_id: str, polygon: list[CatalogPoint]) -> list[_Segment]:
    segments: list[_Segment] = []
    for index in range(len(polygon)):
        start = polygon[index]
        end = polygon[(index + 1) % len(polygon)]
        if _distance(start, end) == 0:
            continue
        segments.append(_Segment(room_id=room_id, edge_index=index, start=start, end=end))
    return segments


def _trace_segments(wall_traces: list[CatalogCadTrace], tolerance: float) -> list[_RawTraceSegment]:
    segments: list[_RawTraceSegment] = []
    for trace in wall_traces:
        if trace.points and len(trace.points) >= 2:
            for index in range(len(trace.points) - 1):
                start = trace.points[index]
                end = trace.points[index + 1]
                if _distance(start, end) <= tolerance:
                    continue
                segments.append(
                    _RawTraceSegment(
                        trace_id=trace.trace_id,
                        start=start,
                        end=end,
                        orientation=_orientation(start, end, tolerance),
                    )
                )
            continue
        if trace.start and trace.end and _distance(trace.start, trace.end) > tolerance:
            segments.append(
                _RawTraceSegment(
                    trace_id=trace.trace_id,
                    start=trace.start,
                    end=trace.end,
                    orientation=_orientation(trace.start, trace.end, tolerance),
                )
            )
    return segments


def _apply_trace_support(
    wall: CatalogWallBoundary,
    raw_segments: list[_RawTraceSegment],
    *,
    tolerance: float,
    snap_tolerance: float,
    minimum_support_ratio: float,
) -> CatalogWallBoundary:
    exact = _find_exact_trace_support(wall, raw_segments, tolerance=tolerance, minimum_support_ratio=minimum_support_ratio)
    if exact is not None:
        return wall.model_copy(
            update={
                "confidence": "exact",
                "trace_support_status": exact.status,
                "trace_support_ids": exact.trace_ids,
                "trace_support_gap": exact.gap,
                "start": exact.start,
                "end": exact.end,
                "length": _distance(exact.start, exact.end),
                "issues": [issue for issue in wall.issues if issue != "inferred_from_bbox"],
            }
        )

    snapped = _find_snap_trace_support(
        wall,
        raw_segments,
        snap_tolerance=snap_tolerance,
        minimum_support_ratio=minimum_support_ratio,
    )
    if snapped is not None:
        return wall.model_copy(
            update={
                "confidence": "trace_supported",
                "trace_support_status": snapped.status,
                "trace_support_ids": snapped.trace_ids,
                "trace_support_gap": snapped.gap,
                "start": snapped.start,
                "end": snapped.end,
                "length": _distance(snapped.start, snapped.end),
                "issues": [issue for issue in wall.issues if issue != "inferred_from_bbox"],
            }
        )

    return wall.model_copy(
        update={
            "confidence": "unsupported",
            "trace_support_status": "unsupported",
            "trace_support_ids": [],
            "trace_support_gap": None,
        }
    )


def _mark_trace_support_unsupported(wall: CatalogWallBoundary) -> CatalogWallBoundary:
    return wall.model_copy(
        update={
            "confidence": "unsupported",
            "trace_support_status": "unsupported",
            "trace_support_ids": [],
            "trace_support_gap": None,
        }
    )


def _find_exact_trace_support(
    wall: CatalogWallBoundary,
    raw_segments: list[_RawTraceSegment],
    *,
    tolerance: float,
    minimum_support_ratio: float,
) -> _TraceSupport | None:
    best = _best_trace_group_support(
        wall,
        raw_segments,
        axis_tolerance=tolerance,
        minimum_support_ratio=minimum_support_ratio,
    )
    if best is None:
        return None
    return _TraceSupport(
        status="exact_trace_supported",
        trace_ids=best["trace_ids"],
        gap=0.0,
        start=best["start"],
        end=best["end"],
    )


def _find_snap_trace_support(
    wall: CatalogWallBoundary,
    raw_segments: list[_RawTraceSegment],
    *,
    snap_tolerance: float,
    minimum_support_ratio: float,
) -> _TraceSupport | None:
    if wall.orientation not in {"horizontal", "vertical"}:
        return None

    best = _best_trace_group_support(
        wall,
        raw_segments,
        axis_tolerance=snap_tolerance,
        minimum_support_ratio=minimum_support_ratio,
    )
    if best is None:
        return None

    gap = round(best["gap"], 3)
    return _TraceSupport(
        status="snapped_to_trace",
        trace_ids=best["trace_ids"],
        gap=gap,
        start=best["start"],
        end=best["end"],
    )


def _best_trace_group_support(
    wall: CatalogWallBoundary,
    raw_segments: list[_RawTraceSegment],
    *,
    axis_tolerance: float,
    minimum_support_ratio: float,
) -> dict[str, object] | None:
    candidates: list[tuple[float, _RawTraceSegment]] = []
    for segment in raw_segments:
        if segment.orientation != wall.orientation:
            continue
        gap, overlap = _axis_gap_and_overlap(wall.start, wall.end, segment.start, segment.end, wall.orientation)
        if gap is None or overlap is None or overlap <= 0 or wall.length == 0:
            continue
        if gap > axis_tolerance:
            continue
        candidates.append((gap, segment))

    if not candidates:
        return None

    wall_axis = _segment_axis(wall.start, wall.end, wall.orientation)
    best: dict[str, object] | None = None
    for cluster in _cluster_trace_segments(candidates, wall.orientation, axis_tolerance):
        coverage = _trace_cluster_coverage(wall, cluster)
        if coverage["covered_length"] <= 0:
            continue
        ratio = coverage["covered_length"] / wall.length
        if ratio < minimum_support_ratio:
            continue
        score = (coverage["gap"], -coverage["covered_length"], -len(coverage["trace_ids"]))
        if best is None or score < best["score"]:
            axis_value = coverage["axis"]
            start, end = _points_from_axis_and_interval(wall.orientation, axis_value, coverage["interval"])
            best = {
                "score": score,
                "gap": coverage["gap"],
                "trace_ids": coverage["trace_ids"],
                "start": start,
                "end": end,
                "axis": wall_axis,
            }
    return best


def _cluster_trace_segments(
    candidates: list[tuple[float, _RawTraceSegment]],
    orientation: str,
    axis_tolerance: float,
) -> list[list[_RawTraceSegment]]:
    ordered = sorted((segment for _, segment in candidates), key=lambda segment: _segment_axis(segment.start, segment.end, orientation))
    clusters: list[list[_RawTraceSegment]] = []
    for segment in ordered:
        axis = _segment_axis(segment.start, segment.end, orientation)
        if not clusters:
            clusters.append([segment])
            continue
        last_cluster = clusters[-1]
        last_axis = sum(_segment_axis(item.start, item.end, orientation) for item in last_cluster) / len(last_cluster)
        if abs(axis - last_axis) <= axis_tolerance:
            last_cluster.append(segment)
        else:
            clusters.append([segment])
    return clusters


def _trace_cluster_coverage(wall: CatalogWallBoundary, cluster: list[_RawTraceSegment]) -> dict[str, object]:
    wall_interval = _major_interval(wall.start, wall.end, wall.orientation)
    intervals: list[tuple[float, float]] = []
    trace_ids: list[str] = []
    axes: list[float] = []
    min_gap = math.inf

    for segment in cluster:
        gap, overlap = _axis_gap_and_overlap(wall.start, wall.end, segment.start, segment.end, wall.orientation)
        if gap is None or overlap is None or overlap <= 0:
            continue
        min_gap = min(min_gap, gap)
        axes.append(_segment_axis(segment.start, segment.end, wall.orientation))
        segment_interval = _major_interval(segment.start, segment.end, wall.orientation)
        start = max(wall_interval[0], segment_interval[0])
        end = min(wall_interval[1], segment_interval[1])
        if end <= start:
            continue
        intervals.append((start, end))
        trace_ids.append(segment.trace_id)

    merged = _merge_scalar_intervals(intervals)
    covered_length = sum(end - start for start, end in merged)
    interval = (merged[0][0], merged[-1][1]) if merged else wall_interval
    axis = sum(axes) / len(axes) if axes else _segment_axis(wall.start, wall.end, wall.orientation)
    return {
        "gap": 0.0 if min_gap is math.inf else min_gap,
        "covered_length": covered_length,
        "trace_ids": sorted(set(trace_ids)),
        "interval": interval,
        "axis": axis,
    }


def _axis_gap_and_overlap(
    wall_start: CatalogPoint,
    wall_end: CatalogPoint,
    trace_start: CatalogPoint,
    trace_end: CatalogPoint,
    orientation: str,
) -> tuple[float | None, float | None]:
    if orientation == "horizontal":
        gap = abs(trace_start.y - wall_start.y)
        overlap = _overlap_1d(wall_start.x, wall_end.x, trace_start.x, trace_end.x)
        return gap, overlap
    if orientation == "vertical":
        gap = abs(trace_start.x - wall_start.x)
        overlap = _overlap_1d(wall_start.y, wall_end.y, trace_start.y, trace_end.y)
        return gap, overlap
    return None, None


def _snap_wall_to_trace(
    wall_start: CatalogPoint,
    wall_end: CatalogPoint,
    trace_start: CatalogPoint,
    trace_end: CatalogPoint,
    orientation: str,
) -> tuple[CatalogPoint, CatalogPoint]:
    if orientation == "horizontal":
        x1 = max(min(wall_start.x, wall_end.x), min(trace_start.x, trace_end.x))
        x2 = min(max(wall_start.x, wall_end.x), max(trace_start.x, trace_end.x))
        y = (trace_start.y + trace_end.y) / 2
        return CatalogPoint(x=x1, y=y), CatalogPoint(x=x2, y=y)
    x = (trace_start.x + trace_end.x) / 2
    y1 = max(min(wall_start.y, wall_end.y), min(trace_start.y, trace_end.y))
    y2 = min(max(wall_start.y, wall_end.y), max(trace_start.y, trace_end.y))
    return CatalogPoint(x=x, y=y1), CatalogPoint(x=x, y=y2)


def _segment_axis(start: CatalogPoint, end: CatalogPoint, orientation: str) -> float:
    if orientation == "horizontal":
        return (start.y + end.y) / 2
    if orientation == "vertical":
        return (start.x + end.x) / 2
    raise ValueError(f"Unsupported orientation for axis calculation: {orientation}")


def _major_interval(start: CatalogPoint, end: CatalogPoint, orientation: str) -> tuple[float, float]:
    if orientation == "horizontal":
        return tuple(sorted((start.x, end.x)))
    if orientation == "vertical":
        return tuple(sorted((start.y, end.y)))
    raise ValueError(f"Unsupported orientation for interval calculation: {orientation}")


def _points_from_axis_and_interval(
    orientation: str,
    axis: float,
    interval: tuple[float, float],
) -> tuple[CatalogPoint, CatalogPoint]:
    if orientation == "horizontal":
        return CatalogPoint(x=interval[0], y=axis), CatalogPoint(x=interval[1], y=axis)
    if orientation == "vertical":
        return CatalogPoint(x=axis, y=interval[0]), CatalogPoint(x=axis, y=interval[1])
    raise ValueError(f"Unsupported orientation for projected points: {orientation}")


def _overlap_1d(a1: float, a2: float, b1: float, b2: float) -> float:
    return min(max(a1, a2), max(b1, b2)) - max(min(a1, a2), min(b1, b2))


def _merge_scalar_intervals(intervals: list[tuple[float, float]], tolerance: float = 1e-6) -> list[tuple[float, float]]:
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged: list[list[float]] = [[ordered[0][0], ordered[0][1]]]
    for start, end in ordered[1:]:
        if start <= merged[-1][1] + tolerance:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def _segment_overlap(segment_a: _Segment, segment_b: _Segment, tolerance: float) -> _Overlap | None:
    px, py = segment_a.start.x, segment_a.start.y
    qx, qy = segment_a.end.x, segment_a.end.y
    rx, ry = segment_b.start.x, segment_b.start.y
    sx, sy = segment_b.end.x, segment_b.end.y

    vx = qx - px
    vy = qy - py
    wx = sx - rx
    wy = sy - ry
    len_sq_a = vx * vx + vy * vy
    len_sq_b = wx * wx + wy * wy
    if len_sq_a == 0 or len_sq_b == 0:
        return None

    if abs(_cross(vx, vy, wx, wy)) > tolerance:
        return None
    if abs(_cross(rx - px, ry - py, vx, vy)) > tolerance:
        return None

    t0 = ((rx - px) * vx + (ry - py) * vy) / len_sq_a
    t1 = ((sx - px) * vx + (sy - py) * vy) / len_sq_a
    start_t = max(0.0, min(t0, t1))
    end_t = min(1.0, max(t0, t1))
    if end_t - start_t <= 0:
        return None

    overlap_start = _point_at(segment_a.start, segment_a.end, start_t)
    overlap_end = _point_at(segment_a.start, segment_a.end, end_t)
    if _distance(overlap_start, overlap_end) <= tolerance:
        return None

    u0 = ((overlap_start.x - rx) * wx + (overlap_start.y - ry) * wy) / len_sq_b
    u1 = ((overlap_end.x - rx) * wx + (overlap_end.y - ry) * wy) / len_sq_b

    return _Overlap(
        segment_a=segment_a,
        segment_b=segment_b,
        start=overlap_start,
        end=overlap_end,
        interval_a=tuple(sorted((start_t, end_t))),
        interval_b=tuple(sorted((u0, u1))),
    )


def _bbox_inferred_shared_wall(
    room_a: CatalogRoomTopology,
    room_b: CatalogRoomTopology,
    tolerance: float,
    minimum_overlap: float,
) -> CatalogWallBoundary | None:
    x_overlap = min(room_a.bbox.x2, room_b.bbox.x2) - max(room_a.bbox.x1, room_b.bbox.x1)
    y_overlap = min(room_a.bbox.y2, room_b.bbox.y2) - max(room_a.bbox.y1, room_b.bbox.y1)
    y_gap = min(abs(room_a.bbox.y2 - room_b.bbox.y1), abs(room_b.bbox.y2 - room_a.bbox.y1))
    x_gap = min(abs(room_a.bbox.x2 - room_b.bbox.x1), abs(room_b.bbox.x2 - room_a.bbox.x1))
    room_ids = tuple(sorted((room_a.room_id, room_b.room_id)))

    if x_overlap > minimum_overlap and y_gap <= tolerance:
        if abs(room_a.bbox.y2 - room_b.bbox.y1) <= abs(room_b.bbox.y2 - room_a.bbox.y1):
            y = (room_a.bbox.y2 + room_b.bbox.y1) / 2
        else:
            y = (room_b.bbox.y2 + room_a.bbox.y1) / 2
        start = CatalogPoint(x=max(room_a.bbox.x1, room_b.bbox.x1), y=y)
        end = CatalogPoint(x=min(room_a.bbox.x2, room_b.bbox.x2), y=y)
        return CatalogWallBoundary(
            wall_id=_build_wall_id("bbox-shared", room_ids, start, end),
            start=start,
            end=end,
            orientation="horizontal",
            length=_distance(start, end),
            is_exterior=False,
            room_ids=list(room_ids),
            boundary_kind="shared",
            owner_room_ids=list(room_ids),
            provenance="bbox_inferred",
            confidence="heuristic",
            issues=["inferred_from_bbox"],
        )

    if y_overlap > minimum_overlap and x_gap <= tolerance:
        if abs(room_a.bbox.x2 - room_b.bbox.x1) <= abs(room_b.bbox.x2 - room_a.bbox.x1):
            x = (room_a.bbox.x2 + room_b.bbox.x1) / 2
        else:
            x = (room_b.bbox.x2 + room_a.bbox.x1) / 2
        start = CatalogPoint(x=x, y=max(room_a.bbox.y1, room_b.bbox.y1))
        end = CatalogPoint(x=x, y=min(room_a.bbox.y2, room_b.bbox.y2))
        return CatalogWallBoundary(
            wall_id=_build_wall_id("bbox-shared", room_ids, start, end),
            start=start,
            end=end,
            orientation="vertical",
            length=_distance(start, end),
            is_exterior=False,
            room_ids=list(room_ids),
            boundary_kind="shared",
            owner_room_ids=list(room_ids),
            provenance="bbox_inferred",
            confidence="heuristic",
            issues=["inferred_from_bbox"],
        )

    return None


def _subtract_intervals(intervals: list[tuple[float, float]], tolerance: float = 1e-6) -> list[tuple[float, float]]:
    if not intervals:
        return [(0.0, 1.0)]
    normalized = sorted((max(0.0, start), min(1.0, end)) for start, end in intervals if end - start > tolerance)
    if not normalized:
        return [(0.0, 1.0)]

    merged: list[list[float]] = []
    for start, end in normalized:
        if not merged or start > merged[-1][1] + tolerance:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)

    gaps: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in merged:
        if start - cursor > tolerance:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if 1.0 - cursor > tolerance:
        gaps.append((cursor, 1.0))
    return gaps


def _point_at(start: CatalogPoint, end: CatalogPoint, t: float) -> CatalogPoint:
    return CatalogPoint(x=start.x + ((end.x - start.x) * t), y=start.y + ((end.y - start.y) * t))


def _orientation(start: CatalogPoint, end: CatalogPoint, tolerance: float) -> str:
    dx = end.x - start.x
    dy = end.y - start.y
    if abs(dx) <= tolerance:
        return "vertical"
    if abs(dy) <= tolerance:
        return "horizontal"
    return "diagonal"


def _distance(start: CatalogPoint, end: CatalogPoint) -> float:
    return math.hypot(end.x - start.x, end.y - start.y)


def _cross(ax: float, ay: float, bx: float, by: float) -> float:
    return (ax * by) - (ay * bx)


def _canonical_segment(start: CatalogPoint, end: CatalogPoint) -> tuple[float, float, float, float]:
    a = (round(start.x, 3), round(start.y, 3))
    b = (round(end.x, 3), round(end.y, 3))
    ordered = sorted((a, b))
    return (*ordered[0], *ordered[1])


def _build_wall_id(kind: str, room_ids: tuple[str, ...], start: CatalogPoint, end: CatalogPoint) -> str:
    canonical = _canonical_segment(start, end)
    signature = "|".join(
        [kind, *room_ids, *(f"{value:.3f}" for value in canonical)]
    )
    digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:12]
    return f"wall-{digest}"


def _prune_low_fidelity_shared_walls(
    walls: list[CatalogWallBoundary],
    topology: FloorPlanTopologyV1,
    *,
    minimum_shared_wall_length: float,
    edge_axis_tolerance: float,
    minimum_edge_overlap: float,
) -> list[CatalogWallBoundary]:
    room_by_id = {room.room_id: room for room in topology.rooms}
    filtered: list[CatalogWallBoundary] = []
    for wall in walls:
        if wall.is_exterior:
            filtered.append(wall)
            continue
        if wall.length < minimum_shared_wall_length:
            continue
        if "inferred_from_bbox" in wall.issues and wall.trace_support_status == "unsupported":
            continue
        filtered.append(wall)
    return filtered


def _room_has_parallel_edge_support(
    room: CatalogRoomTopology,
    wall: CatalogWallBoundary,
    *,
    axis_tolerance: float,
    minimum_overlap: float,
) -> bool:
    polygon = room.polygon
    if len(polygon) < 2:
        return False
    wall_axis = _segment_axis(wall.start, wall.end, wall.orientation)
    wall_interval = _major_interval(wall.start, wall.end, wall.orientation)
    for index in range(len(polygon)):
        start = polygon[index]
        end = polygon[(index + 1) % len(polygon)]
        if _orientation(start, end, 3.0) != wall.orientation:
            continue
        axis = _segment_axis(start, end, wall.orientation)
        if abs(axis - wall_axis) > axis_tolerance:
            continue
        overlap = _overlap_1d(*wall_interval, *_major_interval(start, end, wall.orientation))
        if overlap >= minimum_overlap:
            return True
    return False
