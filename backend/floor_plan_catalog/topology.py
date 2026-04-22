from __future__ import annotations

import hashlib
import re

from backend.floor_plan_catalog.contracts import (
    CatalogRoom,
    CatalogRoomTopology,
    FloorPlanCatalogSeed,
    FloorPlanTopologyV1,
    TopologyReadiness,
)


def derive_floor_plan_topology(seed: FloorPlanCatalogSeed) -> FloorPlanTopologyV1:
    rooms = [_to_room_topology(room) for room in seed.rooms]

    for room in rooms:
        room.adjacent_room_ids = sorted(
            other.room_id
            for other in rooms
            if other.room_id != room.room_id and _rooms_are_adjacent(room, other)
        )
        room.is_exterior_touching = _touches_exterior(seed, room)
        if room.category == "unknown":
            room.issues.append("missing_category")
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
    if "HALL" in upper:
        return "hall"
    if "PATIO" in upper:
        return "patio"
    if "GARAGE" in upper:
        return "garage"
    return "unknown"


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


def _touches_exterior(seed: FloorPlanCatalogSeed, room: CatalogRoomTopology, tolerance: float = 3.0) -> bool:
    bbox = seed.footprint_bbox
    return (
        abs(room.bbox.x1 - bbox.x1) <= tolerance
        or abs(room.bbox.y1 - bbox.y1) <= tolerance
        or abs(room.bbox.x2 - bbox.x2) <= tolerance
        or abs(room.bbox.y2 - bbox.y2) <= tolerance
    )
