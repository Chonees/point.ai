from __future__ import annotations

import hashlib
import math
from collections import defaultdict

from backend.floor_plan_catalog.contracts import (
    CatalogBoundaryNode,
    CatalogBoundarySegment,
    CatalogCadTrace,
    CatalogPoint,
    CatalogReadiness,
    FloorPlanBoundaryGraphV1,
    FloorPlanCatalogSeed,
)


def derive_floor_plan_boundary_graph(seed: FloorPlanCatalogSeed) -> FloorPlanBoundaryGraphV1:
    wall_traces = [trace for trace in seed.cad_traces if trace.trace_kind == "wall"]
    opening_traces = [trace for trace in seed.cad_traces if trace.trace_kind in {"door", "window"}]
    nodes_by_key: dict[tuple[float, float], CatalogBoundaryNode] = {}
    boundaries: list[CatalogBoundarySegment] = []
    incident_boundary_ids: dict[str, list[str]] = {}
    opening_points_by_wall: dict[str, set[tuple[float, float]]] = _collect_opening_points(wall_traces, opening_traces)
    intersection_points_by_wall: dict[str, set[tuple[float, float]]] = _collect_intersection_points(wall_traces)

    for trace in wall_traces:
        if trace.start is None or trace.end is None:
            continue
        split_points = {
            (round(trace.start.x, 3), round(trace.start.y, 3)),
            (round(trace.end.x, 3), round(trace.end.y, 3)),
        }
        split_points.update(intersection_points_by_wall.get(trace.trace_id, set()))
        split_points.update(opening_points_by_wall.get(trace.trace_id, set()))

        ordered_points = _order_points_on_trace(trace, split_points)
        trace_opening_points = opening_points_by_wall.get(trace.trace_id, set())

        for start_point, end_point in zip(ordered_points, ordered_points[1:]):
            start_node = _get_or_create_node(nodes_by_key, start_point)
            end_node = _get_or_create_node(nodes_by_key, end_point)
            opening_ids = _opening_ids_for_segment(trace.trace_id, start_point, end_point, trace_opening_points)
            boundary_kind, owner_room_ids, confidence = _classify_boundary(
                start=start_point,
                end=end_point,
                rooms=seed.rooms,
            )
            boundary_id = _build_boundary_id(trace.trace_id, start_point, end_point)
            boundaries.append(
                CatalogBoundarySegment(
                    boundary_id=boundary_id,
                    start_node_id=start_node.node_id,
                    end_node_id=end_node.node_id,
                    start=start_point,
                    end=end_point,
                    orientation=_orientation(start_point, end_point),
                    length=round(_distance(start_point, end_point), 3),
                    source_trace_ids=[trace.trace_id],
                    boundary_kind=boundary_kind,
                    owner_room_ids=owner_room_ids,
                    opening_ids=opening_ids,
                    confidence=confidence,
                )
            )
            incident_boundary_ids.setdefault(start_node.node_id, []).append(boundary_id)
            incident_boundary_ids.setdefault(end_node.node_id, []).append(boundary_id)

    nodes = []
    opening_point_keys = {
        point
        for points in opening_points_by_wall.values()
        for point in points
    }
    for node in nodes_by_key.values():
        node_key = (round(node.point.x, 3), round(node.point.y, 3))
        nodes.append(
            node.model_copy(
                update={
                    "incident_boundary_ids": sorted(incident_boundary_ids.get(node.node_id, [])),
                    "node_kind": _node_kind(
                        node_key=node_key,
                        incident_boundary_count=len(incident_boundary_ids.get(node.node_id, [])),
                        opening_point_keys=opening_point_keys,
                    ),
                }
            )
        )

    issues = [] if boundaries else ["missing_boundaries"]
    readiness = CatalogReadiness(
        status="ready_for_boundary_review" if not issues else "needs_boundary_review",
        issues=issues,
    )
    return FloorPlanBoundaryGraphV1(
        floor_plan_id=seed.floor_plan_id,
        name=seed.name,
        canonical_unit=seed.canonical_unit,
        nodes=sorted(nodes, key=lambda node: node.node_id),
        boundaries=sorted(boundaries, key=lambda boundary: boundary.boundary_id),
        boundary_graph_readiness=readiness,
        boundary_graph_issues=issues,
    )


