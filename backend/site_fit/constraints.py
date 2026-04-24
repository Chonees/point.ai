from __future__ import annotations

from .cad_units import normalize_bbox, normalize_polygon, normalize_unit_name
from .models import (
    BoundaryDiagnostic,
    ConstraintEvaluation,
    MutationHint,
    NormalizedBoundarySegment,
    NormalizedOpeningSummary,
    NormalizedPlan,
    NormalizedRoomSummary,
    RoomDiagnostic,
    SiteFitJob,
)
from .registration import register_plan_1to1


BUILDABLE_ENVELOPE_RULE_ID = "buildable_envelope.bbox_contains_plan_bbox"
REGISTRATION_SCALE_LOCK_RULE_ID = "registration.scale_locked_1to1"
SIDE_TO_VECTOR = {
    "west": ("x", 1.0),
    "east": ("x", -1.0),
    "north": ("y", 1.0),
    "south": ("y", -1.0),
}


def evaluate_hard_constraints(plan: NormalizedPlan, job: SiteFitJob) -> ConstraintEvaluation:
    site_summary = _build_site_summary(job)
    registration = register_plan_1to1(plan, job.site_constraints)
    buildable_bbox = _resolve_buildable_bbox(
        job.site_constraints,
        source_unit=_resolve_site_unit(job.site_constraints, fallback=plan.canonical_unit),
        to_unit=registration.canonical_unit if registration is not None else plan.canonical_unit,
    )

    if registration.status == "scale_mismatch":
        return ConstraintEvaluation(
            status="registration_scale_mismatch",
            checked_rule_ids=(REGISTRATION_SCALE_LOCK_RULE_ID,),
            violations=(
                {
                    "rule_id": REGISTRATION_SCALE_LOCK_RULE_ID,
                    "message": "The site placement requires rescaling, but the site-fit pipeline locks registration at 1:1.",
                    "plan_bbox": plan.footprint_bbox,
                    "placed_plan_bbox": registration.registered_plan_bbox,
                },
            ),
            warnings=registration.warnings,
            site_summary=site_summary,
            registration=registration,
        )

    if buildable_bbox is None:
        return ConstraintEvaluation(
            status="insufficient_site_constraints",
            warnings=("No buildable envelope or polygon was provided.",),
            site_summary=site_summary,
            registration=registration,
        )

    if plan.footprint_bbox is None:
        return ConstraintEvaluation(
            status="insufficient_plan_geometry",
            warnings=("Plan footprint could not be derived from the provided payload.",),
            site_summary=site_summary,
            registration=registration,
        )

    plan_bbox_for_fit = registration.registered_plan_bbox or plan.footprint_bbox
    fits = _bbox_fits(inner=plan_bbox_for_fit, outer=buildable_bbox)
    if fits:
        return ConstraintEvaluation(
            status="fit_ready",
            checked_rule_ids=(BUILDABLE_ENVELOPE_RULE_ID,),
            site_summary=site_summary,
            registration=registration,
        )

    overflow_by_side = _overflow_by_side(plan_bbox_for_fit, buildable_bbox)
    rooms_by_id = {room.room_id: room for room in plan.room_summaries}
    openings_by_id = {opening.opening_id: opening for opening in plan.openings}
    locked_room_ids = {str(room_id) for room_id in (job.design_locks.get("locked_rooms") or [])}
    boundary_diagnostics: list[BoundaryDiagnostic] = []
    room_diagnostics: list[RoomDiagnostic] = []
    mutation_hints: list[MutationHint] = []

    if len(overflow_by_side) == 1:
        active_side, overflow_delta = next(iter(overflow_by_side.items()))
        axis, direction = SIDE_TO_VECTOR[active_side]
        registration_transform = (registration.transform if registration is not None else {}) or {}
        translate_x = float(registration_transform.get("translate_x") or 0.0)
        translate_y = float(registration_transform.get("translate_y") or 0.0)
        pending_mutation_hints: list[MutationHint] = []
        has_non_axis_blocker = False
        for boundary in plan.boundary_segments:
            relation = _boundary_relation_for_side(
                boundary,
                side=active_side,
                plan_bbox=plan_bbox_for_fit,
                translate_x=translate_x,
                translate_y=translate_y,
            )
            if relation is None or boundary.boundary_kind != "exterior":
                continue

            blocked_opening, requires_rehost = _opening_block_status(boundary, openings_by_id)
            owner_room_ids = tuple(boundary.owner_room_ids)
            if relation == "touching_non_axis":
                has_non_axis_blocker = True
                boundary_diagnostics.append(
                    BoundaryDiagnostic(
                        boundary_id=boundary.boundary_id,
                        side=active_side,
                        axis=axis,
                        overflow_delta=overflow_delta,
                        status="blocked_non_axis_aligned",
                        reason="boundary is not axis-aligned",
                        owner_room_ids=owner_room_ids,
                        opening_ids=boundary.opening_ids,
                        requires_rehost=requires_rehost,
                    )
                )
                continue
            if boundary.mutability == "protected":
                boundary_diagnostics.append(
                    BoundaryDiagnostic(
                        boundary_id=boundary.boundary_id,
                        side=active_side,
                        axis=axis,
                        overflow_delta=overflow_delta,
                        status="blocked_protected",
                        reason="boundary is protected",
                        owner_room_ids=owner_room_ids,
                        opening_ids=boundary.opening_ids,
                        requires_rehost=requires_rehost,
                    )
                )
                continue
            if boundary.mutability == "locked" or not boundary.movable:
                boundary_diagnostics.append(
                    BoundaryDiagnostic(
                        boundary_id=boundary.boundary_id,
                        side=active_side,
                        axis=axis,
                        overflow_delta=overflow_delta,
                        status="blocked_locked",
                        reason="boundary is locked",
                        owner_room_ids=owner_room_ids,
                        opening_ids=boundary.opening_ids,
                        requires_rehost=requires_rehost,
                    )
                )
                continue
            if blocked_opening:
                boundary_diagnostics.append(
                    BoundaryDiagnostic(
                        boundary_id=boundary.boundary_id,
                        side=active_side,
                        axis=axis,
                        overflow_delta=overflow_delta,
                        status="blocked_non_rehostable_opening",
                        reason="hosted opening cannot be rehosted",
                        owner_room_ids=owner_room_ids,
                        opening_ids=boundary.opening_ids,
                        requires_rehost=requires_rehost,
                    )
                )
                continue

            delta = overflow_delta * direction
            any_blocked = False
            blocked_status = "blocked_room_minimum"
            blocked_reason = "owner room cannot absorb the shrink"
            for room_id in owner_room_ids:
                room = rooms_by_id.get(room_id)
                if room is None:
                    continue

                current_width = float(((room.bbox or {}).get("width")) or 0.0)
                current_height = float(((room.bbox or {}).get("height")) or 0.0)
                blocked, reason, projected = _room_is_blocked(room, axis=axis, delta=delta)
                room_status = "blocked_room_minimum" if blocked else "eligible"
                if room_id in locked_room_ids:
                    room_status = "blocked_design_lock"
                    blocked = True
                    reason = "room is design-locked"
                room_diagnostics.append(
                    RoomDiagnostic(
                        room_id=room.room_id,
                        boundary_id=boundary.boundary_id,
                        axis=axis,
                        current_width=current_width,
                        current_height=current_height,
                        projected_width=projected[0],
                        projected_height=projected[1],
                        projected_area=projected[2],
                        status=room_status,
                        reason=reason,
                    )
                )
                if blocked:
                    any_blocked = True
                    if room_status == "blocked_design_lock":
                        blocked_status = "blocked_design_lock"
                        blocked_reason = "owner room is design-locked"

            if any_blocked:
                boundary_diagnostics.append(
                    BoundaryDiagnostic(
                        boundary_id=boundary.boundary_id,
                        side=active_side,
                        axis=axis,
                        overflow_delta=overflow_delta,
                        status=blocked_status,
                        reason=blocked_reason,
                        owner_room_ids=owner_room_ids,
                        opening_ids=boundary.opening_ids,
                        requires_rehost=requires_rehost,
                    )
                )
                continue

            boundary_diagnostics.append(
                BoundaryDiagnostic(
                    boundary_id=boundary.boundary_id,
                    side=active_side,
                    axis=axis,
                    overflow_delta=overflow_delta,
                    status="eligible",
                    owner_room_ids=owner_room_ids,
                    opening_ids=boundary.opening_ids,
                    requires_rehost=requires_rehost,
                    projected_fit_status="fit_ready",
                )
            )
            pending_mutation_hints.append(
                MutationHint(
                    boundary_id=boundary.boundary_id,
                    side=active_side,
                    axis=axis,
                    delta_x=delta if axis == "x" else 0.0,
                    delta_y=delta if axis == "y" else 0.0,
                    owner_room_ids=owner_room_ids,
                    opening_ids=boundary.opening_ids,
                    requires_rehost=requires_rehost,
                )
            )
        if not has_non_axis_blocker:
            mutation_hints.extend(pending_mutation_hints)

    return ConstraintEvaluation(
        status="buildable_conflict",
        checked_rule_ids=(BUILDABLE_ENVELOPE_RULE_ID,),
        violations=(
            {
                "rule_id": BUILDABLE_ENVELOPE_RULE_ID,
                "message": "The normalized plan footprint exceeds the buildable envelope bbox.",
                "plan_bbox": plan_bbox_for_fit,
                "buildable_bbox": buildable_bbox,
            },
        ),
        site_summary=site_summary,
        registration=registration,
        boundary_diagnostics=tuple(boundary_diagnostics),
        room_diagnostics=tuple(room_diagnostics),
        mutation_hints=tuple(mutation_hints),
    )


