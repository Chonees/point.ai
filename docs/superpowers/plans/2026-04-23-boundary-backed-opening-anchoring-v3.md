# Boundary-backed Opening Anchoring v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the remaining unhosted openings by anchoring them against the cleaned canonical boundary/wall model without regressing the structural graph.

**Architecture:** Keep the current cluster-first opening pipeline, but make host selection more boundary-aware and more explicit about degenerate opening artifacts. The slice should improve `opening_graph.py` only after proving with tests that hosted openings increase while `shared`, `exterior`, `support`, and `unknown` boundary counts stay stable.

**Tech Stack:** Python, pytest, Pydantic models, JSON fixture export, React/Vitest inspector fixture consumption.

---

## File Structure

### Existing files to modify
- `backend/floor_plan_catalog/opening_graph.py` — cluster building, host ranking, opening construction, confidence/issue classification.
- `tests/test_floor_plan_catalog_opening_graph.py` — synthetic + real Seminole opening-host regressions.
- `frontend/src/features/catalogInspector/catalogInspector.fixture.json` — regenerated fixture snapshot after backend change.
- `frontend/src/features/catalogInspector/types.ts` — only if new opening issue/confidence strings need explicit typing.
- `frontend/src/features/catalogInspector/CatalogInspectorPage.tsx` — only if we surface a new metric or label.
- `frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx` — only if we need to show a new opening issue state.

### Existing files to read during implementation
- `backend/floor_plan_catalog/contracts.py` — `CatalogOpening`, `CatalogWallBoundary`, `CatalogBoundarySegment` contracts.
- `backend/floor_plan_catalog/wall_graph.py` — current wall provenance/confidence model that opening hosts depend on.
- `backend/floor_plan_catalog/boundary_graph.py` — current boundary canonicalization and artifact/support semantics.
- `scripts/export_seminole_topology_fixture.py` — real fixture regeneration path.

### Current verified baseline (must improve, not regress)
- `boundary kinds = { duplicate: 404, exterior: 182, artifact: 106, support: 40, unknown: 14, shared: 10 }`
- `opening confidence = { hosted: 65, unhosted: 56 }`
- `topology_issues = []`
- `wall_graph_issues = []`
- `opening_graph_issues = ['unhosted_opening']`

---

### Task 1: Lock the regression guardrails in tests

**Files:**
- Modify: `tests/test_floor_plan_catalog_opening_graph.py`
- Read: `backend/floor_plan_catalog/contracts.py`
- Read: `backend/floor_plan_catalog/opening_graph.py`

- [ ] **Step 1: Add a real Seminole guardrail test that verifies structural counts do not regress while unhosted openings drop**

```python
def test_derive_floor_plan_opening_graph_reduces_real_seminole_unhosted_openings_without_boundary_regression():
    seed_payload = json.loads(Path(r"D:\PointAIData\PLANS\catalog\seminole-2000.json").read_text(encoding="utf-8"))
    seed = FloorPlanCatalogSeed.model_validate(seed_payload)
    topology = derive_floor_plan_topology(seed)
    boundary_graph = derive_floor_plan_boundary_graph(seed)
    wall_graph = derive_floor_plan_wall_graph(topology, seed.cad_traces, boundary_graph=boundary_graph)

    opening_graph = derive_floor_plan_opening_graph(topology, wall_graph, seed.cad_traces)

    unhosted = [opening for opening in opening_graph.openings if opening.confidence == "unhosted"]
    hosted = [opening for opening in opening_graph.openings if opening.confidence == "hosted"]
    boundary_kinds = Counter(boundary.boundary_kind for boundary in boundary_graph.boundaries)

    assert len(unhosted) < 56
    assert len(hosted) > 65
    assert boundary_kinds["shared"] == 10
    assert boundary_kinds["exterior"] == 182
    assert boundary_kinds["support"] == 40
    assert boundary_kinds["unknown"] == 14
```

- [ ] **Step 2: Add a synthetic test for boundary-backed host preference over a weaker wall-only candidate**

