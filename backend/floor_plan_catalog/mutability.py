from __future__ import annotations

from collections import defaultdict

from backend.floor_plan_catalog.contracts import (
    CatalogBoundarySegment,
    CatalogOpening,
    CatalogRoomTopology,
    CatalogWallBoundary,
    FloorPlanBoundaryGraphV1,
    FloorPlanOpeningGraphV1,
    FloorPlanTopologyV1,
    FloorPlanWallGraphV1,
)

_WET_ZONE_CATEGORIES = {"bath", "powder_room", "kitchen", "utility"}
_CORE_CATEGORIES = _WET_ZONE_CATEGORIES | {"entry", "hall", "closet"}
_LOCKED_CATEGORIES = {"patio", "porch"}
_FLEXIBLE_CATEGORIES = {"bedroom", "living_room", "dining", "garage"}
_HABITABLE_CATEGORIES = {"bedroom", "living_room", "dining", "entry", "hall"}


def derive_floor_plan_mutability(
    topology: FloorPlanTopologyV1,
    wall_graph: FloorPlanWallGraphV1,
    opening_graph: FloorPlanOpeningGraphV1,
    boundary_graph: FloorPlanBoundaryGraphV1,
) -> tuple[FloorPlanTopologyV1, FloorPlanWallGraphV1, FloorPlanOpeningGraphV1, FloorPlanBoundaryGraphV1]:
    rooms = [_derive_room_constraints(room) for room in topology.rooms]
    rooms_by_id = {room.room_id: room for room in rooms}

    boundary_match_by_wall_id = _match_walls_to_boundaries(wall_graph.walls, boundary_graph.boundaries)
    opening_host_boundary_ids = _map_openings_to_boundaries(opening_graph.openings, boundary_match_by_wall_id, boundary_graph.boundaries)

    opening_special_reasons: dict[str, list[str]] = {}
    for opening in opening_graph.openings:
        reasons: list[str] = []
        host_boundary = None
        if opening_host_boundary_ids.get(opening.opening_id) is not None:
            host_boundary = next(
                (boundary for boundary in boundary_graph.boundaries if boundary.boundary_id == opening_host_boundary_ids[opening.opening_id]),
                None,
            )
        host_wall = next((wall for wall in wall_graph.walls if wall.wall_id == opening.host_wall_id), None)
        if _is_required_egress_door(opening, rooms_by_id, host_wall):
            reasons.append("required_egress_door")
        if _is_required_bedroom_egress_opening(opening, rooms_by_id, host_boundary, host_wall):
            reasons.append("required_egress_opening")
        opening_special_reasons[opening.opening_id] = reasons

    actual_opening_ids_by_boundary: dict[str, list[str]] = defaultdict(list)
    special_reasons_by_boundary: dict[str, list[str]] = defaultdict(list)
    for opening in opening_graph.openings:
        boundary_id = opening_host_boundary_ids.get(opening.opening_id)
        if boundary_id is not None:
            actual_opening_ids_by_boundary[boundary_id].append(opening.opening_id)
            special_reasons_by_boundary[boundary_id].extend(opening_special_reasons.get(opening.opening_id, []))

    boundaries = [
        _derive_boundary_constraints(
            boundary,
            rooms_by_id,
            opening_ids=actual_opening_ids_by_boundary.get(boundary.boundary_id, []),
            special_opening_reasons=special_reasons_by_boundary.get(boundary.boundary_id, []),
        )
        for boundary in boundary_graph.boundaries
    ]
    boundaries_by_id = {boundary.boundary_id: boundary for boundary in boundaries}

    openings_by_host_wall: dict[str, list[CatalogOpening]] = defaultdict(list)
    for opening in opening_graph.openings:
        if opening.host_wall_id:
            openings_by_host_wall[opening.host_wall_id].append(opening)

    walls = [
        _derive_wall_constraints(
            wall,
            rooms_by_id,
            boundary_id=boundary_match_by_wall_id.get(wall.wall_id),
            boundaries_by_id=boundaries_by_id,
            hosted_openings=openings_by_host_wall.get(wall.wall_id, []),
            opening_special_reasons=opening_special_reasons,
        )
        for wall in wall_graph.walls
    ]
    walls_by_id = {wall.wall_id: wall for wall in walls}

    openings = [
        _derive_opening_constraints(
            opening,
            walls_by_id=walls_by_id,
            opening_special_reasons=opening_special_reasons.get(opening.opening_id, []),
        )
        for opening in opening_graph.openings
    ]

    return (
        topology.model_copy(update={"rooms": rooms}),
        wall_graph.model_copy(update={"walls": walls}),
        opening_graph.model_copy(update={"openings": openings}),
        boundary_graph.model_copy(update={"boundaries": boundaries}),
    )


