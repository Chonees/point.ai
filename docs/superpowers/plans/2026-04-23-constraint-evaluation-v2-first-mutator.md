# Constraint Evaluation v2 + First Thin Mutator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add boundary-aware `site_fit` constraint diagnostics plus a first real shrink mutator for rich plan payloads with single-side overflow.

**Architecture:** Keep `NormalizedPlan v2` as the canonical site-fit input, enrich `ConstraintEvaluation` with boundary / room / mutation facts, and let the solver build one thin candidate per eligible mutation hint. The mutator stays intentionally narrow: only rich `plan` payloads, only single-side overflow, only axis-aligned exterior movable boundaries, and only when room minimums and opening rehostability allow the shrink.

**Tech Stack:** Python, FastAPI, dataclasses, pytest

---

## File map

- Create: `tests/test_site_fit_constraints.py` — unit coverage for boundary diagnostics, room minimum blocking, opening rehost gating, and mutation hints.
- Modify: `tests/test_site_fit_api.py` — API regression for propose/apply on rich overflow payloads.
- Modify: `backend/site_fit/models.py` — add diagnostic + hint dataclasses to `ConstraintEvaluation`.
- Modify: `backend/site_fit/contracts.py` — expose diagnostics and hints through `SiteFitComplianceSummaryResponse`.
- Modify: `backend/site_fit/reporter.py` — serialize diagnostics/hints into API-safe dicts.
- Modify: `backend/site_fit/constraints.py` — implement Constraint Evaluation v2.
- Modify: `backend/site_fit/validator.py` — keep passing through the richer evaluation object.
- Modify: `backend/site_fit/mutators.py` — create shrink-boundary candidate builder.
- Modify: `backend/site_fit/solver.py` — emit mutation candidates from eligible hints.
- Modify: `backend/site_fit/exporters.py` — apply a shrink candidate to the copied rich plan payload.
- Modify: `backend/services/site_fit_service.py` — allow applying a generated shrink candidate.

### Task 1: Add RED unit coverage for evaluator diagnostics and mutation hints

**Files:**
- Create: `tests/test_site_fit_constraints.py`
- Read: `backend/site_fit/constraints.py`
- Read: `backend/site_fit/intake.py`
- Read: `backend/site_fit/normalizer.py`

- [ ] **Step 1: Write failing evaluator tests for eligible, minimum-blocked, and opening-blocked boundaries**