def _get_or_create_node(
    nodes_by_key: dict[tuple[float, float], CatalogBoundaryNode],
    point: CatalogPoint,
) -> CatalogBoundaryNode:
    key = (round(point.x, 3), round(point.y, 3))
    if key not in nodes_by_key:
        digest = hashlib.sha1(f"{key[0]:.3f}|{key[1]:.3f}".encode("utf-8")).hexdigest()[:12]
        nodes_by_key[key] = CatalogBoundaryNode(
            node_id=f"node-{digest}",
            point=CatalogPoint(x=key[0], y=key[1]),
        )
    return nodes_by_key[key]


def _build_boundary_id(trace_id: str, start: CatalogPoint, end: CatalogPoint) -> str:
    digest = hashlib.sha1(
        f"{trace_id}|{start.x:.3f}|{start.y:.3f}|{end.x:.3f}|{end.y:.3f}".encode("utf-8")
    ).hexdigest()[:12]
    return f"boundary-{digest}"


def _distance(start: CatalogPoint, end: CatalogPoint) -> float:
    return math.hypot(end.x - start.x, end.y - start.y)


def _orientation(start: CatalogPoint, end: CatalogPoint) -> str:
    dx = abs(end.x - start.x)
    dy = abs(end.y - start.y)
    if dx <= 1e-6 and dy <= 1e-6:
        return "point"
    if dx >= dy:
        return "horizontal"
    return "vertical"


def _collect_intersection_points(wall_traces: list[CatalogCadTrace]) -> dict[str, set[tuple[float, float]]]:
    points_by_trace: dict[str, set[tuple[float, float]]] = defaultdict(set)
    for index, trace in enumerate(wall_traces):
        if trace.start is None or trace.end is None:
            continue
        for other in wall_traces[index + 1 :]:
            if other.start is None or other.end is None:
                continue
            intersection = _orthogonal_intersection_point(trace, other)
            if intersection is None:
                continue
            points_by_trace[trace.trace_id].add(intersection)
            points_by_trace[other.trace_id].add(intersection)
    return points_by_trace


def _collect_opening_points(
    wall_traces: list[CatalogCadTrace],
    opening_traces: list[CatalogCadTrace],
) -> dict[str, set[tuple[float, float]]]:
    points_by_trace: dict[str, set[tuple[float, float]]] = defaultdict(set)
    for wall in wall_traces:
        if wall.start is None or wall.end is None:
            continue
        for opening in opening_traces:
            if opening.start is None or opening.end is None:
                continue
            points = _opening_cut_points(wall, opening)
            if not points:
                continue
            points_by_trace[wall.trace_id].update(points)
    return points_by_trace


def _orthogonal_intersection_point(
    trace: CatalogCadTrace,
    other: CatalogCadTrace,
) -> tuple[float, float] | None:
    orientation = _orientation(trace.start, trace.end)
    other_orientation = _orientation(other.start, other.end)
    if orientation == other_orientation:
        return None
    if orientation == "horizontal" and other_orientation == "vertical":
        x = other.start.x
        y = trace.start.y
        if _point_on_segment(x, y, trace.start, trace.end) and _point_on_segment(x, y, other.start, other.end):
            return (round(x, 3), round(y, 3))
        return None
    if orientation == "vertical" and other_orientation == "horizontal":
        x = trace.start.x
        y = other.start.y
        if _point_on_segment(x, y, trace.start, trace.end) and _point_on_segment(x, y, other.start, other.end):
            return (round(x, 3), round(y, 3))
        return None
    return None


def _opening_cut_points(
    wall: CatalogCadTrace,
    opening: CatalogCadTrace,
) -> set[tuple[float, float]]:
    wall_orientation = _orientation(wall.start, wall.end)
    opening_orientation = _orientation(opening.start, opening.end)
    if wall_orientation != opening_orientation:
        return set()
    points: set[tuple[float, float]] = set()
    if wall_orientation == "horizontal" and abs(opening.start.y - wall.start.y) <= 1e-6:
        points.add((round(opening.start.x, 3), round(opening.start.y, 3)))
        points.add((round(opening.end.x, 3), round(opening.end.y, 3)))
    if wall_orientation == "vertical" and abs(opening.start.x - wall.start.x) <= 1e-6:
        points.add((round(opening.start.x, 3), round(opening.start.y, 3)))
        points.add((round(opening.end.x, 3), round(opening.end.y, 3)))
    return {point for point in points if _point_on_segment(point[0], point[1], wall.start, wall.end)}