```python
def test_derive_floor_plan_opening_graph_prefers_boundary_backed_host_when_wall_candidates_overlap():
    seed = build_seed_with_hostable_openings()
    topology = derive_floor_plan_topology(seed)
    room_a = topology.rooms[0].room_id
    room_b = topology.rooms[1].room_id

    weaker_wall = CatalogWallBoundary(
        wall_id="wall-weaker",
        start=CatalogPoint(x=100, y=0),
        end=CatalogPoint(x=100, y=100),
        orientation="vertical",
        length=100,
        is_exterior=False,
        room_ids=[room_a, room_b],
        boundary_kind="shared",
        owner_room_ids=[room_a, room_b],
        provenance="bbox_inferred",
        confidence="trace_supported",
        trace_support_status="snapped_to_trace",
        trace_support_ids=["shared-wall"],
        trace_support_gap=2.0,
    )
    stronger_wall = weaker_wall.model_copy(
        update={
            "wall_id": "wall-stronger",
            "provenance": "boundary_graph_shared",
            "confidence": "exact",
            "trace_support_status": "exact_trace_supported",
            "trace_support_gap": 0.0,
        }
    )
    wall_graph = FloorPlanWallGraphV1(
        floor_plan_id=topology.floor_plan_id,
        name=topology.name,
        canonical_unit=topology.canonical_unit,
        footprint_bbox=topology.footprint_bbox,
        walls=[weaker_wall, stronger_wall],
        wall_graph_readiness=WallGraphReadiness(status="ready_for_wall_graph_review", issues=[]),
        wall_graph_issues=[],
    )

    opening_graph = derive_floor_plan_opening_graph(
        topology,
        wall_graph,
        [trace for trace in seed.cad_traces if trace.trace_id == "door-shared"],
    )

    opening = next(item for item in opening_graph.openings if item.opening_kind == "door")
    assert opening.host_wall_id == "wall-stronger"
```

- [ ] **Step 3: Add a synthetic test for degenerate cluster classification so we don’t fake hosts for annotation-like fragments**

```python
def test_derive_floor_plan_opening_graph_marks_degenerate_cluster_as_opening_artifact():
    seed = build_seed_with_hostable_openings().model_copy(
        update={
            "cad_traces": [
                CatalogCadTrace(
                    trace_id="doortext-fragment-a",
                    trace_kind="door",
                    type="polyline",
                    layer="DOORTEXT",
                    points=[CatalogPoint(x=220, y=10), CatalogPoint(x=220.4, y=10.4)],
                    bbox=CatalogBBox(x1=220, y1=10, x2=220.4, y2=10.4, width=0.4, height=0.4),
                ),
                CatalogCadTrace(
                    trace_id="doortext-fragment-b",
                    trace_kind="door",
                    type="polyline",
                    layer="DOORTEXT",
                    points=[CatalogPoint(x=220.5, y=10.2), CatalogPoint(x=220.9, y=10.6)],
                    bbox=CatalogBBox(x1=220.5, y1=10.2, x2=220.9, y2=10.6, width=0.4, height=0.4),
                ),
            ]
        }
    )
    topology = derive_floor_plan_topology(seed)
    wall_graph = derive_floor_plan_wall_graph(topology, seed.cad_traces)

    opening_graph = derive_floor_plan_opening_graph(topology, wall_graph, seed.cad_traces)

    artifact = opening_graph.openings[0]
    assert artifact.confidence == "opening_artifact"
    assert artifact.host_wall_id is None
    assert "degenerate_opening_cluster" in artifact.issues
```

- [ ] **Step 4: Run the opening-graph test file and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_opening_graph.py -q
```

Expected: FAIL on the new regression/degenerate tests because the host logic still lacks boundary-backed anchoring and explicit artifact handling.

- [ ] **Step 5: Commit the failing tests**

```bash
git add tests/test_floor_plan_catalog_opening_graph.py
git commit -m "test: cover boundary-backed opening anchoring"
```

---

### Task 2: Implement boundary-backed host ranking and degenerate-opening classification

**Files:**
- Modify: `backend/floor_plan_catalog/opening_graph.py`
- Read: `backend/floor_plan_catalog/contracts.py`
- Read: `backend/floor_plan_catalog/boundary_graph.py`

- [ ] **Step 1: Add a stronger host-rank helper that prefers canonical/boundary-backed walls over weaker inferred walls**

```python
def _wall_opening_host_rank(wall: CatalogWallBoundary, opening_kind: str) -> tuple[int, int, int]:
    if opening_kind == "door":
        boundary_rank = {"shared": 0, "support": 1, "exterior": 2}.get(wall.boundary_kind, 3)
    else:
        boundary_rank = {"exterior": 0, "support": 1, "shared": 2}.get(wall.boundary_kind, 3)

    confidence_rank = {
        "exact": 0,
        "geometric_exact": 0,
        "trace_supported": 1,
        "trace_companion": 2,
    }.get(wall.confidence, 3)

    provenance_rank = {
        "boundary_graph_shared": 0,
        "boundary_graph_exterior": 0,
        "exact_room_overlap": 1,
        "room_exterior_boundary": 2,
        "bbox_inferred": 3,
    }.get(wall.provenance, 2)

    return (boundary_rank, confidence_rank, provenance_rank)
