# Exact Boundary Dedup / Family Clustering v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert duplicate/equivalent boundary fragments into canonical boundary families so the graph becomes less redundant and `unknown` noise drops below the current `286` baseline.

**Architecture:** Keep the pipeline boundary-first. Add family metadata directly to `CatalogBoundarySegment`, cluster exact-geometry duplicate boundaries inside `boundary_graph.py`, and preserve secondary pieces as traceable family members instead of pretending they are independent canonical segments. Then expose that family metadata in the temporary inspector so the graph remains visually honest.

**Tech Stack:** Python 3.14, Pydantic models, pytest, React, TypeScript, Vitest, existing topology inspector fixture/export pipeline.

---

## File Structure

### Existing files to modify
- `backend/floor_plan_catalog/contracts.py` — add boundary family metadata fields
- `backend/floor_plan_catalog/boundary_graph.py` — derive canonical boundary families and mark duplicate members deterministically
- `tests/test_floor_plan_catalog_boundary_graph.py` — backend RED/GREEN coverage for duplicate families and Seminole reduction
- `scripts/export_seminole_topology_fixture.py` — regenerate the real fixture with the new fields (likely no code change, but required in verification)
- `frontend/src/features/catalogInspector/types.ts` — surface family metadata to the UI layer
- `frontend/src/features/catalogInspector/CatalogInspectorPage.tsx` — add duplicate-boundary metric(s)
- `frontend/src/features/catalogInspector/CatalogInspectorCanvas.tsx` — color/style duplicate family members distinctly
- `frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx` — show family id / role / duplicate-of metadata
- `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx` — frontend RED/GREEN coverage for family metadata visibility

### Verification targets
- `tests/test_floor_plan_catalog_boundary_graph.py`
- `tests/test_floor_plan_catalog_wall_graph.py`
- `tests/test_floor_plan_catalog_opening_graph.py`
- `tests/test_floor_plan_catalog_topology.py`
- `tests/test_floor_plan_catalog_curator.py`
- `tests/test_floor_plan_catalog_audit.py`
- `frontend/src/App.test.tsx`
- `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx`

---

### Task 1: Add the failing backend tests for boundary families

**Files:**
- Modify: `tests/test_floor_plan_catalog_boundary_graph.py`
- Test: `tests/test_floor_plan_catalog_boundary_graph.py`

- [ ] **Step 1: Add a synthetic exact-duplicate test**

```python
def test_boundary_graph_groups_exact_duplicate_segments_into_one_family():
    seed = build_duplicate_geometry_seed()

    graph = derive_floor_plan_boundary_graph(seed)
    family_members = [
        boundary
        for boundary in graph.boundaries
        if boundary.boundary_family_id is not None
    ]
    canonical = [boundary for boundary in family_members if boundary.family_role == "canonical"]
    duplicates = [boundary for boundary in family_members if boundary.family_role == "duplicate"]

    assert canonical
    assert duplicates
    assert len({boundary.boundary_family_id for boundary in family_members}) == 1
    assert all(boundary.duplicate_of_boundary_id == canonical[0].boundary_id for boundary in duplicates)
```

- [ ] **Step 2: Add a deterministic selection test**

```python
def test_boundary_graph_picks_the_best_boundary_as_family_canonical_member():
    seed = build_duplicate_geometry_seed()

    graph = derive_floor_plan_boundary_graph(seed)
    canonical = next(boundary for boundary in graph.boundaries if boundary.family_role == "canonical")

    assert canonical.boundary_kind in {"shared", "exterior", "support"}
    assert canonical.duplicate_of_boundary_id is None
```

- [ ] **Step 3: Tighten the real Seminole regression test**

```python
def test_seminole_boundary_graph_reduces_unknown_boundaries_with_family_clustering():
    seed = load_seminole_seed()

    graph = derive_floor_plan_boundary_graph(seed)
    unknown = [boundary for boundary in graph.boundaries if boundary.boundary_kind == "unknown"]
    duplicates = [boundary for boundary in graph.boundaries if boundary.family_role == "duplicate"]

    assert duplicates
    assert len(unknown) < 286
```

