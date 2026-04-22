from __future__ import annotations

import hashlib
import math
import re

from backend.floor_plan_catalog.contracts import (
    CatalogCadTrace,
    CatalogPoint,
    CatalogRoom,
    CatalogRoomTopology,
    FloorPlanCatalogSeed,
    FloorPlanTopologyV1,
    FloorPlanWallGraphV1,
    TopologyReadiness,
)


EXPECTED_ISOLATED_CATEGORIES = {"patio"}


def derive_floor_plan_topology(seed: FloorPlanCatalogSeed) -> FloorPlanTopologyV1:
    rooms = [_to_room_topology(room) for room in seed.rooms]
    adjacent_room_ids: dict[str, set[str]] = {room.room_id: set() for room in rooms}
    inferred_adjacency_ids: dict[str, set[str]] = {room.room_id: set() for room in rooms}

    for index, room in enumerate(rooms):
        for other_room in rooms[index + 1 :]:
            source = _adjacency_source(room, other_room)
            if source is None:
                continue
            adjacent_room_ids[room.room_id].add(other_room.room_id)
            adjacent_room_ids[other_room.room_id].add(room.room_id)
            if source == "inferred":
                inferred_adjacency_ids[room.room_id].add(other_room.room_id)
                inferred_adjacency_ids[other_room.room_id].add(room.room_id)

    for room in rooms:
        room.adjacent_room_ids = sorted(adjacent_room_ids[room.room_id])
        room.is_exterior_touching = _touches_exterior(seed, room)
        if room.category == "unknown":
            room.issues.append("missing_category")
        if inferred_adjacency_ids[room.room_id]:
            room.issues.append("inferred_adjacency")
        if not room.adjacent_room_ids:
            room.issues.append("isolated_room")
        if room.area <= 0 or len(room.polygon) < 4:
            room.issues.append("suspicious_polygon")
        room.issues = sorted(set(room.issues))

    topology_issues = sorted({issue for room in rooms for issue in room.issues})
    readiness = TopologyReadiness(
        status="ready_for_topology_review" if not topology_issues else "needs_topology_review",
        issues=topology_issues,
    )

    return FloorPlanTopologyV1(
        floor_plan_id=seed.floor_plan_id,
        name=seed.name,
        canonical_unit=seed.canonical_unit,
        footprint_bbox=seed.footprint_bbox,
        rooms=rooms,
        topology_readiness=readiness,
        topology_issues=topology_issues,
    )


