from __future__ import annotations

import hashlib
import re

from backend.floor_plan_catalog.contracts import (
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
) -> FloorPlanTopologyV1:
    supported_adjacency: dict[str, set[str]] = {room.room_id: set() for room in topology.rooms}

    for wall in wall_graph.walls:
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
        heuristic_ids = sorted(set(room.adjacent_room_ids) - set(supported_ids))
        issues = [issue for issue in room.issues if issue not in {"inferred_adjacency", "isolated_room"}]

        if supported_ids:
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
                    "heuristic_adjacent_room_ids": heuristic_ids,
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
