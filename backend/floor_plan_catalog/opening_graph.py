from __future__ import annotations

import hashlib
import math
from collections import defaultdict

from backend.floor_plan_catalog.contracts import (
    CatalogCadTrace,
    CatalogOpening,
    CatalogPoint,
    CatalogRoomTopology,
    CatalogWallBoundary,
    FloorPlanOpeningGraphV1,
    FloorPlanTopologyV1,
    FloorPlanWallGraphV1,
    OpeningGraphReadiness,
)


def derive_floor_plan_opening_graph(
    topology: FloorPlanTopologyV1,
    wall_graph: FloorPlanWallGraphV1,
    cad_traces: list[CatalogCadTrace] | None = None,
    *,
    host_tolerance: float = 16.0,
    minimum_overlap: float = 4.0,
    grouping_tolerance: float = 12.0,
    room_tolerance: float = 6.0,
) -> FloorPlanOpeningGraphV1:
    rooms_by_id = {room.room_id: room for room in topology.rooms}
    candidate_walls = [wall for wall in wall_graph.walls if wall.confidence != "unsupported"]
    attachments: list[dict] = []

    for trace in cad_traces or []:
        if trace.trace_kind not in {"door", "window"}:
            continue
        host_candidates = _find_host_candidates(
            trace,
            candidate_walls,
            host_tolerance=host_tolerance,
            minimum_overlap=minimum_overlap,
        )
        touching_room_ids = _trace_touching_room_ids(trace, topology.rooms, tolerance=room_tolerance)
        attachments.append(
            {
                "trace": trace,
                "host": host_candidates[0] if host_candidates else None,
                "host_candidates": host_candidates,
                "touching_room_ids": touching_room_ids,
            }
        )

    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for attachment in attachments:
        trace: CatalogCadTrace = attachment["trace"]
        center = _trace_center_point(trace)
        key = (
            trace.trace_kind,
            round(center.x / grouping_tolerance) if grouping_tolerance else round(center.x),
            round(center.y / grouping_tolerance) if grouping_tolerance else round(center.y),
        )
        grouped[key].append(attachment)

    openings: list[CatalogOpening] = []
    for attachments_for_key in grouped.values():
        host = _select_group_host(
            attachments_for_key,
            candidate_walls,
            host_tolerance=host_tolerance,
            minimum_overlap=minimum_overlap,
        )
        openings.append(_build_opening(attachments_for_key, rooms_by_id, host))

    opening_graph_issues = sorted({issue for opening in openings for issue in opening.issues})
    if not openings:
        opening_graph_issues.append("missing_openings")
    opening_graph_issues = sorted(set(opening_graph_issues))
    readiness = OpeningGraphReadiness(
        status="ready_for_opening_review" if not opening_graph_issues else "needs_opening_review",
        issues=opening_graph_issues,
    )
    return FloorPlanOpeningGraphV1(
        floor_plan_id=topology.floor_plan_id,
        name=topology.name,
        canonical_unit=topology.canonical_unit,
        openings=sorted(openings, key=lambda opening: opening.opening_id),
        opening_graph_readiness=readiness,
        opening_graph_issues=opening_graph_issues,
    )


def _build_opening(
    attachments: list[dict],
    rooms_by_id: dict[str, CatalogRoomTopology],
    host: dict | None,
) -> CatalogOpening:
    trace: CatalogCadTrace = attachments[0]["trace"]
    trace_ids = sorted({attachment["trace"].trace_id for attachment in attachments})
    touching_room_ids = sorted({room_id for attachment in attachments for room_id in attachment["touching_room_ids"]})
    host_wall: CatalogWallBoundary | None = host["wall"] if host else None
    orientation = host_wall.orientation if host_wall else _trace_orientation(trace)
    interval = _merge_intervals(
        [
            _project_trace_interval_to_wall(attachment["trace"], host_wall)
            for attachment in attachments
            if _project_trace_interval_to_wall(attachment["trace"], host_wall) is not None
        ]
    )
    if host_wall is not None and interval is not None:
        start, end = _points_from_interval(host_wall, interval)
        offset = round(interval[0] - _wall_major_interval(host_wall)[0], 3)
        span = round(interval[1] - interval[0], 3)
        owner_room_ids = list(host_wall.owner_room_ids)
        connected_room_ids = _connected_room_ids(trace.trace_kind, owner_room_ids, touching_room_ids)
        confidence = "hosted"
        issues: list[str] = []
    else:
        start, end = _trace_anchor_points(trace)
        offset = 0.0
        span = round(_distance(start, end), 3)
        owner_room_ids = []
        connected_room_ids = _connected_room_ids(trace.trace_kind, [], touching_room_ids)
        confidence = "unhosted"
        issues = ["unhosted_opening"]

    signature = "|".join(
        [
            trace.trace_kind,
            host_wall.wall_id if host_wall else "unhosted",
            f"{start.x:.3f}",
            f"{start.y:.3f}",
            f"{end.x:.3f}",
            f"{end.y:.3f}",
            ",".join(trace_ids),
        ]
    )
    digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:12]
    return CatalogOpening(
        opening_id=f"opening-{trace.trace_kind}-{digest}",
        opening_kind=trace.trace_kind,
        host_wall_id=host_wall.wall_id if host_wall else None,
        owner_room_ids=owner_room_ids,
        connected_room_ids=connected_room_ids,
        trace_ids=trace_ids,
        orientation=orientation,
        start=start,
        end=end,
        offset=offset,
        span=span,
        confidence=confidence,
        issues=sorted(set(issues)),
    )


