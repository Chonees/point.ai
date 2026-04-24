from __future__ import annotations

from .cad_units import canonical_internal_unit, convert_value, normalize_bbox, normalize_unit_name
from .models import (
    NormalizedBoundarySegment,
    NormalizedOpeningSummary,
    NormalizedPlan,
    NormalizedRoomSummary,
    NormalizedWallSegment,
    SiteFitJob,
)


def normalize_plan(job: SiteFitJob) -> NormalizedPlan:
    if job.source_kind == "plan":
        rooms = job.payload.get("rooms") or []
        source_unit = _resolve_plan_source_unit(job.payload)
        canonical_unit = canonical_internal_unit(source_unit, fallback="inch")

        if _is_catalog_plan_payload(job.payload):
            boundaries = job.payload.get("boundaries") or []
            retained_boundaries = _retained_catalog_boundaries(boundaries)
            openings_payload = job.payload.get("openings") or []
            boundary_segments = _normalize_boundary_segments(
                retained_boundaries,
                source_unit=source_unit,
                canonical_unit=canonical_unit,
            )
            room_summaries = _normalize_room_summaries(
                rooms,
                retained_boundaries,
                source_unit=source_unit,
                canonical_unit=canonical_unit,
            )
            wall_segments = _normalize_wall_segments(
                job.payload.get("walls") or [],
                openings_payload,
                source_unit=source_unit,
                canonical_unit=canonical_unit,
            )
            openings = _normalize_openings(
                openings_payload,
                source_unit=source_unit,
                canonical_unit=canonical_unit,
            )
            raw_bbox = job.payload.get("footprint_bbox")
            if raw_bbox is not None:
                footprint_bbox = _normalize_bbox_if_needed(
                    raw_bbox,
                    source_unit=source_unit,
                    canonical_unit=canonical_unit,
                )
            else:
                footprint_bbox = _bbox_from_catalog_boundaries(boundary_segments)
            return NormalizedPlan(
                source_kind="plan",
                payload=_sanitize_catalog_payload(job.payload),
                canonical_unit=canonical_unit,
                room_count=len(room_summaries),
                wall_count=len(wall_segments),
                opening_count=len(openings),
                footprint_bbox=footprint_bbox,
                room_summaries=room_summaries,
                boundary_segments=boundary_segments,
                wall_segments=wall_segments,
                openings=openings,
                movable_boundary_count=sum(1 for item in boundary_segments if item.mutability == "movable"),
                protected_boundary_count=sum(1 for item in boundary_segments if item.mutability == "protected"),
                locked_boundary_count=sum(1 for item in boundary_segments if item.mutability == "locked"),
                rehostable_opening_count=sum(1 for item in openings if item.rehostable),
            )

        raw_bbox = _bbox_from_plan_rooms(rooms)
        return NormalizedPlan(
            source_kind="plan",
            payload=job.payload,
            canonical_unit=canonical_unit,
            room_count=len(rooms),
            wall_count=0,
            opening_count=0,
            footprint_bbox=_normalize_bbox_if_needed(raw_bbox, source_unit=source_unit, canonical_unit=canonical_unit),
        )

    walls = job.payload.get("walls") or []
    openings = job.payload.get("openings") or []
    source_unit = _resolve_structure_source_unit(job.payload)
    canonical_unit = canonical_internal_unit(source_unit, fallback="pixel")
    raw_bbox = _bbox_from_structure_walls(walls)
    return NormalizedPlan(
        source_kind="structure",
        payload=job.payload,
        canonical_unit=canonical_unit,
        room_count=0,
        wall_count=len(walls),
        opening_count=len(openings),
        footprint_bbox=_normalize_bbox_if_needed(raw_bbox, source_unit=source_unit, canonical_unit=canonical_unit),
    )


def _is_catalog_plan_payload(payload: dict) -> bool:
    rooms = payload.get("rooms") or []
    boundaries = payload.get("boundaries") or []
    walls = payload.get("walls") or []
    openings = payload.get("openings") or []
    boundary_nodes = payload.get("boundary_nodes") or []

    has_catalog_boundaries = any(isinstance(boundary, dict) and boundary.get("boundary_id") for boundary in boundaries)
    if not has_catalog_boundaries:
        return False

    if not rooms:
        return bool(walls or openings or boundary_nodes)

    return any(isinstance(room, dict) and "room_id" in room for room in rooms)


def _retained_catalog_boundaries(boundaries: list[dict]) -> list[dict]:
    return [
        boundary
        for boundary in boundaries
        if boundary.get("boundary_kind") not in {"duplicate", "artifact"}
    ]


def _sanitize_catalog_payload(payload: dict) -> dict:
    sanitized = dict(payload)
    sanitized.pop("cad_traces", None)
    sanitized.pop("boundary_nodes", None)
    return sanitized