```python
from backend.site_fit.constraints import evaluate_hard_constraints
from backend.site_fit.intake import build_site_fit_job
from backend.site_fit.normalizer import normalize_plan


def _rich_plan(*, boundary_mutability="movable", opening_rehostable=True, room_min_width=60):
    return {
        "model": "Rich Overflow Sample",
        "unit": "inch",
        "rooms": [
            {
                "room_id": "room-1",
                "name": "LIVING",
                "category": "living_room",
                "mutability": "flexible",
                "min_width": room_min_width,
                "min_height": 40,
                "min_area": 2400,
                "bbox": {"x1": 0, "y1": 0, "x2": 120, "y2": 80, "width": 120, "height": 80},
            }
        ],
        "boundaries": [
            {
                "boundary_id": "west-boundary",
                "boundary_kind": "exterior",
                "owner_room_ids": ["room-1"],
                "mutability": "protected",
                "movable": False,
                "constraint_reasons": [],
                "start": {"x": 0, "y": 0},
                "end": {"x": 0, "y": 80},
                "length": 80,
                "opening_ids": [],
            },
            {
                "boundary_id": "east-boundary",
                "boundary_kind": "exterior",
                "owner_room_ids": ["room-1"],
                "mutability": boundary_mutability,
                "movable": boundary_mutability in {"movable", "movable_with_rehost"},
                "constraint_reasons": [],
                "start": {"x": 120, "y": 0},
                "end": {"x": 120, "y": 80},
                "length": 80,
                "opening_ids": ["opening-1"],
            },
        ],
        "walls": [
            {
                "wall_id": "wall-east",
                "boundary_kind": "exterior",
                "owner_room_ids": ["room-1"],
                "mutability": boundary_mutability,
                "movable": boundary_mutability in {"movable", "movable_with_rehost"},
                "start": {"x": 120, "y": 0},
                "end": {"x": 120, "y": 80},
                "length": 80,
                "hosted_opening_ids": ["opening-1"],
            }
        ],
        "openings": [
            {
                "opening_id": "opening-1",
                "opening_kind": "window",
                "host_wall_id": "wall-east",
                "owner_room_ids": ["room-1"],
                "confidence": "hosted",
                "rehost_required": True,
                "rehostable": opening_rehostable,
                "constraint_reasons": [],
                "offset": 20,
                "span": 20,
                "start": {"x": 120, "y": 20},
                "end": {"x": 120, "y": 40},
            }
        ],
        "footprint_bbox": {"x1": 0, "y1": 0, "x2": 120, "y2": 80, "width": 120, "height": 80},
    }


def _evaluate(*, boundary_mutability="movable", opening_rehostable=True, room_min_width=60, locked_rooms=None):
    job = build_site_fit_job(
        plan=_rich_plan(
            boundary_mutability=boundary_mutability,
            opening_rehostable=opening_rehostable,
            room_min_width=room_min_width,
        ),
        structure=None,
        site_constraints={"buildable_envelope": {"x": 0, "y": 0, "width": 100, "height": 80}},
        design_locks={"locked_rooms": locked_rooms or []},
        jurisdiction=None,
        ruleset_version="site_fit_contract_v1",
    )
    normalized = normalize_plan(job)
    return evaluate_hard_constraints(normalized, job)


def test_evaluate_hard_constraints_marks_single_side_overflow_boundary_as_eligible():
    evaluation = _evaluate(boundary_mutability="movable_with_rehost", opening_rehostable=True)

    assert evaluation.status == "buildable_conflict"
    assert len(evaluation.boundary_diagnostics) == 1
    assert evaluation.boundary_diagnostics[0].boundary_id == "east-boundary"
    assert evaluation.boundary_diagnostics[0].status == "eligible"
    assert evaluation.boundary_diagnostics[0].overflow_delta == 20.0
    assert evaluation.boundary_diagnostics[0].requires_rehost is True
    assert len(evaluation.mutation_hints) == 1
    assert evaluation.mutation_hints[0].boundary_id == "east-boundary"
    assert evaluation.mutation_hints[0].delta_x == -20.0
    assert evaluation.mutation_hints[0].delta_y == 0.0


def test_evaluate_hard_constraints_blocks_boundary_when_room_minimum_would_break():
    evaluation = _evaluate(boundary_mutability="movable", opening_rehostable=True, room_min_width=110)

    assert evaluation.status == "buildable_conflict"
    assert evaluation.boundary_diagnostics[0].status == "blocked_room_minimum"
    assert evaluation.room_diagnostics[0].status == "blocked_room_minimum"
    assert evaluation.mutation_hints == ()


def test_evaluate_hard_constraints_blocks_boundary_with_non_rehostable_opening():
    evaluation = _evaluate(boundary_mutability="movable_with_rehost", opening_rehostable=False)

    assert evaluation.status == "buildable_conflict"
    assert evaluation.boundary_diagnostics[0].status == "blocked_non_rehostable_opening"
    assert evaluation.boundary_diagnostics[0].requires_rehost is True
    assert evaluation.mutation_hints == ()
```