def _find_host_wall(
    trace: CatalogCadTrace,
    walls: list[CatalogWallBoundary],
    *,
    host_tolerance: float,
    minimum_overlap: float,
) -> dict | None:
    candidates = _find_host_candidates(
        trace,
        walls,
        host_tolerance=host_tolerance,
        minimum_overlap=minimum_overlap,
    )
    if not candidates:
        return None
    return {"wall": candidates[0]["wall"]}


def _find_host_candidates(
    trace: CatalogCadTrace,
    walls: list[CatalogWallBoundary],
    *,
    host_tolerance: float,
    minimum_overlap: float,
) -> list[dict]:
    trace_bbox = trace.bbox
    candidates: list[dict] = []
    for wall in walls:
        if wall.orientation not in {"horizontal", "vertical"}:
            continue
        wall_interval = _wall_major_interval(wall)
        if wall.orientation == "horizontal":
            overlap = _overlap_1d(trace_bbox.x1, trace_bbox.x2, wall_interval[0], wall_interval[1])
            axis_gap = _gap_to_interval((trace_bbox.y1, trace_bbox.y2), wall.start.y)
            center_on_wall = wall_interval[0] <= ((trace_bbox.x1 + trace_bbox.x2) / 2) <= wall_interval[1]
        else:
            overlap = _overlap_1d(trace_bbox.y1, trace_bbox.y2, wall_interval[0], wall_interval[1])
            axis_gap = _gap_to_interval((trace_bbox.x1, trace_bbox.x2), wall.start.x)
            center_on_wall = wall_interval[0] <= ((trace_bbox.y1 + trace_bbox.y2) / 2) <= wall_interval[1]
        if axis_gap > host_tolerance:
            continue
        if overlap < minimum_overlap and not center_on_wall:
            continue
        boundary_penalty = 0 if wall.boundary_kind == "shared" and trace.trace_kind == "door" else 1
        score = (
            round(axis_gap, 3),
            -round(max(overlap, 0.0), 3),
            boundary_penalty,
            *_wall_host_rank(wall, trace.trace_kind),
        )
        candidates.append({"wall": wall, "score": score})
    candidates.sort(key=lambda item: item["score"])
    return candidates


def _select_group_host(
    attachments: list[dict],
    walls: list[CatalogWallBoundary],
    *,
    host_tolerance: float,
    minimum_overlap: float,
) -> dict | None:
    candidates_by_wall_id: dict[str, dict] = {}
    for attachment in attachments:
        for candidate in attachment.get("host_candidates", []):
            wall = candidate["wall"]
            entry = candidates_by_wall_id.setdefault(
                wall.wall_id,
                {
                    "wall": wall,
                    "support_count": 0,
                    "best_score": candidate["score"],
                },
            )
            entry["support_count"] += 1
            if candidate["score"] < entry["best_score"]:
                entry["best_score"] = candidate["score"]

    if candidates_by_wall_id:
        best = min(
            candidates_by_wall_id.values(),
            key=lambda candidate: (-candidate["support_count"], candidate["best_score"]),
        )
        return {"wall": best["wall"]}

    return _find_group_host_from_cluster(
        attachments,
        walls,
        host_tolerance=host_tolerance,
        minimum_overlap=minimum_overlap,
    )


