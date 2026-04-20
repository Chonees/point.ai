from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SiteFitIsolation:
    pipeline: str = "site_fit"
    separate_contracts: bool = True
    touched_existing_parse_generate_pipeline: bool = False


@dataclass(frozen=True)
class SiteFitJob:
    source_kind: str
    payload: dict[str, Any]
    site_constraints: dict[str, Any]
    design_locks: dict[str, Any]
    jurisdiction: str | None = None
    ruleset_version: str = "site_fit_contract_v1"


@dataclass(frozen=True)
class NormalizedPlan:
    source_kind: str
    payload: dict[str, Any]
    canonical_unit: str = "inch"
    room_count: int = 0
    wall_count: int = 0
    opening_count: int = 0
    footprint_bbox: dict[str, float] | None = None


@dataclass(frozen=True)
class RegistrationResult:
    status: str
    canonical_unit: str
    scale_locked: bool = True
    transform: dict[str, float] = field(default_factory=dict)
    registered_plan_bbox: dict[str, float] | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConstraintEvaluation:
    status: str
    checked_rule_ids: tuple[str, ...] = ()
    violations: tuple[dict[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()
    site_summary: dict[str, Any] = field(default_factory=dict)
    registration: RegistrationResult | None = None
