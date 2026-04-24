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
class NormalizedRoomSummary:
    room_id: str
    name: str
    category: str
    mutability: str
    min_width: float | None
    min_height: float | None
    min_area: float | None
    bbox: dict[str, float] | None
    owner_boundary_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class NormalizedBoundarySegment:
    boundary_id: str
    boundary_kind: str
    owner_room_ids: tuple[str, ...] = ()
    mutability: str = "unknown"
    movable: bool = False
    constraint_reasons: tuple[str, ...] = ()
    start: dict[str, float] | None = None
    end: dict[str, float] | None = None
    length: float = 0.0
    opening_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class NormalizedWallSegment:
    wall_id: str
    boundary_kind: str
    owner_room_ids: tuple[str, ...] = ()
    mutability: str = "unknown"
    movable: bool = False
    hosted_opening_ids: tuple[str, ...] = ()
    start: dict[str, float] | None = None
    end: dict[str, float] | None = None
    length: float = 0.0


@dataclass(frozen=True)
class NormalizedOpeningSummary:
    opening_id: str
    opening_kind: str
    host_wall_id: str | None = None
    owner_room_ids: tuple[str, ...] = ()
    confidence: str = "unverified"
    rehost_required: bool = False
    rehostable: bool = False
    constraint_reasons: tuple[str, ...] = ()
    offset: float = 0.0
    span: float = 0.0


@dataclass(frozen=True)
class NormalizedPlan:
    source_kind: str
    payload: dict[str, Any]
    canonical_unit: str = "inch"
    room_count: int = 0
    wall_count: int = 0
    opening_count: int = 0
    footprint_bbox: dict[str, float] | None = None
    room_summaries: tuple[NormalizedRoomSummary, ...] = ()
    boundary_segments: tuple[NormalizedBoundarySegment, ...] = ()
    wall_segments: tuple[NormalizedWallSegment, ...] = ()
    openings: tuple[NormalizedOpeningSummary, ...] = ()
    movable_boundary_count: int = 0
    protected_boundary_count: int = 0
    locked_boundary_count: int = 0
    rehostable_opening_count: int = 0


@dataclass(frozen=True)
class RegistrationResult:
    status: str
    canonical_unit: str
    scale_locked: bool = True
    transform: dict[str, float] = field(default_factory=dict)
    registered_plan_bbox: dict[str, float] | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class BoundaryDiagnostic:
    boundary_id: str
    side: str
    axis: str
    overflow_delta: float
    status: str
    reason: str | None = None
    owner_room_ids: tuple[str, ...] = ()
    opening_ids: tuple[str, ...] = ()
    requires_rehost: bool = False
    projected_fit_status: str = "unknown"


@dataclass(frozen=True)
class RoomDiagnostic:
    room_id: str
    boundary_id: str
    axis: str
    current_width: float
    current_height: float
    projected_width: float
    projected_height: float
    projected_area: float
    status: str
    reason: str | None = None


@dataclass(frozen=True)
class MutationHint:
    boundary_id: str
    side: str
    axis: str
    delta_x: float = 0.0
    delta_y: float = 0.0
    owner_room_ids: tuple[str, ...] = ()
    opening_ids: tuple[str, ...] = ()
    requires_rehost: bool = False
    strategy: str = "shrink_boundary"


@dataclass(frozen=True)
class ConstraintEvaluation:
    status: str
    checked_rule_ids: tuple[str, ...] = ()
    violations: tuple[dict[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()
    site_summary: dict[str, Any] = field(default_factory=dict)
    registration: RegistrationResult | None = None
    boundary_diagnostics: tuple[BoundaryDiagnostic, ...] = ()
    room_diagnostics: tuple[RoomDiagnostic, ...] = ()
    mutation_hints: tuple[MutationHint, ...] = ()