def _find_group_host_from_cluster(
    attachments: list[dict],
    walls: list[CatalogWallBoundary],
    *,
    host_tolerance: float,
    minimum_overlap: float,
) -> dict | None:
    if not attachments:
        return None
    x1 = min(attachment["trace"].bbox.x1 for attachment in attachments)
    y1 = min(attachment["trace"].bbox.y1 for attachment in attachments)
    x2 = max(attachment["trace"].bbox.x2 for attachment in attachments)
    y2 = max(attachment["trace"].bbox.y2 for attachment in attachments)
    center = CatalogPoint(x=(x1 + x2) / 2, y=(y1 + y2) / 2)
    dominant_orientation = max(
        ("horizontal", "vertical", "point"),
        key=lambda orientation: sum(
            1 for attachment in attachments if _trace_orientation(attachment["trace"]) == orientation
        ),
    )
    if dominant_orientation == "horizontal":
        start = CatalogPoint(x=x1, y=center.y)
        end = CatalogPoint(x=x2, y=center.y)
    elif dominant_orientation == "vertical":
        start = CatalogPoint(x=center.x, y=y1)
        end = CatalogPoint(x=center.x, y=y2)
    else:
        start = center
        end = center

    synthetic_trace = CatalogCadTrace(
        trace_id="synthetic-cluster",
        trace_kind=attachments[0]["trace"].trace_kind,
        type="line",
        layer="SYNTHETIC",
        start=start,
        end=end,
        bbox=trace_bbox(x1, y1, x2, y2),
    )
    return _find_host_wall(
        synthetic_trace,
        walls,
        host_tolerance=max(host_tolerance, 18.0),
        minimum_overlap=minimum_overlap,
    )


def _wall_host_rank(wall: CatalogWallBoundary, opening_kind: str) -> tuple[int, int, int]:
    if opening_kind == "door":
        boundary_rank = {"shared": 0, "exterior": 1}.get(wall.boundary_kind, 2)
    else:
        boundary_rank = {"exterior": 0, "shared": 1}.get(wall.boundary_kind, 2)
    confidence_rank = {"exact": 0, "geometric_exact": 0, "trace_supported": 1}.get(wall.confidence, 2)
    provenance_rank = {
        "boundary_graph_exterior": 0,
        "boundary_graph_shared": 0,
        "exact_room_overlap": 0,
        "room_exterior_boundary": 1,
        "bbox_inferred": 2,
    }.get(wall.provenance, 1)
    return (boundary_rank, confidence_rank, provenance_rank)


def _trace_touching_room_ids(
    trace: CatalogCadTrace,
    rooms: list[CatalogRoomTopology],
    *,
    tolerance: float,
) -> list[str]:
    points = list(trace.points)
    if trace.start is not None:
        points.append(trace.start)
    if trace.end is not None:
        points.append(trace.end)
    points.append(CatalogPoint(x=(trace.bbox.x1 + trace.bbox.x2) / 2, y=(trace.bbox.y1 + trace.bbox.y2) / 2))
    touching = {
        room.room_id
        for room in rooms
        for point in points
        if _point_in_or_near_polygon(point, room.polygon, tolerance)
    }
    return sorted(touching)


def _connected_room_ids(
    opening_kind: str,
    owner_room_ids: list[str],
    touching_room_ids: list[str],
) -> list[str]:
    if opening_kind != "door":
        return []
    if len(owner_room_ids) == 2:
        return sorted(set(owner_room_ids))
    if len(touching_room_ids) == 2:
        return sorted(set(touching_room_ids))
    return []


def _trace_orientation(trace: CatalogCadTrace) -> str:
    start, end = _trace_anchor_points(trace)
    dx = abs(end.x - start.x)
    dy = abs(end.y - start.y)
    if dx <= 1e-6 and dy <= 1e-6:
        return "point"
    if dx >= dy:
        return "horizontal"
    return "vertical"


def _trace_anchor_points(trace: CatalogCadTrace) -> tuple[CatalogPoint, CatalogPoint]:
    if trace.points and len(trace.points) >= 2:
        return trace.points[0], trace.points[-1]
    if trace.start is not None and trace.end is not None:
        return trace.start, trace.end
    center = CatalogPoint(x=(trace.bbox.x1 + trace.bbox.x2) / 2, y=(trace.bbox.y1 + trace.bbox.y2) / 2)
    return center, center


def _project_trace_interval_to_wall(
    trace: CatalogCadTrace,
    wall: CatalogWallBoundary | None,
) -> tuple[float, float] | None:
    if wall is None or wall.orientation not in {"horizontal", "vertical"}:
        return None
    wall_interval = _wall_major_interval(wall)
    if wall.orientation == "horizontal":
        start = max(wall_interval[0], trace.bbox.x1)
        end = min(wall_interval[1], trace.bbox.x2)
        if end <= start:
            center = (trace.bbox.x1 + trace.bbox.x2) / 2
            half_span = max((trace.bbox.width or 4.0) / 2, 2.0)
            start = max(wall_interval[0], center - half_span)
            end = min(wall_interval[1], center + half_span)
    else:
        start = max(wall_interval[0], trace.bbox.y1)
        end = min(wall_interval[1], trace.bbox.y2)
        if end <= start:
            center = (trace.bbox.y1 + trace.bbox.y2) / 2
            half_span = max((trace.bbox.height or 4.0) / 2, 2.0)
            start = max(wall_interval[0], center - half_span)
            end = min(wall_interval[1], center + half_span)
    if end <= start:
        return None
    return (round(start, 3), round(end, 3))


