# NormalizedPlan v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand `site_fit` normalization so it consumes a reduced mutable assembly (rooms, boundaries, walls, openings) instead of only counts + bbox, while preserving the current site-fit API behavior.

**Architecture:** Keep `site_fit` isolated and enrich `NormalizedPlan` itself rather than passing the entire floor-plan catalog through the boundary. `normalize_plan(...)` should detect rich catalog-like payloads, project only the executor-relevant pieces into stable site-fit dataclasses, and keep legacy bbox/count fields derived from the richer assembly so existing validation and reporting keep working.

**Tech Stack:** Python, FastAPI, Pydantic/dataclasses, pytest

---

## File map

- Modify: `backend/site_fit/models.py` — add reduced-assembly dataclasses and enrich `NormalizedPlan`.
- Modify: `backend/site_fit/normalizer.py` — detect catalog-style payloads and build `NormalizedPlan v2`.
- Modify: `backend/site_fit/reporter.py` — expose the new summary counts needed for observability.
- Modify: `backend/site_fit/contracts.py` — extend `SiteFitPlanSummaryResponse` with assembly counters.
- Modify: `backend/services/site_fit_service.py` — keep responses wired to the richer normalized plan.
- Create: `tests/test_site_fit_normalizer.py` — unit tests for rich normalization behavior.
- Modify: `tests/test_site_fit_api.py` — API-level regression for analyze/propose summaries using rich payloads.
- Read: `backend/floor_plan_catalog/contracts.py` — source field names for rooms, boundaries, walls, openings, and mutability.
- Read: `frontend/src/features/catalogInspector/catalogInspector.fixture.json` — real Seminole payload for realistic regression coverage.

### Task 1: Add RED unit coverage for rich normalized plans

**Files:**
- Create: `tests/test_site_fit_normalizer.py`
- Read: `backend/site_fit/normalizer.py`
- Read: `backend/site_fit/models.py`
- Read: `frontend/src/features/catalogInspector/catalogInspector.fixture.json`

- [ ] **Step 1: Write the failing unit tests for catalog-style payload normalization**

```python
import json
from pathlib import Path

from backend.site_fit.intake import build_site_fit_job
from backend.site_fit.normalizer import normalize_plan

FIXTURE_PATH = Path("frontend/src/features/catalogInspector/catalogInspector.fixture.json")


def _load_catalog_payload() -> dict:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    topology = fixture["topology"]
    wall_graph = fixture["wall_graph"]
    opening_graph = fixture["opening_graph"]
    boundary_graph = fixture["boundary_graph"]
    return {
        "model": topology["name"],
        "unit": topology["canonical_unit"],
        "rooms": topology["rooms"],
        "walls": wall_graph["walls"],
        "openings": opening_graph["openings"],
        "boundaries": boundary_graph["boundaries"],
        "boundary_nodes": boundary_graph["nodes"],
        "footprint_bbox": topology["footprint_bbox"],
        "structure_meta": {"unit": topology["canonical_unit"]},
    }


def test_normalize_plan_exports_rich_catalog_assembly_without_raw_traces():
    job = build_site_fit_job(
        plan=_load_catalog_payload(),
        structure=None,
        site_constraints={"buildable_envelope": {"x": 0, "y": 0, "width": 5000, "height": 5000}},
        design_locks={},
        jurisdiction=None,
        ruleset_version="site_fit_contract_v1",
    )

    normalized = normalize_plan(job)

    assert normalized.source_kind == "plan"
    assert normalized.room_count == len(normalized.room_summaries)
    assert normalized.wall_count == len(normalized.wall_segments)
    assert normalized.opening_count == len(normalized.openings)
    assert normalized.boundary_segments
    assert normalized.wall_segments
    assert normalized.openings
    assert "cad_traces" not in normalized.payload


def test_normalize_plan_preserves_mutability_and_rehostability_in_rich_payload():
    job = build_site_fit_job(
        plan=_load_catalog_payload(),
        structure=None,
        site_constraints={"buildable_envelope": {"x": 0, "y": 0, "width": 5000, "height": 5000}},
        design_locks={},
        jurisdiction=None,
        ruleset_version="site_fit_contract_v1",
    )

    normalized = normalize_plan(job)

    assert any(room.mutability == "flexible" for room in normalized.room_summaries)
    assert any(boundary.mutability == "movable" for boundary in normalized.boundary_segments)
    assert any(opening.rehost_required is True for opening in normalized.openings)
    assert normalized.movable_boundary_count > 0
    assert normalized.rehostable_opening_count > 0
```