def _build_site_summary(job: SiteFitJob) -> dict:
    site_unit = _resolve_site_unit(job.site_constraints, fallback="inch")
    buildable_bbox = _resolve_buildable_bbox(job.site_constraints, source_unit=site_unit, to_unit="inch")
    locked_rooms = job.design_locks.get("locked_rooms") or []
    return {
        "jurisdiction": job.jurisdiction,
        "ruleset_version": job.ruleset_version,
        "site_unit": site_unit,
        "locked_room_count": len(locked_rooms),
        "has_buildable_envelope": buildable_bbox is not None,
        "buildable_bbox": buildable_bbox,
    }


def _resolve_site_unit(site_constraints: dict, *, fallback: str) -> str:
    return normalize_unit_name(site_constraints.get("unit"), fallback=fallback) or fallback


def _resolve_buildable_bbox(site_constraints: dict, *, source_unit: str, to_unit: str) -> dict[str, float] | None:
    envelope = site_constraints.get("buildable_envelope")
    if isinstance(envelope, dict):
        if {"x", "y", "width", "height"} <= set(envelope):
            x = float(envelope["x"])
            y = float(envelope["y"])
            width = float(envelope["width"])
            height = float(envelope["height"])
            bbox = {
                "x1": x,
                "y1": y,
                "x2": x + width,
                "y2": y + height,
                "width": width,
                "height": height,
            }
            return normalize_bbox(bbox, from_unit=source_unit, to_unit=to_unit)
        if {"x1", "y1", "x2", "y2"} <= set(envelope):
            x1 = float(envelope["x1"])
            y1 = float(envelope["y1"])
            x2 = float(envelope["x2"])
            y2 = float(envelope["y2"])
            bbox = {
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "width": x2 - x1,
                "height": y2 - y1,
            }
            return normalize_bbox(bbox, from_unit=source_unit, to_unit=to_unit)

    polygon = site_constraints.get("buildable_polygon") or []
    if polygon:
        normalized_polygon = normalize_polygon(polygon, from_unit=source_unit, to_unit=to_unit)
        xs = [float(point["x"]) for point in normalized_polygon]
        ys = [float(point["y"]) for point in normalized_polygon]
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
    return None