def _derive_room_constraints(room: CatalogRoomTopology) -> CatalogRoomTopology:
    category = room.category
    reasons: list[str] = []
    is_wet_zone = category in _WET_ZONE_CATEGORIES
    is_core = category in _CORE_CATEGORIES

    if is_wet_zone:
        reasons.append("wet_core")
    if category in {"entry", "hall"}:
        reasons.append("critical_circulation")
    if category == "closet":
        reasons.append("core_storage")
    if category in _LOCKED_CATEGORIES:
        reasons.append("outdoor_locked")

    if category in _LOCKED_CATEGORIES:
        mutability = "locked"
    elif category in _CORE_CATEGORIES:
        mutability = "protected"
    elif category in _FLEXIBLE_CATEGORIES:
        mutability = "flexible"
    else:
        mutability = "protected"
        reasons.append("conservative_default")

    min_width, min_height, min_area = _derive_room_minimums(room, mutability)
    if mutability == "flexible" and _room_hits_hard_floors(room):
        mutability = "protected"
        reasons.append("near_minimum_geometry")
        min_width, min_height, min_area = room.width, room.height, room.area

    return room.model_copy(
        update={
            "is_wet_zone": is_wet_zone,
            "is_core": is_core,
            "mutability": mutability,
            "min_width": round(min_width, 3) if min_width is not None else None,
            "min_height": round(min_height, 3) if min_height is not None else None,
            "min_area": round(min_area, 3) if min_area is not None else None,
            "constraint_reasons": sorted(set(reasons)),
        }
    )


def _derive_room_minimums(room: CatalogRoomTopology, mutability: str) -> tuple[float | None, float | None, float | None]:
    if mutability in {"locked", "protected"}:
        return room.width, room.height, room.area

    width_floor = 96.0 if room.category in {"garage", "living_room", "dining"} else 84.0
    height_floor = 96.0 if room.category in {"bedroom", "living_room", "garage"} else 72.0
    area_floor = 0.0
    if room.category in _HABITABLE_CATEGORIES or room.category == "bedroom":
        area_floor = 10080.0

    return (
        max(width_floor, room.width * 0.85),
        max(height_floor, room.height * 0.85),
        max(area_floor, room.area * 0.8),
    )


def _room_hits_hard_floors(room: CatalogRoomTopology) -> bool:
    if room.category in {"garage", "living_room", "dining"}:
        width_floor = 96.0
    else:
        width_floor = 84.0

    if room.category in {"bedroom", "living_room", "garage"}:
        height_floor = 96.0
    else:
        height_floor = 72.0

    area_floor = 10080.0 if room.category in _HABITABLE_CATEGORIES or room.category == "bedroom" else 0.0

    return room.width <= width_floor or room.height <= height_floor or room.area <= area_floor