- [ ] **Step 2: Run the new unit tests to verify they fail first**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_site_fit_normalizer.py -q
```

Expected: FAIL because `NormalizedPlan` does not yet expose `room_summaries`, `boundary_segments`, `wall_segments`, `openings`, or the new count fields.

- [ ] **Step 3: Commit the RED test scaffolding**

```powershell
git add tests/test_site_fit_normalizer.py
git commit -m "test: cover normalized plan v2"
```

### Task 2: Expand the site-fit models and summaries for the richer assembly

**Files:**
- Modify: `backend/site_fit/models.py`
- Modify: `backend/site_fit/contracts.py`
- Modify: `backend/site_fit/reporter.py`
- Test: `tests/test_site_fit_normalizer.py`
- Test: `tests/test_site_fit_api.py`

- [ ] **Step 1: Add the failing API assertion for the new summary counters**

Append this test to `tests/test_site_fit_api.py`:

```python
def test_site_fit_analyze_exposes_mutable_assembly_counts_for_catalog_payload():
    catalog_payload = {
        "model": "Catalog Sample",
        "unit": "inch",
        "rooms": [
            {
                "room_id": "room-living",
                "name": "LIVING ROOM",
                "category": "living_room",
                "bbox": {"x1": 0, "y1": 0, "x2": 120, "y2": 80, "width": 120, "height": 80},
                "centroid": {"x": 60, "y": 40},
                "width": 120,
                "height": 80,
                "area": 9600,
                "measurement_source": "catalog",
                "mutability": "flexible",
                "min_width": 84,
                "min_height": 84,
                "min_area": 10080,
                "constraint_reasons": [],
            }
        ],
        "boundaries": [
            {
                "boundary_id": "boundary-1",
                "boundary_kind": "exterior",
                "owner_room_ids": ["room-living"],
                "mutability": "movable",
                "movable": True,
                "constraint_reasons": [],
                "start": {"x": 0, "y": 0},
                "end": {"x": 120, "y": 0},
                "length": 120,
                "opening_ids": ["opening-1"],
            }
        ],
        "walls": [
            {
                "wall_id": "wall-1",
                "boundary_kind": "exterior",
                "owner_room_ids": ["room-living"],
                "mutability": "movable_with_rehost",
                "movable": True,
                "start": {"x": 0, "y": 0},
                "end": {"x": 120, "y": 0},
                "length": 120,
                "hosted_opening_ids": ["opening-1"],
            }
        ],
        "openings": [
            {
                "opening_id": "opening-1",
                "opening_kind": "window",
                "host_wall_id": "wall-1",
                "owner_room_ids": ["room-living"],
                "confidence": "hosted",
                "rehost_required": True,
                "rehostable": True,
                "constraint_reasons": ["opening_on_movable_wall"],
                "offset": 24,
                "span": 36,
                "start": {"x": 24, "y": 0},
                "end": {"x": 60, "y": 0},
            }
        ],
        "footprint_bbox": {"x1": 0, "y1": 0, "x2": 120, "y2": 80, "width": 120, "height": 80},
    }

    response = client.post(
        "/api/v2/site-fit/analyze",
        json={
            "plan": catalog_payload,
            "site_constraints": {"buildable_envelope": {"x": -10, "y": -10, "width": 260, "height": 160}},
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["plan_summary"]["movable_boundary_count"] == 1
    assert payload["plan_summary"]["protected_boundary_count"] == 0
    assert payload["plan_summary"]["locked_boundary_count"] == 0
    assert payload["plan_summary"]["rehostable_opening_count"] == 1
```

- [ ] **Step 2: Run the focused API test and confirm it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_site_fit_api.py::test_site_fit_analyze_exposes_mutable_assembly_counts_for_catalog_payload -q
```

Expected: FAIL because `SiteFitPlanSummaryResponse` and `build_plan_summary(...)` do not yet expose the new counters.

- [ ] **Step 3: Enrich `backend/site_fit/models.py` with reduced-assembly dataclasses**

Add focused dataclasses above `NormalizedPlan`:

```python
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
```

Extend `NormalizedPlan`:

```python
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
```

- [ ] **Step 4: Extend the public site-fit summary contracts**

Update `backend/site_fit/contracts.py`:

```python
class SiteFitPlanSummaryResponse(BaseModel):
    source_kind: str
    canonical_unit: Optional[str] = None
    room_count: int = 0
    wall_count: int = 0
    opening_count: int = 0
    footprint_bbox: Optional[dict] = None
    movable_boundary_count: int = 0
    protected_boundary_count: int = 0
    locked_boundary_count: int = 0
    rehostable_opening_count: int = 0
```

Update `backend/site_fit/reporter.py`:

```python
def build_plan_summary(plan: NormalizedPlan) -> dict:
    return {
        "source_kind": plan.source_kind,
        "canonical_unit": plan.canonical_unit,
        "room_count": plan.room_count,
        "wall_count": plan.wall_count,
        "opening_count": plan.opening_count,
        "footprint_bbox": plan.footprint_bbox,
        "movable_boundary_count": plan.movable_boundary_count,
        "protected_boundary_count": plan.protected_boundary_count,
        "locked_boundary_count": plan.locked_boundary_count,
        "rehostable_opening_count": plan.rehostable_opening_count,
    }
```

- [ ] **Step 5: Run the focused tests and confirm the contract layer is green**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_site_fit_normalizer.py tests/test_site_fit_api.py::test_site_fit_analyze_exposes_mutable_assembly_counts_for_catalog_payload -q
```

Expected: still FAIL until `normalize_plan(...)` starts populating the new dataclasses and counters.

- [ ] **Step 6: Commit the model/contract scaffolding**

```powershell
git add backend/site_fit/models.py backend/site_fit/contracts.py backend/site_fit/reporter.py tests/test_site_fit_api.py
git commit -m "feat: add normalized plan v2 contracts"
```

### Task 3: Teach `normalize_plan(...)` to build the reduced mutable assembly

**Files:**
- Modify: `backend/site_fit/normalizer.py`
- Test: `tests/test_site_fit_normalizer.py`
- Read: `backend/floor_plan_catalog/contracts.py`

- [ ] **Step 1: Add detection helpers for catalog-like plan payloads**

Insert these helpers near the top of `backend/site_fit/normalizer.py`:

```python
def _is_catalog_plan_payload(payload: dict) -> bool:
    rooms = payload.get("rooms") or []
    boundaries = payload.get("boundaries") or []
    return bool(rooms and boundaries and isinstance(rooms[0], dict) and "room_id" in rooms[0])


def _point_dict(point: dict | None) -> dict[str, float] | None:
    if not isinstance(point, dict):
        return None
    return {"x": float(point.get("x", 0.0)), "y": float(point.get("y", 0.0))}
```

- [ ] **Step 2: Add rich projection helpers for rooms, boundaries, walls, and openings**

Add focused helper functions:

```python
def _normalize_room_summaries(
    rooms: list[dict],
    boundaries: list[dict],
) -> tuple[NormalizedRoomSummary, ...]:
    room_boundaries: dict[str, list[str]] = {}
    for boundary in boundaries:
        for room_id in boundary.get("owner_room_ids") or []:
            room_boundaries.setdefault(str(room_id), []).append(str(boundary["boundary_id"]))
    return tuple(
        NormalizedRoomSummary(
            room_id=str(room["room_id"]),
            name=str(room.get("name") or room["room_id"]),
            category=str(room.get("category") or "unknown"),
            mutability=str(room.get("mutability") or "unknown"),
            min_width=_optional_float(room.get("min_width")),
            min_height=_optional_float(room.get("min_height")),
            min_area=_optional_float(room.get("min_area")),
            bbox=_normalize_catalog_bbox(room.get("bbox")),
            owner_boundary_ids=tuple(room_boundaries.get(room["room_id"], [])),
        )
        for room in rooms
    )
```

```python
def _normalize_boundary_segments(boundaries: list[dict]) -> tuple[NormalizedBoundarySegment, ...]:
    return tuple(
        NormalizedBoundarySegment(
            boundary_id=str(boundary["boundary_id"]),
            boundary_kind=str(boundary.get("boundary_kind") or "unknown"),
            owner_room_ids=tuple(boundary.get("owner_room_ids") or []),
            mutability=str(boundary.get("mutability") or "unknown"),
            movable=bool(boundary.get("movable")),
            constraint_reasons=tuple(boundary.get("constraint_reasons") or []),
            start=_point_dict(boundary.get("start")),
            end=_point_dict(boundary.get("end")),
            length=float(boundary.get("length") or 0.0),
            opening_ids=tuple(boundary.get("opening_ids") or []),
        )
        for boundary in boundaries
        if boundary.get("boundary_kind") not in {"duplicate", "artifact"}
    )
```

Repeat the same style for `_normalize_wall_segments(...)` and `_normalize_openings(...)`, preserving only executor-relevant fields and filtering out raw CAD-only noise.

- [ ] **Step 3: Route catalog-like plans through the rich normalization branch**

Update `normalize_plan(job)`:

```python
if job.source_kind == "plan":
    source_unit = _resolve_plan_source_unit(job.payload)
    canonical_unit = canonical_internal_unit(source_unit, fallback="inch")
    if _is_catalog_plan_payload(job.payload):
        boundary_segments = _normalize_boundary_segments(job.payload.get("boundaries") or [])
        room_summaries = _normalize_room_summaries(
            job.payload.get("rooms") or [],
            job.payload.get("boundaries") or [],
        )
        wall_segments = _normalize_wall_segments(job.payload.get("walls") or [])
        openings = _normalize_openings(job.payload.get("openings") or [])
        raw_bbox = job.payload.get("footprint_bbox") or _bbox_from_catalog_boundaries(boundary_segments)
        footprint_bbox = normalize_bbox(raw_bbox, from_unit=source_unit, to_unit="inch") if canonical_unit == "inch" else raw_bbox
        return NormalizedPlan(
            source_kind="plan",
            payload=job.payload,
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
```

Keep the existing simple-room and structure branches intact for backward compatibility.

- [ ] **Step 4: Run the unit and focused API tests until green**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_site_fit_normalizer.py tests/test_site_fit_api.py::test_site_fit_analyze_exposes_mutable_assembly_counts_for_catalog_payload -q
```

Expected: PASS.

- [ ] **Step 5: Commit the normalizer implementation**

```powershell
git add backend/site_fit/normalizer.py tests/test_site_fit_normalizer.py
git commit -m "feat: normalize catalog plans into mutable assemblies"
```

### Task 4: Lock in backward compatibility and realistic regression coverage

**Files:**
- Modify: `tests/test_site_fit_api.py`
- Modify: `backend/services/site_fit_service.py` (only if response wiring needs adjustment)
- Test: `tests/test_site_fit_normalizer.py`

- [ ] **Step 1: Add a realistic Seminole regression to the unit test file**

Append this test to `tests/test_site_fit_normalizer.py`:

```python
def test_normalize_plan_seminole_fixture_keeps_rich_counts_stable():
    job = build_site_fit_job(
        plan=_load_catalog_payload(),
        structure=None,
        site_constraints={"buildable_envelope": {"x": -1000, "y": -1000, "width": 10000, "height": 10000}},
        design_locks={},
        jurisdiction=None,
        ruleset_version="site_fit_contract_v1",
    )

    normalized = normalize_plan(job)

    assert normalized.room_count == 16
    assert normalized.movable_boundary_count == 39
    assert normalized.protected_boundary_count == 93
    assert normalized.locked_boundary_count == 59
    assert normalized.rehostable_opening_count == 12
```

- [ ] **Step 2: Re-run all site-fit tests to confirm no regression in the legacy bbox-first flow**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_site_fit_normalizer.py tests/test_site_fit_api.py -q
```

Expected: PASS, including the existing legacy API tests for plain plans and structures.

- [ ] **Step 3: If needed, keep `backend/services/site_fit_service.py` unchanged except for type-compatible summary plumbing**

The goal is to preserve the current orchestration shape:

```python
normalized_plan = normalize_plan(job)
evaluation = validate_site_fit(normalized_plan, job)
return {
    "analysis_id": uuid.uuid4().hex[:12],
    "contract_version": req.ruleset_version,
    "status": evaluation.status,
    "isolation": build_isolation_summary(),
    "plan_summary": build_plan_summary(normalized_plan),
    ...
}
```

Only adjust this file if richer summary data requires an explicit compatibility fix.

- [ ] **Step 4: Commit the regression lock-in**

```powershell
git add tests/test_site_fit_api.py tests/test_site_fit_normalizer.py backend/services/site_fit_service.py
git commit -m "test: lock normalized plan v2 regressions"
```

### Task 5: Final verification and documentation refresh

**Files:**
- Modify: `docs/superpowers/plans/2026-04-23-normalized-plan-v2.md` (check off completed work during execution)
- Modify: `D:\obsidian\vault\01 - Projects\Point.ai\Current State.md`
- Create/Modify: `D:\obsidian\vault\01 - Projects\Point.ai\Implementation\2026-04-23 - NormalizedPlan v2 implementation.md`

- [ ] **Step 1: Run the full site-fit verification suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_site_fit_normalizer.py tests/test_site_fit_api.py -q
```

Expected: PASS.

- [ ] **Step 2: Refresh Obsidian with the new current truth**

Add/update notes with:

```markdown
- `site_fit` now consumes `NormalizedPlan v2` with reduced mutable assembly pieces.
- Legacy bbox/count summaries remain for compatibility, but they are derived from the richer model.
- Next bridge becomes `Constraint Evaluation v2` over mutable boundaries instead of bbox-only fit logic.
```

- [ ] **Step 3: Verify git state before claiming completion**

Run:

```powershell
git status --short
```

Expected: clean working tree after the final commit.

- [ ] **Step 4: Final documentation commit**

```powershell
git add docs/superpowers/plans/2026-04-23-normalized-plan-v2.md "D:\obsidian\vault\01 - Projects\Point.ai\Current State.md" "D:\obsidian\vault\01 - Projects\Point.ai\Implementation\2026-04-23 - NormalizedPlan v2 implementation.md"
git commit -m "docs: record normalized plan v2 implementation"
```

## Self-review

- Spec coverage: the plan covers model expansion, normalizer enrichment, summary/reporter wiring, rich payload regression, and Obsidian updates. The next slice (`Constraint Evaluation v2`) is intentionally left out.
- Placeholder scan: no TBD/TODO placeholders remain; every task includes concrete files, code, and commands.
- Type consistency: `NormalizedRoomSummary`, `NormalizedBoundarySegment`, `NormalizedWallSegment`, `NormalizedOpeningSummary`, and the new plan summary counters are named consistently across tasks.