- [ ] **Step 4: Add the synthetic fixture builder used by the tests**

```python
def build_duplicate_geometry_seed() -> FloorPlanCatalogSeed:
    room = CatalogRoom(
        name="DUPLICATE TEST",
        polygon=[
            CatalogPoint(x=0, y=0),
            CatalogPoint(x=120, y=0),
            CatalogPoint(x=120, y=60),
            CatalogPoint(x=0, y=60),
        ],
        bbox=CatalogBBox(x1=0, y1=0, x2=120, y2=60, width=120, height=60),
        centroid=CatalogPoint(x=60, y=30),
        width=120,
        height=60,
        area=7200,
        measurement_source="room_region",
    )
    return FloorPlanCatalogSeed(
        floor_plan_id="duplicate-geometry-seed",
        name="DUPLICATE GEOMETRY",
        source_path="synthetic/duplicate-geometry.dxf",
        canonical_unit="inch",
        footprint_bbox=CatalogBBox(x1=0, y1=0, x2=120, y2=60, width=120, height=60),
        rooms=[room],
        cad_traces=[
            build_trace("wall-bottom-a", (0, 0), (120, 0)),
            build_trace("wall-bottom-b", (0, 0), (120, 0)),
            build_trace("wall-left", (0, 0), (0, 60)),
            build_trace("wall-right", (120, 0), (120, 60)),
            build_trace("wall-top", (0, 60), (120, 60)),
        ],
        source_layers=["WALLS"],
        block_refs=[],
        readiness=CatalogReadiness(status="ready_for_catalog", issues=[]),
    )
```

- [ ] **Step 5: Run the backend RED test to verify failure**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_boundary_graph.py -q
```

Expected:
- FAIL because `CatalogBoundarySegment` does not yet expose family metadata and no duplicate clustering exists yet

- [ ] **Step 6: Commit the RED test**

```bash
git add tests/test_floor_plan_catalog_boundary_graph.py
git commit -m "test: cover boundary family clustering"
```

---

### Task 2: Implement boundary family metadata and exact duplicate clustering

**Files:**
- Modify: `backend/floor_plan_catalog/contracts.py`
- Modify: `backend/floor_plan_catalog/boundary_graph.py`
- Test: `tests/test_floor_plan_catalog_boundary_graph.py`

- [ ] **Step 1: Add family metadata fields to `CatalogBoundarySegment`**

```python
class CatalogBoundarySegment(BaseModel):
    boundary_id: str
    start_node_id: str
    end_node_id: str
    start: CatalogPoint
    end: CatalogPoint
    orientation: str
    length: float
    source_trace_ids: list[str] = Field(default_factory=list)
    boundary_kind: str = "unknown"
    owner_room_ids: list[str] = Field(default_factory=list)
    companion_boundary_id: str | None = None
    boundary_family_id: str | None = None
    family_role: str = "unknown"
    duplicate_of_boundary_id: str | None = None
    opening_ids: list[str] = Field(default_factory=list)
    confidence: str = "unverified"
    issues: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: Add a canonical family id helper in `boundary_graph.py`**

```python
def _build_boundary_family_id(orientation: str, start: CatalogPoint, end: CatalogPoint) -> str:
    digest = hashlib.sha1(
        f"{orientation}|{start.x:.3f}|{start.y:.3f}|{end.x:.3f}|{end.y:.3f}".encode("utf-8")
    ).hexdigest()[:12]
    return f"family-{digest}"
```

- [ ] **Step 3: Add deterministic ranking helpers**