def _points_from_interval(
    wall: CatalogWallBoundary,
    interval: tuple[float, float],
) -> tuple[CatalogPoint, CatalogPoint]:
    if wall.orientation == "horizontal":
        return CatalogPoint(x=interval[0], y=wall.start.y), CatalogPoint(x=interval[1], y=wall.start.y)
    return CatalogPoint(x=wall.start.x, y=interval[0]), CatalogPoint(x=wall.start.x, y=interval[1])


def _wall_major_interval(wall: CatalogWallBoundary) -> tuple[float, float]:
    if wall.orientation == "horizontal":
        return tuple(sorted((wall.start.x, wall.end.x)))
    if wall.orientation == "vertical":
        return tuple(sorted((wall.start.y, wall.end.y)))
    raise ValueError(f"Unsupported wall orientation: {wall.orientation}")


def _merge_intervals(intervals: list[tuple[float, float] | None]) -> tuple[float, float] | None:
    usable = sorted(interval for interval in intervals if interval is not None)
    if not usable:
        return None
    start = min(interval[0] for interval in usable)
    end = max(interval[1] for interval in usable)
    return (round(start, 3), round(end, 3))


def _gap_to_interval(interval: tuple[float, float], value: float) -> float:
    start, end = sorted(interval)
    if start <= value <= end:
        return 0.0
    return min(abs(value - start), abs(value - end))


def _overlap_1d(a1: float, a2: float, b1: float, b2: float) -> float:
    return min(max(a1, a2), max(b1, b2)) - max(min(a1, a2), min(b1, b2))


def trace_center(trace: CatalogCadTrace) -> int:
    return round(((trace.bbox.x1 + trace.bbox.x2) + (trace.bbox.y1 + trace.bbox.y2)) / 2)


def _trace_center_point(trace: CatalogCadTrace) -> CatalogPoint:
    return CatalogPoint(x=(trace.bbox.x1 + trace.bbox.x2) / 2, y=(trace.bbox.y1 + trace.bbox.y2) / 2)


def trace_bbox(x1: float, y1: float, x2: float, y2: float):
    from backend.floor_plan_catalog.contracts import CatalogBBox

    return CatalogBBox(
        x1=min(x1, x2),
        y1=min(y1, y2),
        x2=max(x1, x2),
        y2=max(y1, y2),
        width=abs(x2 - x1),
        height=abs(y2 - y1),
    )


def _point_in_or_near_polygon(point: CatalogPoint, polygon: list[CatalogPoint], tolerance: float) -> bool:
    if _point_in_polygon(point, polygon):
        return True
    for index in range(len(polygon)):
        start = polygon[index]
        end = polygon[(index + 1) % len(polygon)]
        if _distance_point_to_segment(point, start, end) <= tolerance:
            return True
    return False


def _point_in_polygon(point: CatalogPoint, polygon: list[CatalogPoint]) -> bool:
    inside = False
    for index in range(len(polygon)):
        start = polygon[index]
        end = polygon[(index + 1) % len(polygon)]
        if (start.y > point.y) == (end.y > point.y):
            continue
        x_intersection = ((end.x - start.x) * (point.y - start.y) / ((end.y - start.y) or 1e-12)) + start.x
        if point.x < x_intersection:
            inside = not inside
    return inside


def _distance_point_to_segment(point: CatalogPoint, start: CatalogPoint, end: CatalogPoint) -> float:
    dx = end.x - start.x
    dy = end.y - start.y
    if dx == 0 and dy == 0:
        return math.hypot(point.x - start.x, point.y - start.y)
    t = ((point.x - start.x) * dx + (point.y - start.y) * dy) / ((dx * dx) + (dy * dy))
    t = max(0.0, min(1.0, t))
    projection_x = start.x + (t * dx)
    projection_y = start.y + (t * dy)
    return math.hypot(point.x - projection_x, point.y - projection_y)


def _distance(start: CatalogPoint, end: CatalogPoint) -> float:
    return math.hypot(end.x - start.x, end.y - start.y)
