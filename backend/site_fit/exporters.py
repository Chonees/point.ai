from __future__ import annotations

from copy import deepcopy

from .models import SiteFitIsolation, SiteFitJob


def _move_point(point: dict | None, *, delta_x: float, delta_y: float) -> dict | None:
    if not isinstance(point, dict):
        return point
    return {
        **point,
        "x": float(point.get("x", 0.0)) + delta_x,
        "y": float(point.get("y", 0.0)) + delta_y,
    }


def _segment_matches_side(segment: dict, *, active_side: str, footprint_bbox: dict, tolerance: float = 1e-6) -> bool:
    start = segment.get("start") or {}
    end = segment.get("end") or {}
    if active_side in {"east", "west"}:
        if abs(float(start.get("x", 0.0)) - float(end.get("x", 0.0))) > tolerance:
            return False
        target_x = float(footprint_bbox["x2"] if active_side == "east" else footprint_bbox["x1"])
        return abs(float(start.get("x", 0.0)) - target_x) <= tolerance
    if abs(float(start.get("y", 0.0)) - float(end.get("y", 0.0))) > tolerance:
        return False
    target_y = float(footprint_bbox["y2"] if active_side == "south" else footprint_bbox["y1"])
    return abs(float(start.get("y", 0.0)) - target_y) <= tolerance


def _apply_boundary_shrink(payload: dict, *, change: dict) -> dict:
    applied = deepcopy(payload)
    delta_x = float(change.get("delta_x") or 0.0)
    delta_y = float(change.get("delta_y") or 0.0)
    boundary_id = change["boundary_id"]
    owner_room_ids = set(change.get("owner_room_ids") or [])
    opening_ids = set(change.get("opening_ids") or [])
    footprint_bbox = deepcopy(applied.get("footprint_bbox") or {})
    active_side = str(change.get("side") or "")

    for boundary in applied.get("boundaries") or []:
        if boundary.get("boundary_id") != boundary_id:
            continue
        boundary["start"] = _move_point(boundary.get("start"), delta_x=delta_x, delta_y=delta_y)
        boundary["end"] = _move_point(boundary.get("end"), delta_x=delta_x, delta_y=delta_y)

    for wall in applied.get("walls") or []:
        hosted_opening_ids = set(wall.get("hosted_opening_ids") or [])
        if hosted_opening_ids & opening_ids or (
            active_side
            and wall.get("boundary_kind") == "exterior"
            and set(wall.get("owner_room_ids") or []) & owner_room_ids
            and footprint_bbox
            and _segment_matches_side(wall, active_side=active_side, footprint_bbox=footprint_bbox)
        ):
            wall["start"] = _move_point(wall.get("start"), delta_x=delta_x, delta_y=delta_y)
            wall["end"] = _move_point(wall.get("end"), delta_x=delta_x, delta_y=delta_y)

    for opening in applied.get("openings") or []:
        if opening.get("opening_id") in opening_ids:
            opening["start"] = _move_point(opening.get("start"), delta_x=delta_x, delta_y=delta_y)
            opening["end"] = _move_point(opening.get("end"), delta_x=delta_x, delta_y=delta_y)

    for room in applied.get("rooms") or []:
        if room.get("room_id") not in owner_room_ids:
            continue
        bbox = deepcopy(room.get("bbox") or {})
        if delta_x < 0:
            bbox["x2"] = float(bbox.get("x2", 0.0)) + delta_x
        elif delta_x > 0:
            bbox["x1"] = float(bbox.get("x1", 0.0)) + delta_x
        if delta_y < 0:
            bbox["y2"] = float(bbox.get("y2", 0.0)) + delta_y
        elif delta_y > 0:
            bbox["y1"] = float(bbox.get("y1", 0.0)) + delta_y
        bbox["width"] = float(bbox.get("x2", 0.0)) - float(bbox.get("x1", 0.0))
        bbox["height"] = float(bbox.get("y2", 0.0)) - float(bbox.get("y1", 0.0))
        room["bbox"] = bbox

    if footprint_bbox:
        if delta_x < 0:
            footprint_bbox["x2"] = float(footprint_bbox.get("x2", 0.0)) + delta_x
        elif delta_x > 0:
            footprint_bbox["x1"] = float(footprint_bbox.get("x1", 0.0)) + delta_x
        if delta_y < 0:
            footprint_bbox["y2"] = float(footprint_bbox.get("y2", 0.0)) + delta_y
        elif delta_y > 0:
            footprint_bbox["y1"] = float(footprint_bbox.get("y1", 0.0)) + delta_y
        footprint_bbox["width"] = float(footprint_bbox.get("x2", 0.0)) - float(footprint_bbox.get("x1", 0.0))
        footprint_bbox["height"] = float(footprint_bbox.get("y2", 0.0)) - float(footprint_bbox.get("y1", 0.0))
        applied["footprint_bbox"] = footprint_bbox

    return applied


def export_applied_plan(job: SiteFitJob, *, candidate_id: str, change_set: list[dict] | None = None) -> dict:
    payload = deepcopy(job.payload)
    if candidate_id.startswith("shrink_boundary::") and change_set:
        payload = _apply_boundary_shrink(payload, change=change_set[0])
    return {
        job.source_kind: payload,
        "site_fit_meta": {
            "pipeline": SiteFitIsolation().pipeline,
            "candidate_id": candidate_id,
            "ruleset_version": job.ruleset_version,
        },
    }