```python
_BOUNDARY_KIND_PRIORITY = {
    "shared": 0,
    "exterior": 1,
    "support": 2,
    "unknown": 3,
}

_CONFIDENCE_PRIORITY = {
    "trace_projected": 0,
    "trace_exact": 1,
    "trace_partitioned": 2,
    "trace_companion": 3,
    "unverified": 4,
}


def _boundary_family_rank(boundary: CatalogBoundarySegment) -> tuple[int, int, float, str]:
    return (
        _BOUNDARY_KIND_PRIORITY.get(boundary.boundary_kind, 99),
        _CONFIDENCE_PRIORITY.get(boundary.confidence, 99),
        -boundary.length,
        boundary.boundary_id,
    )
```

- [ ] **Step 4: Cluster exact duplicate geometry and mark family roles**

```python
def _cluster_exact_duplicate_boundaries(
    boundaries: list[CatalogBoundarySegment],
) -> list[CatalogBoundarySegment]:
    grouped: dict[tuple[str, tuple[tuple[float, float], tuple[float, float]]], list[CatalogBoundarySegment]] = defaultdict(list)
    for boundary in boundaries:
        canonical_start, canonical_end = _sorted_boundary_endpoints(boundary.start, boundary.end)
        grouped[(boundary.orientation, (canonical_start, canonical_end))].append(boundary)

    clustered: list[CatalogBoundarySegment] = []
    for (orientation, (start_key, end_key)), members in grouped.items():
        if len(members) == 1:
            clustered.append(members[0])
            continue
        canonical = sorted(members, key=_boundary_family_rank)[0]
        family_id = _build_boundary_family_id(
            orientation,
            CatalogPoint(x=start_key[0], y=start_key[1]),
            CatalogPoint(x=end_key[0], y=end_key[1]),
        )
        for member in members:
            if member.boundary_id == canonical.boundary_id:
                clustered.append(
                    member.model_copy(
                        update={
                            "boundary_family_id": family_id,
                            "family_role": "canonical",
                            "duplicate_of_boundary_id": None,
                        }
                    )
                )
            else:
                clustered.append(
                    member.model_copy(
                        update={
                            "boundary_family_id": family_id,
                            "family_role": "duplicate",
                            "duplicate_of_boundary_id": canonical.boundary_id,
                            "issues": sorted({*member.issues, "duplicate_geometry"}),
                        }
                    )
                )
        
    return clustered
```

- [ ] **Step 5: Wire the clustering pass into `derive_floor_plan_boundary_graph`**

```python
boundaries = _promote_support_boundaries(boundaries)
boundaries = _cluster_exact_duplicate_boundaries(boundaries)
```

- [ ] **Step 6: Preserve explicit family role on support boundaries**

```python
promoted.append(
    boundary.model_copy(
        update={
            "boundary_kind": "support",
            "owner_room_ids": list(companion.owner_room_ids),
            "companion_boundary_id": companion.boundary_id,
            "confidence": "trace_companion",
            "family_role": "support",
            "issues": sorted({*boundary.issues, "secondary_shell"}),
        }
    )
)
```

- [ ] **Step 7: Run the backend GREEN test**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_boundary_graph.py -q
```

Expected:
- PASS
- exact duplicate boundaries now have family metadata
- Seminole unknown count drops below `286`

- [ ] **Step 8: Commit**

```bash
git add backend/floor_plan_catalog/contracts.py backend/floor_plan_catalog/boundary_graph.py tests/test_floor_plan_catalog_boundary_graph.py
git commit -m "feat: add exact boundary family clustering"
```

---

### Task 3: Add the failing frontend test for family metadata visibility

**Files:**
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx`
- Test: `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx`

- [ ] **Step 1: Add a UI test for duplicate-boundary metrics**