def _derive_boundary_constraints(
    boundary: CatalogBoundarySegment,
    rooms_by_id: dict[str, CatalogRoomTopology],
    *,
    opening_ids: list[str],
    special_opening_reasons: list[str],
) -> CatalogBoundarySegment:
    reasons = list(boundary.constraint_reasons)

    if boundary.boundary_kind in {"duplicate", "artifact", "support"}:
        reasons.append("non_canonical_boundary")
        return boundary.model_copy(
            update={
                "opening_ids": sorted(set(boundary.opening_ids + opening_ids)),
                "movable": False,
                "mutability": "derived_only",
                "constraint_reasons": sorted(set(reasons)),
            }
        )

    room_mutabilities = {
        rooms_by_id[room_id].mutability
        for room_id in boundary.owner_room_ids
        if room_id in rooms_by_id
    }

    if _is_garage_separation(boundary, rooms_by_id):
        mutability = "protected"
        reasons.append("garage_separation")
    elif boundary.structural_unknown or boundary.boundary_kind == "unknown":
        mutability = "locked"
        reasons.append("structural_unknown")
    elif "required_egress_door" in special_opening_reasons:
        mutability = "locked"
        reasons.append("required_egress_door")
    elif "required_egress_opening" in special_opening_reasons:
        mutability = "protected"
        reasons.append("required_egress_opening")
    elif "locked" in room_mutabilities:
        mutability = "locked"
    elif "protected" in room_mutabilities:
        mutability = "protected"
    elif opening_ids:
        mutability = "movable_with_rehost"
    else:
        mutability = "movable"

    return boundary.model_copy(
        update={
            "opening_ids": sorted(set(boundary.opening_ids + opening_ids)),
            "movable": mutability in {"movable", "movable_with_rehost"},
            "mutability": mutability,
            "constraint_reasons": sorted(set(reasons + _boundary_reasons(boundary, room_mutabilities, mutability, special_opening_reasons))),
        }
    )


def _boundary_reasons(
    boundary: CatalogBoundarySegment,
    room_mutabilities: set[str],
    mutability: str,
    special_opening_reasons: list[str],
) -> list[str]:
    reasons: list[str] = []
    if boundary.boundary_kind == "exterior":
        reasons.append("exterior_boundary")
    if boundary.boundary_kind == "shared":
        reasons.append("shared_boundary")
    if "required_egress_opening" in special_opening_reasons:
        reasons.append("required_egress_opening")
    if "required_egress_door" in special_opening_reasons:
        reasons.append("required_egress_door")
    if "locked" in room_mutabilities:
        reasons.append("locked_room_owner")
    if "protected" in room_mutabilities:
        reasons.append("protected_room_owner")
    if mutability == "movable_with_rehost":
        reasons.append("hosted_opening")
    if mutability == "movable":
        reasons.append("flexible_owner_geometry")
    return reasons


def _derive_wall_constraints(
    wall: CatalogWallBoundary,
    rooms_by_id: dict[str, CatalogRoomTopology],
    *,
    boundary_id: str | None,
    boundaries_by_id: dict[str, CatalogBoundarySegment],
    hosted_openings: list[CatalogOpening],
    opening_special_reasons: dict[str, list[str]],
) -> CatalogWallBoundary:
    if boundary_id and boundary_id in boundaries_by_id:
        boundary = boundaries_by_id[boundary_id]
        return wall.model_copy(
            update={
                "movable": boundary.movable,
                "mutability": boundary.mutability,
                "structural_unknown": boundary.structural_unknown,
                "constraint_reasons": sorted(set(boundary.constraint_reasons)),
            }
        )

    reasons: list[str] = []
    room_mutabilities = {
        rooms_by_id[room_id].mutability
        for room_id in wall.owner_room_ids
        if room_id in rooms_by_id
    }
    if any("required_egress_door" in opening_special_reasons.get(opening.opening_id, []) for opening in hosted_openings):
        mutability = "locked"
        reasons.append("required_egress_door")
    elif any("required_egress_opening" in opening_special_reasons.get(opening.opening_id, []) for opening in hosted_openings):
        mutability = "protected"
        reasons.append("required_egress_opening")
    elif "locked" in room_mutabilities:
        mutability = "locked"
        reasons.append("locked_room_owner")
    elif _is_garage_separation_wall(wall, rooms_by_id):
        mutability = "protected"
        reasons.append("garage_separation")
    elif "protected" in room_mutabilities:
        mutability = "protected"
        reasons.append("protected_room_owner")
    elif hosted_openings:
        mutability = "movable_with_rehost"
        reasons.append("hosted_opening")
    else:
        mutability = "movable" if wall.boundary_kind in {"shared", "exterior"} else "derived_only"
        if mutability == "movable":
            reasons.append("flexible_owner_geometry")
        else:
            reasons.append("non_canonical_boundary")

    return wall.model_copy(
        update={
            "movable": mutability in {"movable", "movable_with_rehost"},
            "mutability": mutability,
            "constraint_reasons": sorted(set(reasons)),
        }
    )