def strengthen_floor_plan_topology(
    topology: FloorPlanTopologyV1,
    wall_graph: FloorPlanWallGraphV1,
    cad_traces: list[CatalogCadTrace] | None = None,
) -> FloorPlanTopologyV1:
    supported_adjacency: dict[str, set[str]] = {room.room_id: set() for room in topology.rooms}
    opening_adjacency = _derive_opening_adjacency(topology.rooms, cad_traces or [])
    owned_wall_ids: dict[str, set[str]] = {room.room_id: set() for room in topology.rooms}
    shared_wall_ids: dict[str, set[str]] = {room.room_id: set() for room in topology.rooms}
    exterior_wall_ids: dict[str, set[str]] = {room.room_id: set() for room in topology.rooms}

    for wall in wall_graph.walls:
        for owner_room_id in wall.owner_room_ids:
            if owner_room_id not in owned_wall_ids:
                continue
            owned_wall_ids[owner_room_id].add(wall.wall_id)
            if wall.boundary_kind == "shared":
                shared_wall_ids[owner_room_id].add(wall.wall_id)
            if wall.boundary_kind == "exterior":
                exterior_wall_ids[owner_room_id].add(wall.wall_id)
        if wall.is_exterior or len(wall.room_ids) != 2:
            continue
        if wall.confidence == "unsupported":
            continue
        left_room_id, right_room_id = wall.room_ids
        supported_adjacency[left_room_id].add(right_room_id)
        supported_adjacency[right_room_id].add(left_room_id)

    rooms: list[CatalogRoomTopology] = []
    for room in topology.rooms:
        supported_ids = sorted(supported_adjacency.get(room.room_id, set()))
        opening_ids = sorted(set(opening_adjacency.get(room.room_id, set())) - set(supported_ids))
        heuristic_ids = sorted(set(room.adjacent_room_ids) - set(supported_ids) - set(opening_ids))
        issues = [issue for issue in room.issues if issue not in {"inferred_adjacency", "isolated_room"}]

        if supported_ids or opening_ids:
            isolation_status = "connected"
        elif room.category in EXPECTED_ISOLATED_CATEGORIES:
            isolation_status = "expected_isolated"
        else:
            isolation_status = "suspicious_isolated"
            issues.append("isolated_room")

        rooms.append(
            room.model_copy(
                update={
                    "adjacent_room_ids": supported_ids,
                    "opening_adjacent_room_ids": opening_ids,
                    "heuristic_adjacent_room_ids": heuristic_ids,
                    "owned_wall_ids": sorted(owned_wall_ids.get(room.room_id, set())),
                    "shared_wall_ids": sorted(shared_wall_ids.get(room.room_id, set())),
                    "exterior_wall_ids": sorted(exterior_wall_ids.get(room.room_id, set())),
                    "isolation_status": isolation_status,
                    "issues": sorted(set(issues)),
                }
            )
        )

    topology_issues = sorted({issue for room in rooms for issue in room.issues})
    readiness = TopologyReadiness(
        status="ready_for_topology_review" if not topology_issues else "needs_topology_review",
        issues=topology_issues,
    )

    return topology.model_copy(
        update={
            "rooms": rooms,
            "topology_readiness": readiness,
            "topology_issues": topology_issues,
        }
    )


def _to_room_topology(room: CatalogRoom) -> CatalogRoomTopology:
    slug = re.sub(r"[^a-z0-9]+", "-", room.name.lower()).strip("-")
    return CatalogRoomTopology(
        room_id=_build_room_id(room, slug),
        name=room.name,
        category=_infer_category(room.name),
        polygon=room.polygon,
        bbox=room.bbox,
        centroid=room.centroid,
        width=room.width,
        height=room.height,
        area=room.area,
        measurement_source=room.measurement_source,
    )


def _build_room_id(room: CatalogRoom, slug: str) -> str:
    polygon_signature = "|".join(
        f"{point.x:.3f},{point.y:.3f}" for point in room.polygon
    )
    signature = "|".join(
        [
            room.name,
            f"{room.bbox.x1:.3f}",
            f"{room.bbox.y1:.3f}",
            f"{room.bbox.x2:.3f}",
            f"{room.bbox.y2:.3f}",
            f"{room.width:.3f}",
            f"{room.height:.3f}",
            f"{room.area:.3f}",
            room.measurement_source,
            str(len(room.polygon)),
            polygon_signature,
        ]
    )
    digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:12]
    return f"room-{slug}-{digest}"


def _infer_category(name: str) -> str:
    upper = name.upper()
    if "KITCHEN" in upper:
        return "kitchen"
    if "BED" in upper:
        return "bedroom"
    if "BATH" in upper:
        return "bath"
    if "PWDR" in upper or "POWDER" in upper:
        return "powder_room"
    if "LIVING" in upper:
        return "living_room"
    if "DINING" in upper:
        return "dining"
    if "HALL" in upper:
        return "hall"
    if "ENTRY" in upper or "FOYER" in upper:
        return "entry"
    if "PATIO" in upper:
        return "patio"
    if "PORCH" in upper:
        return "porch"
    if "GARAGE" in upper:
        return "garage"
    if "UTILITY" in upper:
        return "utility"
    if "CLOSET" in upper or "WIC" in upper:
        return "closet"
    return "unknown"