- [ ] **Step 2: Run the new constraints tests to verify RED**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_site_fit_constraints.py -q
```

Expected: FAIL because `ConstraintEvaluation` does not yet expose `boundary_diagnostics`, `room_diagnostics`, or `mutation_hints`, and the evaluator still reasons only over bbox fit.

- [ ] **Step 3: Commit the RED evaluator tests**

```powershell
git add tests/test_site_fit_constraints.py
git commit -m "test: cover site fit constraint evaluation v2"
```

### Task 2: Add RED API coverage for propose/apply on the first thin mutator

**Files:**
- Modify: `tests/test_site_fit_api.py`
- Read: `backend/services/site_fit_service.py`
- Read: `backend/site_fit/solver.py`
- Read: `backend/site_fit/exporters.py`

- [ ] **Step 1: Add failing propose/apply API tests for a shrink candidate**

Append these tests to `tests/test_site_fit_api.py`:

```python
RICH_OVERFLOW_PLAN = {
    "model": "Rich Overflow Sample",
    "unit": "inch",
    "rooms": [
        {
            "room_id": "room-1",
            "name": "LIVING",
            "category": "living_room",
            "mutability": "flexible",
            "min_width": 60,
            "min_height": 40,
            "min_area": 2400,
            "bbox": {"x1": 0, "y1": 0, "x2": 120, "y2": 80, "width": 120, "height": 80},
        }
    ],
    "boundaries": [
        {
            "boundary_id": "west-boundary",
            "boundary_kind": "exterior",
            "owner_room_ids": ["room-1"],
            "mutability": "protected",
            "movable": False,
            "constraint_reasons": [],
            "start": {"x": 0, "y": 0},
            "end": {"x": 0, "y": 80},
            "length": 80,
            "opening_ids": [],
        },
        {
            "boundary_id": "east-boundary",
            "boundary_kind": "exterior",
            "owner_room_ids": ["room-1"],
            "mutability": "movable_with_rehost",
            "movable": True,
            "constraint_reasons": [],
            "start": {"x": 120, "y": 0},
            "end": {"x": 120, "y": 80},
            "length": 80,
            "opening_ids": ["opening-1"],
        },
    ],
    "walls": [
        {
            "wall_id": "wall-east",
            "boundary_kind": "exterior",
            "owner_room_ids": ["room-1"],
            "mutability": "movable_with_rehost",
            "movable": True,
            "start": {"x": 120, "y": 0},
            "end": {"x": 120, "y": 80},
            "length": 80,
            "hosted_opening_ids": ["opening-1"],
        }
    ],
    "openings": [
        {
            "opening_id": "opening-1",
            "opening_kind": "window",
            "host_wall_id": "wall-east",
            "owner_room_ids": ["room-1"],
            "confidence": "hosted",
            "rehost_required": True,
            "rehostable": True,
            "constraint_reasons": [],
            "offset": 20,
            "span": 20,
            "start": {"x": 120, "y": 20},
            "end": {"x": 120, "y": 40},
        }
    ],
    "footprint_bbox": {"x1": 0, "y1": 0, "x2": 120, "y2": 80, "width": 120, "height": 80},
}

RICH_OVERFLOW_SITE = {
    "buildable_envelope": {"x": 0, "y": 0, "width": 100, "height": 80},
}


