from __future__ import annotations

from .models import ConstraintEvaluation, NormalizedPlan, SiteFitIsolation, RegistrationResult


def build_plan_summary(plan: NormalizedPlan) -> dict:
    return {
        "source_kind": plan.source_kind,
        "canonical_unit": plan.canonical_unit,
        "room_count": plan.room_count,
        "wall_count": plan.wall_count,
        "opening_count": plan.opening_count,
        "footprint_bbox": plan.footprint_bbox,
    }


def build_compliance_summary(evaluation: ConstraintEvaluation) -> dict:
    status = "pass" if evaluation.status == "fit_ready" else "fail"
    if evaluation.status in {"insufficient_site_constraints", "insufficient_plan_geometry"}:
        status = "not_evaluated"
    return {
        "status": status,
        "checked_rule_ids": list(evaluation.checked_rule_ids),
        "violations": [dict(item) for item in evaluation.violations],
        "warnings": list(evaluation.warnings),
    }


def build_registration_summary(registration: RegistrationResult | None) -> dict:
    if registration is None:
        return {
            "status": "not_available",
            "canonical_unit": None,
            "scale_locked": True,
            "transform": _identity_transform(),
        }
    return {
        "status": registration.status,
        "canonical_unit": registration.canonical_unit,
        "scale_locked": registration.scale_locked,
        "transform": dict(registration.transform),
        "registered_plan_bbox": registration.registered_plan_bbox,
        "warnings": list(registration.warnings),
    }


def build_isolation_summary() -> dict:
    isolation = SiteFitIsolation()
    return {
        "pipeline": isolation.pipeline,
        "separate_contracts": isolation.separate_contracts,
        "touched_existing_parse_generate_pipeline": isolation.touched_existing_parse_generate_pipeline,
    }


def _identity_transform() -> dict:
    return {
        "scale": 1.0,
        "rotation_degrees": 0.0,
        "translate_x": 0.0,
        "translate_y": 0.0,
    }