def _adjacency_source(a: CatalogRoomTopology, b: CatalogRoomTopology) -> str | None:
    if _rooms_are_adjacent(a, b):
        return "exact"
    if _rooms_are_bbox_adjacent(a, b):
        return "inferred"
    return None


def _rooms_are_adjacent(a: CatalogRoomTopology, b: CatalogRoomTopology, tolerance: float = 3.0) -> bool:
    horizontal_overlap = min(a.bbox.x2, b.bbox.x2) - max(a.bbox.x1, b.bbox.x1)
    vertical_overlap = min(a.bbox.y2, b.bbox.y2) - max(a.bbox.y1, b.bbox.y1)
    touches_vertically = horizontal_overlap > tolerance and min(
        abs(a.bbox.y2 - b.bbox.y1),
        abs(b.bbox.y2 - a.bbox.y1),
    ) <= tolerance
    touches_horizontally = vertical_overlap > tolerance and min(
        abs(a.bbox.x2 - b.bbox.x1),
        abs(b.bbox.x2 - a.bbox.x1),
    ) <= tolerance
    return touches_vertically or touches_horizontally


def _rooms_are_bbox_adjacent(
    a: CatalogRoomTopology,
    b: CatalogRoomTopology,
    tolerance: float = 10.0,
    minimum_overlap: float = 12.0,
) -> bool:
    horizontal_overlap = min(a.bbox.x2, b.bbox.x2) - max(a.bbox.x1, b.bbox.x1)
    vertical_overlap = min(a.bbox.y2, b.bbox.y2) - max(a.bbox.y1, b.bbox.y1)
    vertical_gap = min(abs(a.bbox.y2 - b.bbox.y1), abs(b.bbox.y2 - a.bbox.y1))
    horizontal_gap = min(abs(a.bbox.x2 - b.bbox.x1), abs(b.bbox.x2 - a.bbox.x1))
    touches_vertically = horizontal_overlap > minimum_overlap and vertical_gap <= tolerance
    touches_horizontally = vertical_overlap > minimum_overlap and horizontal_gap <= tolerance
    return touches_vertically or touches_horizontally


def _touches_exterior(seed: FloorPlanCatalogSeed, room: CatalogRoomTopology, tolerance: float = 3.0) -> bool:
    bbox = seed.footprint_bbox
    return (
        abs(room.bbox.x1 - bbox.x1) <= tolerance
        or abs(room.bbox.y1 - bbox.y1) <= tolerance
        or abs(room.bbox.x2 - bbox.x2) <= tolerance
        or abs(room.bbox.y2 - bbox.y2) <= tolerance
    )


def _derive_opening_adjacency(
    rooms: list[CatalogRoomTopology],
    cad_traces: list[CatalogCadTrace],
    tolerance: float = 6.0,
) -> dict[str, set[str]]:
    adjacency: dict[str, set[str]] = {room.room_id: set() for room in rooms}
    if not cad_traces:
        return adjacency

    for trace in cad_traces:
        if trace.trace_kind != "door":
            continue
        start, end = _trace_endpoints(trace)
        if start is None or end is None:
            continue
        start_room_ids = {
            room.room_id
            for room in rooms
            if _point_in_or_near_polygon(start, room.polygon, tolerance)
        }
        end_room_ids = {
            room.room_id
            for room in rooms
            if _point_in_or_near_polygon(end, room.polygon, tolerance)
        }
        for start_room_id in start_room_ids:
            for end_room_id in end_room_ids:
                if start_room_id == end_room_id:
                    continue
                adjacency[start_room_id].add(end_room_id)
                adjacency[end_room_id].add(start_room_id)

    return adjacency


def _trace_endpoints(trace: CatalogCadTrace) -> tuple[CatalogPoint | None, CatalogPoint | None]:
    if trace.points and len(trace.points) >= 2:
        return trace.points[0], trace.points[-1]
    return trace.start, trace.end


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