```

- [ ] **Step 2: Keep cluster-first grouping, but make final host selection aggregate evidence across the full cluster**

```python
def _select_group_host(
    attachments: list[dict],
    walls: list[CatalogWallBoundary],
    *,
    host_tolerance: float,
    minimum_overlap: float,
) -> dict | None:
    candidates_by_wall_id: dict[str, dict] = {}
    for attachment in attachments:
        for candidate in attachment.get("host_candidates", []):
            wall = candidate["wall"]
            entry = candidates_by_wall_id.setdefault(
                wall.wall_id,
                {"wall": wall, "support_count": 0, "best_score": candidate["score"]},
            )
            entry["support_count"] += 1
            if candidate["score"] < entry["best_score"]:
                entry["best_score"] = candidate["score"]

    if candidates_by_wall_id:
        best = min(
            candidates_by_wall_id.values(),
            key=lambda item: (-item["support_count"], item["best_score"]),
        )
        return {"wall": best["wall"]}

    return _find_group_host_from_cluster(
        attachments,
        walls,
        host_tolerance=host_tolerance,
        minimum_overlap=minimum_overlap,
    )
```

- [ ] **Step 3: Add a degenerate-cluster classifier before final opening construction**

```python
def _is_degenerate_opening_cluster(attachments: list[dict]) -> bool:
    traces = [attachment["trace"] for attachment in attachments]
    layers = {trace.layer.upper() for trace in traces}
    span_estimate = max(trace.bbox.width or 0.0 for trace in traces) + max(trace.bbox.height or 0.0 for trace in traces)

    if layers == {"DOORTEXT"}:
        return True
    if span_estimate <= 2.0:
        return True
    if all(_trace_orientation(trace) == "point" for trace in traces):
        return True
    return False
```

- [ ] **Step 4: Update opening construction to emit explicit opening artifacts instead of pretending they are real unhosted openings**

```python
def _build_opening(
    attachments: list[dict],
    rooms_by_id: dict[str, CatalogRoomTopology],
    host: dict | None,
) -> CatalogOpening:
    trace = attachments[0]["trace"]
    trace_ids = sorted({attachment["trace"].trace_id for attachment in attachments})

    if _is_degenerate_opening_cluster(attachments):
        start, end = _cluster_anchor_points(attachments)
        return CatalogOpening(
            opening_id=_build_opening_id(trace.trace_kind, host_wall_id=None, trace_ids=trace_ids, start=start, end=end),
            opening_kind=trace.trace_kind,
            host_wall_id=None,
            owner_room_ids=[],
            connected_room_ids=[],
            trace_ids=trace_ids,
            orientation=_cluster_orientation(attachments),
            start=start,
            end=end,
            offset=0.0,
            span=round(_distance(start, end), 3),
            confidence="opening_artifact",
            issues=["degenerate_opening_cluster"],
        )

    # existing hosted / unhosted path continues here
```

- [ ] **Step 5: Re-run the focused opening-graph tests and confirm GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_opening_graph.py -q
```

Expected: PASS

- [ ] **Step 6: Commit the backend implementation**

```bash
git add backend/floor_plan_catalog/opening_graph.py
git commit -m "feat: anchor openings against canonical boundaries"
```

---

### Task 3: Regenerate the real fixture and audit the numbers

**Files:**
- Modify: `frontend/src/features/catalogInspector/catalogInspector.fixture.json`
- Read: `scripts/export_seminole_topology_fixture.py`

- [ ] **Step 1: Regenerate the real Seminole fixture**

Run:

```powershell
.\.venv\Scripts\python.exe scripts/export_seminole_topology_fixture.py D:\PointAIData\PLANS\catalog\seminole-2000.json --output frontend/src/features/catalogInspector/catalogInspector.fixture.json
```

Expected output: the fixture path printed successfully.

- [ ] **Step 2: Audit the regenerated fixture to confirm improvement instead of cosmetic churn**

Run:

```powershell
@'
import json
from collections import Counter
from pathlib import Path
p = Path('frontend/src/features/catalogInspector/catalogInspector.fixture.json')
data = json.loads(p.read_text())
print('boundary_kinds', Counter(b['boundary_kind'] for b in data['boundaries']))
print('opening_confidence', Counter(o['confidence'] for o in data['openings']))
print('opening_issues', Counter(issue for o in data['openings'] for issue in o.get('issues', [])))
'@ | .\.venv\Scripts\python.exe -
```

Expected:
- `unhosted` is lower than `56`
- no regression in `shared = 10`, `exterior = 182`, `support = 40`, `unknown = 14`
- if `opening_artifact` appears, it should explain part of the drop honestly instead of inventing hosts

- [ ] **Step 3: If new opening confidence/issue labels need UI typing, update the TypeScript model minimally**

```ts
export interface CatalogInspectorOpening {
  // ...existing fields...
  confidence: 'hosted' | 'unhosted' | 'opening_artifact' | string
  issues: string[]
}
```