def _bbox_fits(*, inner: dict[str, float], outer: dict[str, float]) -> bool:
    return (
        inner["x1"] >= outer["x1"]
        and inner["y1"] >= outer["y1"]
        and inner["x2"] <= outer["x2"]
        and inner["y2"] <= outer["y2"]
    )


def _overflow_by_side(plan_bbox: dict[str, float], buildable_bbox: dict[str, float]) -> dict[str, float]:
    overflow: dict[str, float] = {}
    if plan_bbox["x1"] < buildable_bbox["x1"]:
        overflow["west"] = buildable_bbox["x1"] - plan_bbox["x1"]
    if plan_bbox["x2"] > buildable_bbox["x2"]:
        overflow["east"] = plan_bbox["x2"] - buildable_bbox["x2"]
    if plan_bbox["y1"] < buildable_bbox["y1"]:
        overflow["north"] = buildable_bbox["y1"] - plan_bbox["y1"]
    if plan_bbox["y2"] > buildable_bbox["y2"]:
        overflow["south"] = plan_bbox["y2"] - buildable_bbox["y2"]
    return overflow


def _boundary_relation_for_side(
    boundary: NormalizedBoundarySegment,
    *,
    side: str,
    plan_bbox: dict[str, float],
    translate_x: float = 0.0,
    translate_y: float = 0.0,
    tolerance: float = 1e-6,
) -> str | None:
    start = _translated_point(boundary.start, translate_x=translate_x, translate_y=translate_y)
    end = _translated_point(boundary.end, translate_x=translate_x, translate_y=translate_y)
    if side == "west":
        return _axis_relation(
            start.get("x", 0.0),
            end.get("x", 0.0),
            start.get("y", 0.0),
            end.get("y", 0.0),
            target=plan_bbox["x1"],
            tolerance=tolerance,
        )
    if side == "east":
        return _axis_relation(
            start.get("x", 0.0),
            end.get("x", 0.0),
            start.get("y", 0.0),
            end.get("y", 0.0),
            target=plan_bbox["x2"],
            tolerance=tolerance,
        )
    if side == "north":
        return _axis_relation(
            start.get("y", 0.0),
            end.get("y", 0.0),
            start.get("x", 0.0),
            end.get("x", 0.0),
            target=plan_bbox["y1"],
            tolerance=tolerance,
        )
    if side == "south":
        return _axis_relation(
            start.get("y", 0.0),
            end.get("y", 0.0),
            start.get("x", 0.0),
            end.get("x", 0.0),
            target=plan_bbox["y2"],
            tolerance=tolerance,
        )
    return None


