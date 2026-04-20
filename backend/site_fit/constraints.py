from __future__ import annotations

from .cad_units import normalize_bbox, normalize_polygon, normalize_unit_name
from .models import ConstraintEvaluation, NormalizedPlan, SiteFitJob
from .registration import register_plan_1to1


BUILDABLE_ENVELOPE_RULE_ID = "buildable_envelope.bbox_contains_plan_bbox"
REGISTRATION_SCALE_LOCK_RULE_ID = "registration.scale_locked_1to1"


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