- [ ] **Step 4: Commit the fixture/type update**

```bash
git add frontend/src/features/catalogInspector/catalogInspector.fixture.json frontend/src/features/catalogInspector/types.ts
git commit -m "chore: refresh opening anchoring fixture"
```

---

### Task 4: Surface the new audit state in the inspector only if needed

**Files:**
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorPage.tsx`
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx`
- Test: `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx`

- [ ] **Step 1: Add a failing UI test only if a new confidence/issue state is present in the regenerated fixture**

```tsx
it('surfaces opening artifacts separately from real unhosted openings', () => {
  render(<CatalogInspectorPage topology={fixture} />)

  expect(screen.getByText(/^Opening artifacts$/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the focused frontend test to confirm RED**

Run:

```powershell
npx vitest run --config vitest.config.ts src/features/catalogInspector/CatalogInspectorPage.test.tsx --pool=threads
```

Expected: FAIL only if the new UI surface is genuinely required.

- [ ] **Step 3: Implement the smallest possible UI change to keep the model honest**

```tsx
const openingArtifactCount = hostedOpenings.filter((opening) => opening.confidence === 'opening_artifact').length

<div className="rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3">
  <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Opening artifacts</p>
  <p className="mt-1 text-lg font-semibold text-orange-300">{openingArtifactCount}</p>
</div>
```

```tsx
case 'opening_artifact':
  return 'Opening artifact'
```

- [ ] **Step 4: Run the focused frontend test and confirm GREEN**

Run:

```powershell
npx vitest run --config vitest.config.ts src/features/catalogInspector/CatalogInspectorPage.test.tsx --pool=threads
```

Expected: PASS

- [ ] **Step 5: Commit the UI honesty patch (only if Task 4 was needed)**

```bash
git add frontend/src/features/catalogInspector/CatalogInspectorPage.tsx frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx
git commit -m "feat: surface opening artifact audit state"
```

---

### Task 5: Full verification, documentation, and handoff

**Files:**
- Modify: `D:\obsidian\vault\01 - Projects\Point.ai\Current State.md`
- Create/Modify: `D:\obsidian\vault\01 - Projects\Point.ai\Implementation\2026-04-23 - Boundary-backed Opening Anchoring v3.md`

- [ ] **Step 1: Run the full backend verification suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_boundary_graph.py tests/test_floor_plan_catalog_wall_graph.py tests/test_floor_plan_catalog_opening_graph.py tests/test_floor_plan_catalog_topology.py tests/test_floor_plan_catalog_curator.py tests/test_floor_plan_catalog_audit.py -q
```

Expected: PASS

- [ ] **Step 2: Run the frontend verification suite from `frontend/` so Vitest resolves setup paths correctly**

Run:

```powershell
npx vitest run --config vitest.config.ts src/App.test.tsx src/features/catalogInspector/CatalogInspectorPage.test.tsx --pool=threads
```

Working directory: `frontend/`

Expected: PASS

- [ ] **Step 3: Verify the visual route still loads**

Run:

```powershell
cmd /c curl -I http://localhost:5173/?debug=seminole-topology
```

Expected: `HTTP/1.1 200 OK`

- [ ] **Step 4: Update Obsidian with the verified result and learned guardrails**

```md
## 2026-04-23 - Boundary-backed Opening Anchoring v3
- Implemented stronger boundary-backed host selection for openings.
- Reduced `unhosted_openings` from `56` to `<new value>`.
- Preserved `shared = 10`, `exterior = 182`, `support = 40`, `unknown = 14`.
- If present, `opening_artifact` now separates degenerate CAD residue from executor-grade openings.
```

- [ ] **Step 5: Commit the docs/update if any repo-tracked file changed during verification**

```bash
git status --short
```

If repo-tracked files changed:

```bash
git add <files>
git commit -m "chore: finalize boundary-backed opening anchoring v3"
```

- [ ] **Step 6: Final cleanliness check**

Run:

```powershell
git status --short
```

Expected: no output

---

## Self-Review

### Spec coverage
- Boundary-backed host selection: covered in Task 2
- Cluster-first anchoring preserved: covered in Tasks 1 and 2
- Degenerate opening separation: covered in Tasks 1 and 2
- Real Seminole regression with guardrails: covered in Task 1 and Task 3
- Honest fixture / inspector reflection: covered in Task 3 and optional Task 4
- Final verification: covered in Task 5

### Placeholder scan
- No `TODO`, `TBD`, or “handle appropriately” placeholders remain.
- Commands, files, and expected outcomes are explicit.

### Type consistency
- Uses `CatalogOpening.confidence`, existing `issues`, and current boundary metrics consistently.
- No new contract is required unless the implementation introduces `opening_artifact`, in which case the TypeScript type update is explicitly scoped in Task 3.