def _normalize_room_summaries(
    rooms: list[dict],
    boundaries: list[dict],
    *,
    source_unit: str | None,
    canonical_unit: str,
) -> tuple[NormalizedRoomSummary, ...]:
    room_boundaries: dict[str, list[str]] = {}
    for boundary in boundaries:
        boundary_id = boundary.get("boundary_id")
        if boundary_id is None:
            continue
        for room_id in boundary.get("owner_room_ids") or []:
            room_boundaries.setdefault(str(room_id), []).append(str(boundary_id))

    return tuple(
        NormalizedRoomSummary(
            room_id=str(room["room_id"]),
            name=str(room.get("name") or room["room_id"]),
            category=str(room.get("category") or "unknown"),
            mutability=str(room.get("mutability") or "unknown"),
            min_width=_optional_float(room.get("min_width"), source_unit=source_unit, canonical_unit=canonical_unit),
            min_height=_optional_float(room.get("min_height"), source_unit=source_unit, canonical_unit=canonical_unit),
            min_area=_optional_float(room.get("min_area"), source_unit=source_unit, canonical_unit=canonical_unit, square=True),
            bbox=_normalize_catalog_bbox(room.get("bbox"), source_unit=source_unit, canonical_unit=canonical_unit),
            owner_boundary_ids=tuple(room_boundaries.get(str(room["room_id"]), [])),
        )
        for room in rooms
    )


def _normalize_boundary_segments(
    boundaries: list[dict],
    *,
    source_unit: str | None,
    canonical_unit: str,
) -> tuple[NormalizedBoundarySegment, ...]:
    return tuple(
        NormalizedBoundarySegment(
            boundary_id=str(boundary["boundary_id"]),
            boundary_kind=str(boundary.get("boundary_kind") or "unknown"),
            owner_room_ids=tuple(str(room_id) for room_id in (boundary.get("owner_room_ids") or [])),
            mutability=str(boundary.get("mutability") or "unknown"),
            movable=bool(boundary.get("movable")),
            constraint_reasons=tuple(str(reason) for reason in (boundary.get("constraint_reasons") or [])),
            start=_point_dict(boundary.get("start"), source_unit=source_unit, canonical_unit=canonical_unit),
            end=_point_dict(boundary.get("end"), source_unit=source_unit, canonical_unit=canonical_unit),
            length=_optional_float(boundary.get("length"), source_unit=source_unit, canonical_unit=canonical_unit) or 0.0,
            opening_ids=tuple(str(opening_id) for opening_id in (boundary.get("opening_ids") or [])),
        )
        for boundary in boundaries
    )


def _normalize_wall_segments(
    walls: list[dict],
    openings: list[dict],
    *,
    source_unit: str | None,
    canonical_unit: str,
) -> tuple[NormalizedWallSegment, ...]:
    opening_ids_by_wall: dict[str, list[str]] = {}
    for opening in openings:
        host_wall_id = opening.get("host_wall_id")
        opening_id = opening.get("opening_id")
        if host_wall_id and opening_id:
            opening_ids_by_wall.setdefault(str(host_wall_id), []).append(str(opening_id))

    normalized_walls: list[NormalizedWallSegment] = []
    for wall in walls:
        wall_id = str(wall["wall_id"])
        hosted_opening_ids = list(str(item) for item in (wall.get("hosted_opening_ids") or []))
        for opening_id in opening_ids_by_wall.get(wall_id, []):
            if opening_id not in hosted_opening_ids:
                hosted_opening_ids.append(opening_id)
        normalized_walls.append(
            NormalizedWallSegment(
                wall_id=wall_id,
                boundary_kind=str(wall.get("boundary_kind") or "unknown"),
                owner_room_ids=tuple(str(room_id) for room_id in (wall.get("owner_room_ids") or [])),
                mutability=str(wall.get("mutability") or "unknown"),
                movable=bool(wall.get("movable")),
                hosted_opening_ids=tuple(hosted_opening_ids),
                start=_point_dict(wall.get("start"), source_unit=source_unit, canonical_unit=canonical_unit),
                end=_point_dict(wall.get("end"), source_unit=source_unit, canonical_unit=canonical_unit),
                length=_optional_float(wall.get("length"), source_unit=source_unit, canonical_unit=canonical_unit) or 0.0,
            )
        )
    return tuple(normalized_walls)