def _derive_opening_constraints(
    opening: CatalogOpening,
    *,
    walls_by_id: dict[str, CatalogWallBoundary],
    opening_special_reasons: list[str],
) -> CatalogOpening:
    reasons = list(opening.constraint_reasons)
    reasons.extend(opening_special_reasons)

    if opening.confidence in {"opening_artifact", "unhosted"}:
        return opening.model_copy(
            update={
                "rehost_required": False,
                "rehostable": False,
                "constraint_reasons": sorted(set(reasons + (["artifact_opening"] if opening.confidence == "opening_artifact" else ["unhosted_opening"]))),
            }
        )

    if "required_egress_door" in opening_special_reasons or "required_egress_opening" in opening_special_reasons:
        return opening.model_copy(
            update={
                "rehost_required": False,
                "rehostable": False,
                "constraint_reasons": sorted(set(reasons)),
            }
        )

    host_wall = walls_by_id.get(opening.host_wall_id or "")
    if host_wall is None:
        return opening.model_copy(
            update={
                "rehost_required": False,
                "rehostable": False,
                "constraint_reasons": sorted(set(reasons + ["missing_host_wall"])),
            }
        )

    rehostable = host_wall.mutability in {"movable", "movable_with_rehost"}
    return opening.model_copy(
        update={
            "rehost_required": rehostable,
            "rehostable": rehostable,
            "constraint_reasons": sorted(set(reasons + (["host_boundary_movable"] if rehostable else ["host_boundary_protected"]))),
        }
    )


def _is_required_egress_door(
    opening: CatalogOpening,
    rooms_by_id: dict[str, CatalogRoomTopology],
    host_wall: CatalogWallBoundary | None,
) -> bool:
    return (
        opening.opening_kind == "door"
        and host_wall is not None
        and host_wall.is_exterior
        and any(rooms_by_id.get(room_id) and rooms_by_id[room_id].category == "entry" for room_id in opening.owner_room_ids)
        and len(opening.connected_room_ids) == 0
    )


def _is_required_bedroom_egress_opening(
    opening: CatalogOpening,
    rooms_by_id: dict[str, CatalogRoomTopology],
    host_boundary: CatalogBoundarySegment | None,
    host_wall: CatalogWallBoundary | None,
) -> bool:
    is_exterior_host = (host_boundary is not None and host_boundary.boundary_kind == "exterior") or (host_wall is not None and host_wall.is_exterior)
    return (
        opening.opening_kind == "window"
        and is_exterior_host
        and any(rooms_by_id.get(room_id) and rooms_by_id[room_id].category == "bedroom" for room_id in opening.owner_room_ids)
    )


def _is_garage_separation(boundary: CatalogBoundarySegment, rooms_by_id: dict[str, CatalogRoomTopology]) -> bool:
    categories = {rooms_by_id[room_id].category for room_id in boundary.owner_room_ids if room_id in rooms_by_id}
    return "garage" in categories and len(categories - {"garage"}) > 0


def _is_garage_separation_wall(wall: CatalogWallBoundary, rooms_by_id: dict[str, CatalogRoomTopology]) -> bool:
    categories = {rooms_by_id[room_id].category for room_id in wall.owner_room_ids if room_id in rooms_by_id}
    return "garage" in categories and len(categories - {"garage"}) > 0