def _translated_point(
    point: dict[str, float] | None,
    *,
    translate_x: float,
    translate_y: float,
) -> dict[str, float]:
    source = point or {}
    return {
        "x": float(source.get("x", 0.0)) + translate_x,
        "y": float(source.get("y", 0.0)) + translate_y,
    }


def _axis_relation(
    aligned_start: float,
    aligned_end: float,
    cross_start: float,
    cross_end: float,
    *,
    target: float,
    tolerance: float,
) -> str | None:
    if abs(aligned_start - aligned_end) <= tolerance and abs(aligned_start - target) <= tolerance:
        return "aligned"
    if min(aligned_start, aligned_end) <= target + tolerance and max(aligned_start, aligned_end) >= target - tolerance:
        if abs(cross_start - cross_end) > tolerance:
            return "touching_non_axis"
    return None


def _project_room(room: NormalizedRoomSummary, *, axis: str, delta: float) -> tuple[float, float, float]:
    bbox = room.bbox or {}
    current_width = float(bbox.get("width") or 0.0)
    current_height = float(bbox.get("height") or 0.0)
    projected_width = current_width - abs(delta) if axis == "x" else current_width
    projected_height = current_height - abs(delta) if axis == "y" else current_height
    projected_area = projected_width * projected_height
    return projected_width, projected_height, projected_area


def _room_is_blocked(
    room: NormalizedRoomSummary,
    *,
    axis: str,
    delta: float,
) -> tuple[bool, str | None, tuple[float, float, float]]:
    projected_width, projected_height, projected_area = _project_room(room, axis=axis, delta=delta)
    if room.min_width is not None and projected_width < room.min_width:
        return True, "projected width violates room minimum", (projected_width, projected_height, projected_area)
    if room.min_height is not None and projected_height < room.min_height:
        return True, "projected height violates room minimum", (projected_width, projected_height, projected_area)
    if room.min_area is not None and projected_area < room.min_area:
        return True, "projected area violates room minimum", (projected_width, projected_height, projected_area)
    return False, None, (projected_width, projected_height, projected_area)


def _opening_block_status(
    boundary: NormalizedBoundarySegment,
    openings_by_id: dict[str, NormalizedOpeningSummary],
) -> tuple[bool, bool]:
    requires_rehost = False
    for opening_id in boundary.opening_ids:
        opening = openings_by_id.get(opening_id)
        if opening is None:
            continue
        if opening.rehost_required:
            requires_rehost = True
        if opening.rehost_required and not opening.rehostable:
            return True, requires_rehost
    return False, requires_rehost