```tsx
it('renders duplicate boundary metrics from the fixture', () => {
  render(<CatalogInspectorPage topology={fixture} />)

  expect(screen.getByText(/^Duplicate boundaries$/i)).toBeInTheDocument()
  expect(screen.getByText(/^Support boundaries$/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Add a UI test for selected boundary family metadata**

```tsx
it('shows boundary family metadata for a selected duplicate or canonical member', () => {
  render(<CatalogInspectorPage topology={fixture} />)

  fireEvent.click(screen.getByRole('checkbox', { name: /exact boundaries/i }))
  fireEvent.click(screen.getAllByTestId(/^boundary-/)[0])

  const boundaryPanel = screen.getByTestId('selected-boundary-panel')
  expect(within(boundaryPanel).getByText(/family id/i)).toBeInTheDocument()
  expect(within(boundaryPanel).getByText(/family role/i)).toBeInTheDocument()
  expect(within(boundaryPanel).getByText(/duplicate of/i)).toBeInTheDocument()
})
```

- [ ] **Step 3: Run the frontend RED test**

Run:

```bash
cmd /c npm --prefix frontend test -- src/features/catalogInspector/CatalogInspectorPage.test.tsx
```

Expected:
- FAIL because the UI does not yet expose duplicate family metrics / sidebar metadata

- [ ] **Step 4: Commit the RED test**

```bash
git add frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx
git commit -m "test: cover boundary family metadata in inspector"
```

---

### Task 4: Surface boundary family metadata in the inspector and regenerate the real fixture

**Files:**
- Modify: `frontend/src/features/catalogInspector/types.ts`
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorPage.tsx`
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorCanvas.tsx`
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx`
- Modify: `frontend/src/features/catalogInspector/catalogInspector.fixture.json`
- Test: `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx`

- [ ] **Step 1: Add family fields to the inspector boundary type**

```ts
export interface CatalogInspectorBoundary {
  boundary_id: string
  start_node_id: string
  end_node_id: string
  start: CatalogInspectorPoint
  end: CatalogInspectorPoint
  orientation: 'horizontal' | 'vertical' | 'diagonal' | string
  length: number
  source_trace_ids: string[]
  boundary_kind: 'shared' | 'exterior' | 'support' | 'unknown' | string
  owner_room_ids: string[]
  companion_boundary_id?: string | null
  boundary_family_id?: string | null
  family_role?: 'canonical' | 'duplicate' | 'support' | 'unknown' | string
  duplicate_of_boundary_id?: string | null
  opening_ids: string[]
  confidence: string
  issues: string[]
}
```

- [ ] **Step 2: Add duplicate-boundary metrics in `CatalogInspectorPage.tsx`**

```tsx
const duplicateBoundaryCount = boundaries.filter((boundary) => boundary.family_role === 'duplicate').length
const canonicalBoundaryCount = boundaries.filter((boundary) => boundary.family_role === 'canonical').length
```

```tsx
<div className="rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3">
  <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Duplicate boundaries</p>
  <p className="mt-1 text-lg font-semibold text-rose-200">{duplicateBoundaryCount}</p>
</div>
```

- [ ] **Step 3: Give duplicate family members a distinct canvas style**

```tsx
function boundaryStroke(boundary: CatalogInspectorBoundary, isSelected: boolean) {
  if (boundary.family_role === 'duplicate') return isSelected ? '#fda4af' : 'rgba(251,113,133,0.58)'
  if (boundary.boundary_kind === 'shared') return isSelected ? '#fde68a' : 'rgba(250,204,21,0.82)'
  if (boundary.boundary_kind === 'exterior') return isSelected ? '#67e8f9' : 'rgba(34,211,238,0.68)'
  if (boundary.boundary_kind === 'support') return isSelected ? '#c4b5fd' : 'rgba(167,139,250,0.72)'
  return isSelected ? '#fca5a5' : 'rgba(248,113,113,0.58)'
}
```

- [ ] **Step 4: Show family metadata in the sidebar**

```tsx
<div className="rounded-xl bg-black/20 p-3">
  <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Family id</p>
  <p className="mt-1 text-zinc-100">{selectedBoundary.boundary_family_id ?? 'None'}</p>
</div>
<div className="rounded-xl bg-black/20 p-3">
  <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Family role</p>
  <p className="mt-1 text-zinc-100">{selectedBoundary.family_role ?? 'unknown'}</p>
</div>
<div className="rounded-xl bg-black/20 p-3">
  <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Duplicate of</p>
  <p className="mt-1 text-zinc-100">{selectedBoundary.duplicate_of_boundary_id ?? 'None'}</p>
</div>
```