def _match_walls_to_boundaries(
    walls: list[CatalogWallBoundary],
    boundaries: list[CatalogBoundarySegment],
) -> dict[str, str]:
    canonical_boundaries = [boundary for boundary in boundaries if boundary.boundary_kind in {"shared", "exterior"}]
    matches: dict[str, str] = {}
    for wall in walls:
        if wall.provenance == "boundary_graph_exterior":
            boundary_id = f"boundary-{wall.wall_id.removeprefix('wall-')}"
            if any(boundary.boundary_id == boundary_id for boundary in boundaries):
                matches[wall.wall_id] = boundary_id
                continue
        match = _best_boundary_match_for_wall(wall, canonical_boundaries)
        if match is not None:
            matches[wall.wall_id] = match.boundary_id
    return matches


def _best_boundary_match_for_wall(
    wall: CatalogWallBoundary,
    boundaries: list[CatalogBoundarySegment],
) -> CatalogBoundarySegment | None:
    best: CatalogBoundarySegment | None = None
    best_score: tuple[float, float, str] | None = None
    wall_owner_ids = set(wall.owner_room_ids)
    wall_interval = _major_interval(wall.start, wall.end, wall.orientation)
    wall_axis = _segment_axis(wall.start, wall.end, wall.orientation)
    for boundary in boundaries:
        if boundary.orientation != wall.orientation:
            continue
        if boundary.boundary_kind != wall.boundary_kind:
            continue
        if set(boundary.owner_room_ids) != wall_owner_ids:
            continue
        overlap = _overlap_1d(*wall_interval, *_major_interval(boundary.start, boundary.end, boundary.orientation))
        if overlap <= 0:
            continue
        axis_gap = abs(wall_axis - _segment_axis(boundary.start, boundary.end, boundary.orientation))
        score = (axis_gap, -overlap, boundary.boundary_id)
        if best_score is None or score < best_score:
            best_score = score
            best = boundary
    return best


def _map_openings_to_boundaries(
    openings: list[CatalogOpening],
    boundary_match_by_wall_id: dict[str, str],
    boundaries: list[CatalogBoundarySegment],
) -> dict[str, str | None]:
    canonical_boundaries = [boundary for boundary in boundaries if boundary.boundary_kind in {"shared", "exterior"}]
    mapping: dict[str, str | None] = {}
    for opening in openings:
        if opening.host_wall_id and opening.host_wall_id in boundary_match_by_wall_id:
            mapping[opening.opening_id] = boundary_match_by_wall_id[opening.host_wall_id]
            continue
        mapping[opening.opening_id] = _best_boundary_match_for_opening(opening, canonical_boundaries)
    return mapping


def _best_boundary_match_for_opening(
    opening: CatalogOpening,
    boundaries: list[CatalogBoundarySegment],
) -> str | None:
    best_id: str | None = None
    best_score: tuple[float, float, str] | None = None
    opening_interval = _major_interval(opening.start, opening.end, opening.orientation)
    opening_axis = _segment_axis(opening.start, opening.end, opening.orientation)
    opening_owner_ids = set(opening.owner_room_ids)
    for boundary in boundaries:
        if boundary.orientation != opening.orientation:
            continue
        if opening_owner_ids and not opening_owner_ids.issubset(set(boundary.owner_room_ids)):
            continue
        overlap = _overlap_1d(*opening_interval, *_major_interval(boundary.start, boundary.end, boundary.orientation))
        if overlap <= 0:
            continue
        axis_gap = abs(opening_axis - _segment_axis(boundary.start, boundary.end, boundary.orientation))
        score = (axis_gap, -overlap, boundary.boundary_id)
        if best_score is None or score < best_score:
            best_score = score
            best_id = boundary.boundary_id
    return best_id


def _segment_axis(start, end, orientation: str) -> float:
    if orientation == "horizontal":
        return (start.y + end.y) / 2
    if orientation == "vertical":
        return (start.x + end.x) / 2
    return 0.0


def _major_interval(start, end, orientation: str) -> tuple[float, float]:
    if orientation == "horizontal":
        return tuple(sorted((start.x, end.x)))
    if orientation == "vertical":
        return tuple(sorted((start.y, end.y)))
    return (0.0, 0.0)


def _overlap_1d(a1: float, a2: float, b1: float, b2: float) -> float:
    return max(0.0, min(max(a1, a2), max(b1, b2)) - max(min(a1, a2), min(b1, b2)))