def _order_points_on_trace(
    trace: CatalogCadTrace,
    point_keys: set[tuple[float, float]],
) -> list[CatalogPoint]:
    points = [CatalogPoint(x=x, y=y) for x, y in point_keys]
    orientation = _orientation(trace.start, trace.end)
    if orientation == "vertical":
        points.sort(key=lambda point: (point.y, point.x))
    else:
        points.sort(key=lambda point: (point.x, point.y))
    return points


def _opening_ids_for_segment(
    trace_id: str,
    start: CatalogPoint,
    end: CatalogPoint,
    opening_points: set[tuple[float, float]],
) -> list[str]:
    start_key = (round(start.x, 3), round(start.y, 3))
    end_key = (round(end.x, 3), round(end.y, 3))
    if start_key in opening_points or end_key in opening_points:
        return [f"opening-cut-{trace_id}"]
    return []


def _node_kind(
    *,
    node_key: tuple[float, float],
    incident_boundary_count: int,
    opening_point_keys: set[tuple[float, float]],
) -> str:
    if node_key in opening_point_keys:
        return "opening_cut"
    if incident_boundary_count >= 3:
        return "tee"
    return "corner"


def _point_on_segment(x: float, y: float, start: CatalogPoint, end: CatalogPoint, tolerance: float = 1e-6) -> bool:
    if min(start.x, end.x) - tolerance <= x <= max(start.x, end.x) + tolerance and min(start.y, end.y) - tolerance <= y <= max(start.y, end.y) + tolerance:
        area = abs((end.x - start.x) * (y - start.y) - (end.y - start.y) * (x - start.x))
        return area <= tolerance
    return False


def _classify_boundary(
    *,
    start: CatalogPoint,
    end: CatalogPoint,
    rooms,
    axis_tolerance: float = 8.0,
    minimum_overlap: float = 8.0,
) -> tuple[str, list[str], str]:
    orientation = _orientation(start, end)
    owner_room_ids: list[str] = []
    for room in rooms:
        bbox = room.bbox
        if orientation == "horizontal":
            overlap = _overlap_1d(start.x, end.x, bbox.x1, bbox.x2)
            touches_bbox_edge = abs(start.y - bbox.y1) <= axis_tolerance or abs(start.y - bbox.y2) <= axis_tolerance
        else:
            overlap = _overlap_1d(start.y, end.y, bbox.y1, bbox.y2)
            touches_bbox_edge = abs(start.x - bbox.x1) <= axis_tolerance or abs(start.x - bbox.x2) <= axis_tolerance
        if overlap >= minimum_overlap and touches_bbox_edge:
            room_id = _room_id_for(room)
            if room_id not in owner_room_ids:
                owner_room_ids.append(room_id)

    if len(owner_room_ids) == 2:
        return "shared", sorted(owner_room_ids), "trace_partitioned"
    if len(owner_room_ids) == 1:
        return "exterior", owner_room_ids, "trace_exact"
    return "unknown", sorted(owner_room_ids), "unverified"


def _room_id_for(room) -> str:
    try:
        from backend.floor_plan_catalog.topology import _build_room_id  # type: ignore

        slug = "".join(char.lower() if char.isalnum() else "-" for char in room.name).strip("-")
        return _build_room_id(room, slug)
    except Exception:
        digest = hashlib.sha1(f"{room.name}|{room.bbox.x1:.3f}|{room.bbox.y1:.3f}|{room.bbox.x2:.3f}|{room.bbox.y2:.3f}".encode("utf-8")).hexdigest()[:12]
        return f"room-{digest}"


def _overlap_1d(a1: float, a2: float, b1: float, b2: float) -> float:
    return max(0.0, min(max(a1, a2), max(b1, b2)) - max(min(a1, a2), min(b1, b2)))