def test_site_fit_propose_returns_shrink_candidate_for_single_side_rich_overflow():
    response = client.post(
        "/api/v2/site-fit/propose",
        json={
            "plan": RICH_OVERFLOW_PLAN,
            "site_constraints": RICH_OVERFLOW_SITE,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "buildable_conflict"
    assert payload["compliance_summary"]["mutation_hints"][0]["boundary_id"] == "east-boundary"
    assert payload["candidates"][0]["candidate_id"] == "shrink_boundary::east-boundary"
    assert payload["candidates"][0]["change_count"] == 1
    assert payload["candidates"][0]["changes"][0]["delta_x"] == -20.0


def test_site_fit_apply_applies_shrink_boundary_candidate_to_rich_plan_payload():
    response = client.post(
        "/api/v2/site-fit/apply",
        json={
            "plan": RICH_OVERFLOW_PLAN,
            "site_constraints": RICH_OVERFLOW_SITE,
            "candidate_id": "shrink_boundary::east-boundary",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    applied_plan = payload["applied_plan"]["plan"]
    assert payload["candidate_id"] == "shrink_boundary::east-boundary"
    assert payload["change_set"][0]["boundary_id"] == "east-boundary"
    assert applied_plan["footprint_bbox"]["x2"] == 100.0
    assert applied_plan["boundaries"][1]["start"]["x"] == 100.0
    assert applied_plan["boundaries"][1]["end"]["x"] == 100.0
    assert applied_plan["walls"][0]["start"]["x"] == 100.0
    assert applied_plan["openings"][0]["start"]["x"] == 100.0
    assert applied_plan["rooms"][0]["bbox"]["x2"] == 100.0
```

- [ ] **Step 2: Run the focused API tests to verify RED**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_site_fit_api.py::test_site_fit_propose_returns_shrink_candidate_for_single_side_rich_overflow tests/test_site_fit_api.py::test_site_fit_apply_applies_shrink_boundary_candidate_to_rich_plan_payload -q
```

Expected: FAIL because the current solver emits no shrink candidates and `apply_site_fit(...)` only accepts `baseline_preserved`.

- [ ] **Step 3: Commit the RED API tests**

```powershell
git add tests/test_site_fit_api.py
git commit -m "test: cover first site fit mutator"
```

### Task 3: Expand the model, contract, and reporter layers for diagnostics

**Files:**
- Modify: `backend/site_fit/models.py`
- Modify: `backend/site_fit/contracts.py`
- Modify: `backend/site_fit/reporter.py`
- Test: `tests/test_site_fit_constraints.py`
- Test: `tests/test_site_fit_api.py`

- [ ] **Step 1: Add diagnostic dataclasses to `backend/site_fit/models.py`**

Insert these dataclasses above `ConstraintEvaluation`:

```python
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
```

Extend `ConstraintEvaluation`:

```python
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
```

- [ ] **Step 2: Expose the new evaluator facts in `backend/site_fit/contracts.py`**

Replace `SiteFitComplianceSummaryResponse` with:

```python
class SiteFitComplianceSummaryResponse(BaseModel):
    status: str
    checked_rule_ids: list[str] = Field(default_factory=list)
    violations: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    boundary_diagnostics: list[dict] = Field(default_factory=list)
    room_diagnostics: list[dict] = Field(default_factory=list)
    mutation_hints: list[dict] = Field(default_factory=list)
```

- [ ] **Step 3: Serialize diagnostics and hints in `backend/site_fit/reporter.py`**

Update `build_compliance_summary(...)`:

```python
from dataclasses import asdict


def build_compliance_summary(evaluation: ConstraintEvaluation) -> dict:
    status = "pass" if evaluation.status == "fit_ready" else "fail"
    if evaluation.status in {"insufficient_site_constraints", "insufficient_plan_geometry"}:
        status = "not_evaluated"
    return {
        "status": status,
        "checked_rule_ids": list(evaluation.checked_rule_ids),
        "violations": [dict(item) for item in evaluation.violations],
        "warnings": list(evaluation.warnings),
        "boundary_diagnostics": [asdict(item) for item in evaluation.boundary_diagnostics],
        "room_diagnostics": [asdict(item) for item in evaluation.room_diagnostics],
        "mutation_hints": [asdict(item) for item in evaluation.mutation_hints],
    }
```

- [ ] **Step 4: Run the focused tests and confirm they still fail for evaluator logic, not missing fields**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_site_fit_constraints.py tests/test_site_fit_api.py::test_site_fit_propose_returns_shrink_candidate_for_single_side_rich_overflow -q
```

Expected: FAIL, but now due to missing evaluator logic / candidate generation rather than missing response fields.

- [ ] **Step 5: Commit the model/contract/reporter scaffolding**

```powershell
git add backend/site_fit/models.py backend/site_fit/contracts.py backend/site_fit/reporter.py
git commit -m "feat: add site fit constraint diagnostics contracts"
```

### Task 4: Implement Constraint Evaluation v2 over rich normalized boundaries

**Files:**
- Modify: `backend/site_fit/constraints.py`
- Modify: `backend/site_fit/validator.py`
- Test: `tests/test_site_fit_constraints.py`

- [ ] **Step 1: Add overflow-side and boundary-side helpers in `backend/site_fit/constraints.py`**

Insert helpers near the bottom of the file:

```python
SIDE_TO_VECTOR = {
    "west": ("x", 1.0),
    "east": ("x", -1.0),
    "north": ("y", 1.0),
    "south": ("y", -1.0),
}


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


def _boundary_side(boundary, plan_bbox: dict[str, float], *, tolerance: float = 1e-6) -> tuple[str | None, str | None]:
    start = boundary.start or {}
    end = boundary.end or {}
    if abs(start.get("x", 0.0) - end.get("x", 0.0)) <= tolerance:
        x = start.get("x", 0.0)
        if abs(x - plan_bbox["x1"]) <= tolerance:
            return "west", "x"
        if abs(x - plan_bbox["x2"]) <= tolerance:
            return "east", "x"
    if abs(start.get("y", 0.0) - end.get("y", 0.0)) <= tolerance:
        y = start.get("y", 0.0)
        if abs(y - plan_bbox["y1"]) <= tolerance:
            return "north", "y"
        if abs(y - plan_bbox["y2"]) <= tolerance:
            return "south", "y"
    return None, None
```

- [ ] **Step 2: Add room projection helpers and opening gating**

Add helpers for room minimum checks and opening checks:

```python
def _project_room(room, *, axis: str, delta: float) -> tuple[float, float, float]:
    bbox = room.bbox or {}
    current_width = float(bbox.get("width") or 0.0)
    current_height = float(bbox.get("height") or 0.0)
    projected_width = current_width - abs(delta) if axis == "x" else current_width
    projected_height = current_height - abs(delta) if axis == "y" else current_height
    projected_area = projected_width * projected_height
    return projected_width, projected_height, projected_area


def _room_is_blocked(room, *, axis: str, delta: float) -> tuple[bool, str | None, tuple[float, float, float]]:
    projected_width, projected_height, projected_area = _project_room(room, axis=axis, delta=delta)
    if room.min_width is not None and projected_width < room.min_width:
        return True, "projected width violates room minimum", (projected_width, projected_height, projected_area)
    if room.min_height is not None and projected_height < room.min_height:
        return True, "projected height violates room minimum", (projected_width, projected_height, projected_area)
    if room.min_area is not None and projected_area < room.min_area:
        return True, "projected area violates room minimum", (projected_width, projected_height, projected_area)
    return False, None, (projected_width, projected_height, projected_area)


def _opening_block_status(boundary, openings_by_id: dict[str, object]) -> tuple[bool, bool]:
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
```

- [ ] **Step 3: Rewrite the conflict branch in `evaluate_hard_constraints(...)` to emit diagnostics and hints**

Inside the `if not fits:` branch, replace the bare violation return with logic that:

```python
overflow_by_side = _overflow_by_side(plan_bbox_for_fit, buildable_bbox)
rooms_by_id = {room.room_id: room for room in plan.room_summaries}
openings_by_id = {opening.opening_id: opening for opening in plan.openings}
boundary_diagnostics = []
room_diagnostics = []
mutation_hints = []

if len(overflow_by_side) == 1:
    active_side, overflow_delta = next(iter(overflow_by_side.items()))
    axis, direction = SIDE_TO_VECTOR[active_side]
    for boundary in plan.boundary_segments:
        side, boundary_axis = _boundary_side(boundary, plan_bbox_for_fit)
        if side != active_side or boundary_axis != axis or boundary.boundary_kind != "exterior":
            continue

        blocked_opening, requires_rehost = _opening_block_status(boundary, openings_by_id)
        if boundary.mutability == "protected":
            boundary_diagnostics.append(BoundaryDiagnostic(boundary_id=boundary.boundary_id, side=side, axis=axis, overflow_delta=overflow_delta, status="blocked_protected", reason="boundary is protected", owner_room_ids=boundary.owner_room_ids, opening_ids=boundary.opening_ids, requires_rehost=requires_rehost))
            continue
        if boundary.mutability == "locked":
            boundary_diagnostics.append(BoundaryDiagnostic(boundary_id=boundary.boundary_id, side=side, axis=axis, overflow_delta=overflow_delta, status="blocked_locked", reason="boundary is locked", owner_room_ids=boundary.owner_room_ids, opening_ids=boundary.opening_ids, requires_rehost=requires_rehost))
            continue
        if blocked_opening:
            boundary_diagnostics.append(BoundaryDiagnostic(boundary_id=boundary.boundary_id, side=side, axis=axis, overflow_delta=overflow_delta, status="blocked_non_rehostable_opening", reason="hosted opening cannot be rehosted", owner_room_ids=boundary.owner_room_ids, opening_ids=boundary.opening_ids, requires_rehost=requires_rehost))
            continue

        delta = overflow_delta * direction
        owner_room_ids = tuple(boundary.owner_room_ids)
        any_blocked = False
        for room_id in owner_room_ids:
            room = rooms_by_id.get(room_id)
            if room is None:
                continue
            blocked, reason, projected = _room_is_blocked(room, axis=axis, delta=delta)
            room_status = "blocked_room_minimum" if blocked else "eligible"
            room_diagnostics.append(RoomDiagnostic(room_id=room.room_id, boundary_id=boundary.boundary_id, axis=axis, current_width=float((room.bbox or {}).get("width") or 0.0), current_height=float((room.bbox or {}).get("height") or 0.0), projected_width=projected[0], projected_height=projected[1], projected_area=projected[2], status=room_status, reason=reason))
            if blocked or room_id in (job.design_locks.get("locked_rooms") or []):
                any_blocked = True

        if any_blocked:
            boundary_diagnostics.append(BoundaryDiagnostic(boundary_id=boundary.boundary_id, side=side, axis=axis, overflow_delta=overflow_delta, status="blocked_room_minimum", reason="owner room cannot absorb the shrink", owner_room_ids=owner_room_ids, opening_ids=boundary.opening_ids, requires_rehost=requires_rehost))
            continue

        boundary_diagnostics.append(BoundaryDiagnostic(boundary_id=boundary.boundary_id, side=side, axis=axis, overflow_delta=overflow_delta, status="eligible", reason=None, owner_room_ids=owner_room_ids, opening_ids=boundary.opening_ids, requires_rehost=requires_rehost, projected_fit_status="fit_ready"))
        mutation_hints.append(MutationHint(boundary_id=boundary.boundary_id, side=side, axis=axis, delta_x=delta if axis == "x" else 0.0, delta_y=delta if axis == "y" else 0.0, owner_room_ids=owner_room_ids, opening_ids=boundary.opening_ids, requires_rehost=requires_rehost))
```

Return the conflict evaluation with the new fields populated:

```python
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
```

- [ ] **Step 4: Run the unit evaluator tests to verify GREEN**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_site_fit_constraints.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the evaluator implementation**

```powershell
git add backend/site_fit/constraints.py backend/site_fit/validator.py tests/test_site_fit_constraints.py
git commit -m "feat: evaluate site fit constraints by boundary"
```

### Task 5: Implement the first thin mutator, candidate generation, and apply/export flow

**Files:**
- Modify: `backend/site_fit/mutators.py`
- Modify: `backend/site_fit/solver.py`
- Modify: `backend/site_fit/exporters.py`
- Modify: `backend/services/site_fit_service.py`
- Test: `tests/test_site_fit_api.py`

- [ ] **Step 1: Add a shrink candidate builder to `backend/site_fit/mutators.py`**

Add this helper next to `build_baseline_candidate(...)`:

```python
def build_shrink_boundary_candidate(plan: NormalizedPlan, hint) -> dict:
    delta_x = float(hint.delta_x)
    delta_y = float(hint.delta_y)
    return {
        "candidate_id": f"shrink_boundary::{hint.boundary_id}",
        "strategy": "shrink_boundary",
        "summary": f"Move boundary {hint.boundary_id} inward to resolve {hint.side} overflow.",
        "fit_status": "fit_ready",
        "change_count": 1,
        "changes": [
            {
                "boundary_id": hint.boundary_id,
                "side": hint.side,
                "delta_x": delta_x,
                "delta_y": delta_y,
                "owner_room_ids": list(hint.owner_room_ids),
                "opening_ids": list(hint.opening_ids),
                "requires_rehost": hint.requires_rehost,
            }
        ],
    }
```

- [ ] **Step 2: Teach `backend/site_fit/solver.py` to emit shrink candidates when the evaluator provides eligible hints**

Replace `propose_candidates(...)` with:

```python
from .mutators import build_baseline_candidate, build_shrink_boundary_candidate


def propose_candidates(plan: NormalizedPlan, evaluation: ConstraintEvaluation) -> list[dict]:
    if evaluation.status == "fit_ready":
        return [score_candidate(build_baseline_candidate(plan))]
    if evaluation.status != "buildable_conflict":
        return []
    if plan.source_kind != "plan":
        return []
    return [
        score_candidate(build_shrink_boundary_candidate(plan, hint))
        for hint in evaluation.mutation_hints
    ]
```

- [ ] **Step 3: Implement payload mutation in `backend/site_fit/exporters.py`**

Add a new helper and route `export_applied_plan(...)` through it:

```python
def _apply_boundary_shrink(payload: dict, *, change: dict) -> dict:
    applied = deepcopy(payload)
    delta_x = float(change.get("delta_x") or 0.0)
    delta_y = float(change.get("delta_y") or 0.0)
    boundary_id = change["boundary_id"]
    owner_room_ids = set(change.get("owner_room_ids") or [])
    opening_ids = set(change.get("opening_ids") or [])

    for boundary in applied.get("boundaries") or []:
        if boundary.get("boundary_id") == boundary_id:
            boundary["start"]["x"] = float(boundary["start"].get("x", 0.0)) + delta_x
            boundary["end"]["x"] = float(boundary["end"].get("x", 0.0)) + delta_x
            boundary["start"]["y"] = float(boundary["start"].get("y", 0.0)) + delta_y
            boundary["end"]["y"] = float(boundary["end"].get("y", 0.0)) + delta_y

    for wall in applied.get("walls") or []:
        hosted_opening_ids = set(wall.get("hosted_opening_ids") or [])
        if hosted_opening_ids & opening_ids:
            wall["start"]["x"] = float(wall["start"].get("x", 0.0)) + delta_x
            wall["end"]["x"] = float(wall["end"].get("x", 0.0)) + delta_x
            wall["start"]["y"] = float(wall["start"].get("y", 0.0)) + delta_y
            wall["end"]["y"] = float(wall["end"].get("y", 0.0)) + delta_y

    for opening in applied.get("openings") or []:
        if opening.get("opening_id") in opening_ids:
            opening["start"]["x"] = float(opening["start"].get("x", 0.0)) + delta_x
            opening["end"]["x"] = float(opening["end"].get("x", 0.0)) + delta_x
            opening["start"]["y"] = float(opening["start"].get("y", 0.0)) + delta_y
            opening["end"]["y"] = float(opening["end"].get("y", 0.0)) + delta_y

    for room in applied.get("rooms") or []:
        if room.get("room_id") in owner_room_ids:
            bbox = room.get("bbox") or {}
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

    bbox = applied.get("footprint_bbox") or {}
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
    applied["footprint_bbox"] = bbox
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
```

- [ ] **Step 4: Allow apply flow to use generated candidates in `backend/services/site_fit_service.py`**

Replace the candidate guard in `apply_site_fit(...)` with lookup logic:

```python
candidate = next((item for item in proposal["candidates"] if item["candidate_id"] == req.candidate_id), None)
if candidate is None:
    raise ValueError("Unknown site-fit candidate_id.")
if candidate["fit_status"] != "fit_ready":
    raise ValueError("The selected candidate cannot be applied because it does not resolve fit yet.")
```

And update the response builder:

```python
"applied_plan": export_applied_plan(
    job,
    candidate_id=req.candidate_id,
    change_set=candidate.get("changes") or [],
),
"change_set": candidate.get("changes") or [],
```

- [ ] **Step 5: Run the focused API tests to verify GREEN**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_site_fit_api.py::test_site_fit_propose_returns_shrink_candidate_for_single_side_rich_overflow tests/test_site_fit_api.py::test_site_fit_apply_applies_shrink_boundary_candidate_to_rich_plan_payload -q
```

Expected: PASS.

- [ ] **Step 6: Run the focused site-fit suite and verify nothing regressed**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_site_fit_constraints.py tests/test_site_fit_normalizer.py tests/test_site_fit_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit the first thin mutator slice**

```powershell
git add backend/site_fit/mutators.py backend/site_fit/solver.py backend/site_fit/exporters.py backend/services/site_fit_service.py tests/test_site_fit_api.py tests/test_site_fit_constraints.py
git commit -m "feat: add first site fit boundary mutator"
```

## Self-review

- Spec coverage: the plan covers evaluator diagnostics, room minimum gating, opening rehost gating, mutation hints, thin candidate generation, apply/export mutation, and focused API verification.
- Placeholder scan: no TODO/TBD placeholders remain; each task names exact files, commands, and expected assertions.
- Type consistency: `BoundaryDiagnostic`, `RoomDiagnostic`, `MutationHint`, `boundary_diagnostics`, `room_diagnostics`, and `mutation_hints` are named consistently across models, contracts, reporter, evaluator, and tests.
