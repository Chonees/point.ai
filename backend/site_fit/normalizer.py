from __future__ import annotations

from .cad_units import canonical_internal_unit, normalize_bbox, normalize_unit_name
from .models import NormalizedPlan, SiteFitJob


def normalize_plan(job: SiteFitJob) -> NormalizedPlan:
    if job.source_kind == "plan":
        rooms = job.payload.get("rooms") or []
        source_unit = _resolve_plan_source_unit(job.payload)
        raw_bbox = _bbox_from_plan_rooms(rooms)
        return NormalizedPlan(
            source_kind="plan",
            payload=job.payload,
            canonical_unit=canonical_internal_unit(source_unit, fallback="inch"),
            room_count=len(rooms),
            wall_count=0,
            opening_count=0,
            footprint_bbox=normalize_bbox(raw_bbox, from_unit=source_unit, to_unit="inch")
            if canonical_internal_unit(source_unit, fallback="inch") == "inch"
            else raw_bbox,
        )

    walls = job.payload.get("walls") or []
    openings = job.payload.get("openings") or []
    source_unit = _resolve_structure_source_unit(job.payload)
    raw_bbox = _bbox_from_structure_walls(walls)
    return NormalizedPlan(
        source_kind="structure",
        payload=job.payload,
        canonical_unit=canonical_internal_unit(source_unit, fallback="pixel"),
        room_count=0,
        wall_count=len(walls),
        opening_count=len(openings),
        footprint_bbox=normalize_bbox(raw_bbox, from_unit=source_unit, to_unit="inch")
        if canonical_internal_unit(source_unit, fallback="pixel") == "inch"
        else raw_bbox,
    )


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


def _resolve_plan_source_unit(payload: dict) -> str:
    unit = payload.get("unit")
    return normalize_unit_name(unit, fallback="inch") or "inch"


def _resolve_structure_source_unit(payload: dict) -> str:
    unit = payload.get("unit")
    if not unit:
        unit = (payload.get("structure_meta") or {}).get("unit")
    return normalize_unit_name(unit, fallback="pixel") or "pixel"