- [ ] **Step 5: Regenerate the real fixture**

Run:

```bash
.\.venv\Scripts\python.exe scripts/export_seminole_topology_fixture.py D:\PointAIData\PLANS\catalog\seminole-2000.json --output frontend/src/features/catalogInspector\catalogInspector.fixture.json
```

Expected:
- fixture now includes `boundary_family_id`, `family_role`, and `duplicate_of_boundary_id`
- duplicate family members become visible in the inspector dataset

- [ ] **Step 6: Run the frontend GREEN test**

Run:

```bash
cmd /c npm --prefix frontend test -- src/features/catalogInspector/CatalogInspectorPage.test.tsx
```

Expected:
- PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/catalogInspector/types.ts frontend/src/features/catalogInspector/CatalogInspectorPage.tsx frontend/src/features/catalogInspector/CatalogInspectorCanvas.tsx frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx frontend/src/features/catalogInspector/catalogInspector.fixture.json frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx
git commit -m "feat: surface boundary family metadata in inspector"
```

---

### Task 5: Run full regression verification and capture the new state

**Files:**
- Modify: `D:\obsidian\vault\01 - Projects\Point.ai\Current State.md`
- Create: `D:\obsidian\vault\01 - Projects\Point.ai\Implementation\2026-04-22 - Exact Boundary Dedup Family Clustering v1.md`

- [ ] **Step 1: Run the full backend verification**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_boundary_graph.py tests/test_floor_plan_catalog_wall_graph.py tests/test_floor_plan_catalog_opening_graph.py tests/test_floor_plan_catalog_topology.py tests/test_floor_plan_catalog_curator.py tests/test_floor_plan_catalog_audit.py -q
```

Expected:
- PASS
- `unsupported_exterior = 0` remains true
- `unsupported_shared = 0` remains true

- [ ] **Step 2: Run the focused frontend verification**

Run:

```bash
cmd /c npm --prefix frontend test -- src/App.test.tsx src/features/catalogInspector/CatalogInspectorPage.test.tsx
```

Expected:
- PASS

- [ ] **Step 3: Verify the local inspector route still responds**

Run:

```bash
cmd /c curl -I http://localhost:5173/?debug=seminole-topology
```

Expected:
- `HTTP/1.1 200 OK`

- [ ] **Step 4: Capture the verified result in Obsidian**

Append to `Current State.md` and write an implementation note with the new breakdown, for example:

```md
- 2026-04-22: Added exact boundary family clustering. Verified SEMINOLE2000 now exports fewer `unknown` boundaries, explicit duplicate family members, and inspector-visible family metadata while keeping unsupported shared/exterior walls at zero.
```

- [ ] **Step 5: Confirm clean git status**

Run:

```bash
git status --short
```

Expected:
- empty output

- [ ] **Step 6: Commit documentation-only follow-up if needed**

```bash
git add docs/superpowers/plans/2026-04-22-exact-boundary-dedup-family-clustering-v1.md
git commit -m "docs: record exact boundary family clustering verification"
```

---

## Self-Review

### Spec coverage
- Canonical family semantics: covered in Task 2
- Deterministic canonical selection: covered in Task 2
- Seminole `unknown` reduction: covered in Tasks 1, 2, and 5
- Inspector family visibility: covered in Tasks 3 and 4
- Preservation of support-shell semantics: covered in Task 2

### Placeholder scan
- No `TODO`, `TBD`, or “implement later” placeholders remain
- Every task includes exact file paths, commands, and code blocks

### Type consistency
- `CatalogBoundarySegment` backend fields align with `CatalogInspectorBoundary` frontend fields
- The plan consistently uses `boundary_family_id`, `family_role`, and `duplicate_of_boundary_id`