def _normalize_openings(
    openings: list[dict],
    *,
    source_unit: str | None,
    canonical_unit: str,
) -> tuple[NormalizedOpeningSummary, ...]:
    return tuple(
        NormalizedOpeningSummary(
            opening_id=str(opening["opening_id"]),
            opening_kind=str(opening.get("opening_kind") or "unknown"),
            host_wall_id=str(opening["host_wall_id"]) if opening.get("host_wall_id") is not None else None,
            owner_room_ids=tuple(str(room_id) for room_id in (opening.get("owner_room_ids") or [])),
            confidence=str(opening.get("confidence") or "unverified"),
            rehost_required=bool(opening.get("rehost_required")),
            rehostable=bool(opening.get("rehostable")),
            constraint_reasons=tuple(str(reason) for reason in (opening.get("constraint_reasons") or [])),
            offset=_optional_float(opening.get("offset"), source_unit=source_unit, canonical_unit=canonical_unit) or 0.0,
            span=_optional_float(opening.get("span"), source_unit=source_unit, canonical_unit=canonical_unit) or 0.0,
        )
        for opening in openings
    )


def _normalize_catalog_bbox(
    bbox: dict | None,
    *,
    source_unit: str | None,
    canonical_unit: str,
) -> dict[str, float] | None:
    if not isinstance(bbox, dict):
        return None
    raw_bbox = {
        "x1": float(bbox.get("x1", 0.0)),
        "y1": float(bbox.get("y1", 0.0)),
        "x2": float(bbox.get("x2", 0.0)),
        "y2": float(bbox.get("y2", 0.0)),
        "width": float(bbox.get("width", 0.0)),
        "height": float(bbox.get("height", 0.0)),
    }
    return _normalize_bbox_if_needed(raw_bbox, source_unit=source_unit, canonical_unit=canonical_unit)


def _point_dict(
    point: dict | None,
    *,
    source_unit: str | None,
    canonical_unit: str,
) -> dict[str, float] | None:
    if not isinstance(point, dict):
        return None
    return {
        "x": _convert_linear_value(point.get("x", 0.0), source_unit=source_unit, canonical_unit=canonical_unit),
        "y": _convert_linear_value(point.get("y", 0.0), source_unit=source_unit, canonical_unit=canonical_unit),
    }


def _bbox_from_plan_rooms(rooms: list[dict]) -> dict[str, float] | None:
    if not rooms:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for room in rooms:
        x = float(room.get("x", 0.0))
        y = float(room.get("y", 0.0))
        w = float(room.get("w", 0.0))
        h = float(room.get("h", 0.0))
        xs.extend((x, x + w))
        ys.extend((y, y + h))
    return _bbox_from_ranges(xs, ys)


def _bbox_from_catalog_boundaries(boundaries: tuple[NormalizedBoundarySegment, ...]) -> dict[str, float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for boundary in boundaries:
        if boundary.start is not None:
            xs.append(boundary.start["x"])
            ys.append(boundary.start["y"])
        if boundary.end is not None:
            xs.append(boundary.end["x"])
            ys.append(boundary.end["y"])
    return _bbox_from_ranges(xs, ys)


def _bbox_from_structure_walls(walls: list[dict]) -> dict[str, float] | None:
    if not walls:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for wall in walls:
        xs.extend((float(wall.get("x1", 0.0)), float(wall.get("x2", 0.0))))
        ys.extend((float(wall.get("y1", 0.0)), float(wall.get("y2", 0.0))))
    return _bbox_from_ranges(xs, ys)


def _bbox_from_ranges(xs: list[float], ys: list[float]) -> dict[str, float] | None:
    if not xs or not ys:
        return None
    x1 = min(xs)
    y1 = min(ys)
    x2 = max(xs)
    y2 = max(ys)
    return {
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "width": x2 - x1,
        "height": y2 - y1,
    }


def _normalize_bbox_if_needed(
    raw_bbox: dict[str, float] | None,
    *,
    source_unit: str | None,
    canonical_unit: str,
) -> dict[str, float] | None:
    if canonical_unit == "inch":
        return normalize_bbox(raw_bbox, from_unit=source_unit, to_unit="inch")
    return raw_bbox


def _optional_float(
    value: object,
    *,
    source_unit: str | None,
    canonical_unit: str,
    square: bool = False,
) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if canonical_unit != "inch" or source_unit is None:
        return numeric
    if square:
        factor = convert_value(1.0, from_unit=source_unit, to_unit="inch")
        return numeric * factor * factor
    return convert_value(numeric, from_unit=source_unit, to_unit="inch")


def _convert_linear_value(value: object, *, source_unit: str | None, canonical_unit: str) -> float:
    numeric = float(value)
    if canonical_unit != "inch":
        return numeric
    return convert_value(numeric, from_unit=source_unit, to_unit="inch")


def _resolve_plan_source_unit(payload: dict) -> str:
    unit = payload.get("unit")
    if not unit:
        unit = (payload.get("structure_meta") or {}).get("unit")
    return normalize_unit_name(unit, fallback="inch") or "inch"


def _resolve_structure_source_unit(payload: dict) -> str:
    unit = payload.get("unit")
    if not unit:
        unit = (payload.get("structure_meta") or {}).get("unit")
    return normalize_unit_name(unit, fallback="pixel") or "pixel"
