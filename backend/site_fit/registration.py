from __future__ import annotations

from .cad_units import canonical_internal_unit, normalize_bbox, normalize_unit_name
from .models import NormalizedPlan, RegistrationResult


REGISTRATION_EPSILON = 1e-6


def register_plan_1to1(plan: NormalizedPlan, site_constraints: dict) -> RegistrationResult:
    canonical_unit = _resolve_canonical_unit(plan, site_constraints)

    if plan.footprint_bbox is None:
        return RegistrationResult(
            status="missing_plan_bbox",
            canonical_unit=canonical_unit,
            transform=_identity_transform(),
            warnings=("Plan footprint could not be derived for 1:1 registration.",),
        )

    site_unit = _resolve_site_unit(site_constraints, fallback=plan.canonical_unit)
    placed_bbox = _resolve_bbox(site_constraints.get("placed_plan_footprint"), source_unit=site_unit, to_unit=canonical_unit)
    if placed_bbox is None:
        return RegistrationResult(
            status="plan_bbox_only",
            canonical_unit=canonical_unit,
            transform=_identity_transform(),
            registered_plan_bbox=dict(plan.footprint_bbox),
        )

    width_matches = _matches(plan.footprint_bbox["width"], placed_bbox["width"])
    height_matches = _matches(plan.footprint_bbox["height"], placed_bbox["height"])
    if not (width_matches and height_matches):
        return RegistrationResult(
            status="scale_mismatch",
            canonical_unit=canonical_unit,
            transform=_identity_transform(),
            registered_plan_bbox=placed_bbox,
            warnings=("Placed site footprint requires rescaling, but scale is locked at 1:1.",),
        )

    return RegistrationResult(
        status="registered_1to1",
        canonical_unit=canonical_unit,
        transform={
            "scale": 1.0,
            "rotation_degrees": 0.0,
            "translate_x": float(placed_bbox["x1"] - plan.footprint_bbox["x1"]),
            "translate_y": float(placed_bbox["y1"] - plan.footprint_bbox["y1"]),
        },
        registered_plan_bbox=placed_bbox,
    )


def _resolve_canonical_unit(plan: NormalizedPlan, site_constraints: dict) -> str:
    site_unit = _resolve_site_unit(site_constraints, fallback=plan.canonical_unit)
    if plan.canonical_unit == "inch" or site_unit == "inch":
        return "inch"
    return canonical_internal_unit(site_unit, fallback=plan.canonical_unit)


def _resolve_site_unit(site_constraints: dict, *, fallback: str) -> str:
    return normalize_unit_name(site_constraints.get("unit"), fallback=fallback) or fallback


def _resolve_bbox(raw: dict | None, *, source_unit: str, to_unit: str) -> dict[str, float] | None:
    if not isinstance(raw, dict):
        return None
    if {"x", "y", "width", "height"} <= set(raw):
        x = float(raw["x"])
        y = float(raw["y"])
        width = float(raw["width"])
        height = float(raw["height"])
        bbox = {
            "x1": x,
            "y1": y,
            "x2": x + width,
            "y2": y + height,
            "width": width,
            "height": height,
        }
        return normalize_bbox(bbox, from_unit=source_unit, to_unit=to_unit)
    if {"x1", "y1", "x2", "y2"} <= set(raw):
        x1 = float(raw["x1"])
        y1 = float(raw["y1"])
        x2 = float(raw["x2"])
        y2 = float(raw["y2"])
        bbox = {
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "width": x2 - x1,
            "height": y2 - y1,
        }
        return normalize_bbox(bbox, from_unit=source_unit, to_unit=to_unit)
    return None


def _matches(left: float, right: float) -> bool:
    return abs(float(left) - float(right)) <= REGISTRATION_EPSILON


def _identity_transform() -> dict[str, float]:
    return {
        "scale": 1.0,
        "rotation_degrees": 0.0,
        "translate_x": 0.0,
        "translate_y": 0.0,
    }
