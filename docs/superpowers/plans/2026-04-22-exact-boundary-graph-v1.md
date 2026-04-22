# Exact Boundary Graph v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Derivar un boundary graph exacto para `SEMINOLE2000`, reproyectar la lectura actual del plano sobre ese graph y exponer la comparación visual en el inspector técnico para preparar el futuro site-aware executor.

**Architecture:** Vamos a introducir una nueva capa `FloorPlanBoundaryGraphV1` entre `cad_traces` y `wall_graph`. Primero normalizamos traces y detectamos nodos/segmentos exactos en tests sintéticos; después conectamos esa capa con el catálogo real de Seminole, derivamos métricas y finalmente la mostramos en el inspector para comparar raw traces vs wall graph actual vs exact boundaries.

**Tech Stack:** Python 3.14, pytest, Pydantic models, React + TypeScript inspector temporal, Vite test.

---

## File Map

### Backend
- Create: `backend/floor_plan_catalog/boundary_graph.py` — derivación del boundary graph exacto desde traces y apertura a integración futura con wall/opening graph.
- Modify: `backend/floor_plan_catalog/contracts.py` — nuevos contratos `CatalogBoundaryNode`, `CatalogBoundarySegment`, `BoundaryGraphReadiness`, `FloorPlanBoundaryGraphV1`.
- Modify: `scripts/export_seminole_topology_fixture.py` — exportar boundary graph al fixture del inspector.

### Tests
- Create: `tests/test_floor_plan_catalog_boundary_graph.py` — TDD del graph exacto con casos sintéticos y Seminole.
- Modify: `tests/test_floor_plan_catalog_topology.py` — integrar boundary graph en el pipeline exportado si hace falta validar compatibilidad.

### Frontend
- Modify: `frontend/src/features/catalogInspector/types.ts` — tipos para `nodes` y `boundaries`.
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorPage.tsx` — métricas, toggles y estado de selección.
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorCanvas.tsx` — render de exact boundaries y nodos.
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx` — detalles de boundary/node seleccionados.
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx` — tests de UI para el overlay nuevo.
- Modify: `frontend/src/features/catalogInspector/catalogInspector.fixture.json` — fixture regenerada.

### Docs
- Modify: `MVP.md` — reflejar que el bridge al executor ahora pasa por exact boundary graph.
- Modify: `D:\obsidian\vault\01 - Projects\Point.ai\Current State.md` — estado duradero.
- Create: `D:\obsidian\vault\01 - Projects\Point.ai\Implementation\2026-04-22 - Exact boundary graph v1 implementation.md`.

---

### Task 1: Definir contratos y casos sintéticos del boundary graph

**Files:**
- Modify: `backend/floor_plan_catalog/contracts.py`
- Create: `tests/test_floor_plan_catalog_boundary_graph.py`

- [ ] **Step 1: Write the failing contract test**

```python
from backend.floor_plan_catalog.boundary_graph import derive_floor_plan_boundary_graph
from backend.floor_plan_catalog.contracts import FloorPlanCatalogSeed


def test_derive_boundary_graph_creates_nodes_and_boundaries_for_l_shape_seed():
    seed = build_l_shape_seed()

    graph = derive_floor_plan_boundary_graph(seed)

    assert graph.floor_plan_id == seed.floor_plan_id
    assert len(graph.nodes) >= 4
    assert len(graph.boundaries) >= 4
    assert any(node.node_kind == 'corner' for node in graph.nodes)
    assert all(boundary.source_trace_ids for boundary in graph.boundaries)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_floor_plan_catalog_boundary_graph.py::test_derive_boundary_graph_creates_nodes_and_boundaries_for_l_shape_seed -q`
Expected: FAIL with `ModuleNotFoundError` or missing contract/symbols for `boundary_graph`.

- [ ] **Step 3: Add minimal contracts and placeholder derivation**

```python
class CatalogBoundaryNode(BaseModel):
    node_id: str
    point: CatalogPoint
    node_kind: str = 'corner'
    incident_boundary_ids: list[str] = Field(default_factory=list)


class CatalogBoundarySegment(BaseModel):
    boundary_id: str
    start_node_id: str
    end_node_id: str
    start: CatalogPoint
    end: CatalogPoint
    orientation: str
    length: float
    source_trace_ids: list[str] = Field(default_factory=list)
    boundary_kind: str = 'unknown'
    owner_room_ids: list[str] = Field(default_factory=list)
    opening_ids: list[str] = Field(default_factory=list)
    confidence: str = 'unverified'
    issues: list[str] = Field(default_factory=list)


class FloorPlanBoundaryGraphV1(BaseModel):
    floor_plan_id: str
    name: str
    canonical_unit: str
    nodes: list[CatalogBoundaryNode] = Field(default_factory=list)
    boundaries: list[CatalogBoundarySegment] = Field(default_factory=list)
    boundary_graph_readiness: CatalogReadiness
    boundary_graph_issues: list[str] = Field(default_factory=list)
```

```python
def derive_floor_plan_boundary_graph(seed: FloorPlanCatalogSeed) -> FloorPlanBoundaryGraphV1:
    return FloorPlanBoundaryGraphV1(
        floor_plan_id=seed.floor_plan_id,
        name=seed.name,
        canonical_unit=seed.canonical_unit,
        nodes=[],
        boundaries=[],
        boundary_graph_readiness=CatalogReadiness(status='needs_boundary_review', issues=['missing_boundaries']),
        boundary_graph_issues=['missing_boundaries'],
    )
```

- [ ] **Step 4: Run test to verify targeted failure changes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_floor_plan_catalog_boundary_graph.py::test_derive_boundary_graph_creates_nodes_and_boundaries_for_l_shape_seed -q`
Expected: FAIL on length assertions instead of import errors.

- [ ] **Step 5: Implement minimal synthetic graph derivation to pass**

```python
def derive_floor_plan_boundary_graph(seed: FloorPlanCatalogSeed) -> FloorPlanBoundaryGraphV1:
    wall_segments = _canonicalize_wall_segments(seed.wall_traces)
    nodes, boundaries = _build_graph_from_segments(wall_segments)
    issues = [] if boundaries else ['missing_boundaries']
    return FloorPlanBoundaryGraphV1(
        floor_plan_id=seed.floor_plan_id,
        name=seed.name,
        canonical_unit=seed.canonical_unit,
        nodes=nodes,
        boundaries=boundaries,
        boundary_graph_readiness=CatalogReadiness(
            status='ready_for_boundary_review' if not issues else 'needs_boundary_review',
            issues=issues,
        ),
        boundary_graph_issues=issues,
    )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_floor_plan_catalog_boundary_graph.py::test_derive_boundary_graph_creates_nodes_and_boundaries_for_l_shape_seed -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/floor_plan_catalog/contracts.py backend/floor_plan_catalog/boundary_graph.py tests/test_floor_plan_catalog_boundary_graph.py
git commit -m "feat: add exact boundary graph contracts"
```

### Task 2: TDD corner, tee, and opening-cut segmentation

**Files:**
- Modify: `tests/test_floor_plan_catalog_boundary_graph.py`
- Modify: `backend/floor_plan_catalog/boundary_graph.py`

- [ ] **Step 1: Write failing geometric behavior tests**

```python
def test_boundary_graph_splits_segments_at_tee_intersection():
    seed = build_tee_seed()

    graph = derive_floor_plan_boundary_graph(seed)

    assert any(node.node_kind == 'tee' for node in graph.nodes)
    assert len([b for b in graph.boundaries if b.orientation == 'vertical']) >= 2


def test_boundary_graph_marks_opening_cuts_on_horizontal_wall():
    seed = build_opening_cut_seed()

    graph = derive_floor_plan_boundary_graph(seed)

    assert any(node.node_kind == 'opening_cut' for node in graph.nodes)
    assert any(boundary.opening_ids for boundary in graph.boundaries)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_floor_plan_catalog_boundary_graph.py -q`
Expected: FAIL on missing tee/opening-cut support.

- [ ] **Step 3: Implement node splitting and opening cuts**

```python
def _collect_split_points(wall_segments, opening_segments):
    split_points = defaultdict(set)
    for wall in wall_segments:
        split_points[wall.trace_id].update(_intersections_for_wall(wall, wall_segments))
        split_points[wall.trace_id].update(_opening_cuts_for_wall(wall, opening_segments))
    return split_points


def _node_kind(point, incident_segments, opening_points):
    if point in opening_points:
        return 'opening_cut'
    if len(incident_segments) >= 4:
        return 'cross'
    if len(incident_segments) == 3:
        return 'tee'
    return 'corner'
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_floor_plan_catalog_boundary_graph.py -q`
Expected: PASS for synthetic graph tests.

- [ ] **Step 5: Commit**

```bash
git add backend/floor_plan_catalog/boundary_graph.py tests/test_floor_plan_catalog_boundary_graph.py
git commit -m "feat: split exact boundary graph at tees and openings"
```

### Task 3: Integrate Seminole and prove shared boundaries are no longer bbox-derived

**Files:**
- Modify: `tests/test_floor_plan_catalog_boundary_graph.py`
- Modify: `backend/floor_plan_catalog/boundary_graph.py`

- [ ] **Step 1: Write the failing Seminole integration test**

```python
def test_seminole_boundary_graph_produces_shared_boundaries_without_bbox_inference():
    seed = load_seminole_seed()

    graph = derive_floor_plan_boundary_graph(seed)

    shared = [boundary for boundary in graph.boundaries if boundary.boundary_kind == 'shared']

    assert shared
    assert all(boundary.confidence in {'trace_exact', 'trace_merged', 'trace_partitioned'} for boundary in shared)
    assert all('bbox_inferred' not in boundary.issues for boundary in shared)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_floor_plan_catalog_boundary_graph.py::test_seminole_boundary_graph_produces_shared_boundaries_without_bbox_inference -q`
Expected: FAIL because Seminole still lacks exact shared boundary classification.

- [ ] **Step 3: Implement Seminole-ready exact boundary classification**

```python
def _classify_boundary_kind(boundary, rooms):
    owner_room_ids = _touching_room_ids(boundary, rooms)
    if len(owner_room_ids) == 2:
        return 'shared', owner_room_ids, 'trace_partitioned'
    if len(owner_room_ids) == 1:
        return 'exterior', owner_room_ids, 'trace_exact'
    return 'unknown', owner_room_ids, 'unverified'
```

```python
def _build_boundaries(...):
    # derive owner rooms from exact segments and room reprojection, not bbox adjacency
    ...
```

- [ ] **Step 4: Run targeted test and then full backend boundary suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_floor_plan_catalog_boundary_graph.py::test_seminole_boundary_graph_produces_shared_boundaries_without_bbox_inference -q`
Expected: PASS.

Run: `./.venv/Scripts/python.exe -m pytest tests/test_floor_plan_catalog_boundary_graph.py tests/test_floor_plan_catalog_wall_graph.py tests/test_floor_plan_catalog_opening_graph.py tests/test_floor_plan_catalog_topology.py tests/test_floor_plan_catalog_curator.py tests/test_floor_plan_catalog_audit.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/floor_plan_catalog/boundary_graph.py tests/test_floor_plan_catalog_boundary_graph.py
git commit -m "feat: derive exact shared boundaries for seminole"
```

### Task 4: Export exact boundary graph to the inspector fixture

**Files:**
- Modify: `scripts/export_seminole_topology_fixture.py`
- Modify: `tests/test_floor_plan_catalog_topology.py`
- Modify: `frontend/src/features/catalogInspector/catalogInspector.fixture.json`

- [ ] **Step 1: Write the failing export test**

```python
def test_export_fixture_includes_boundary_graph_payload(tmp_path):
    output_path = tmp_path / 'fixture.json'

    export_seminole_topology_fixture(output_path)

    payload = json.loads(output_path.read_text())
    assert 'boundaryNodes' in payload
    assert 'boundaries' in payload
    assert payload['boundaries']
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_floor_plan_catalog_topology.py::test_export_fixture_includes_boundary_graph_payload -q`
Expected: FAIL because boundary graph is not exported yet.

- [ ] **Step 3: Implement export wiring**

```python
boundary_graph = derive_floor_plan_boundary_graph(seed)
...
payload['boundaryNodes'] = [node.model_dump(mode='json') for node in boundary_graph.nodes]
payload['boundaries'] = [boundary.model_dump(mode='json') for boundary in boundary_graph.boundaries]
payload['boundary_graph_readiness'] = boundary_graph.boundary_graph_readiness.model_dump(mode='json')
payload['boundary_graph_issues'] = boundary_graph.boundary_graph_issues
```

- [ ] **Step 4: Run test and regenerate fixture**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_floor_plan_catalog_topology.py::test_export_fixture_includes_boundary_graph_payload -q`
Expected: PASS.

Run: `./.venv/Scripts/python.exe scripts/export_seminole_topology_fixture.py D:\PointAIData\PLANS\catalog\seminole-2000.json --output frontend/src/features/catalogInspector/catalogInspector.fixture.json`
Expected: script completes and fixture gains boundary graph payload.

- [ ] **Step 5: Commit**

```bash
git add scripts/export_seminole_topology_fixture.py tests/test_floor_plan_catalog_topology.py frontend/src/features/catalogInspector/catalogInspector.fixture.json
git commit -m "feat: export exact boundary graph to inspector fixture"
```

### Task 5: Show exact boundaries and nodes in the inspector

**Files:**
- Modify: `frontend/src/features/catalogInspector/types.ts`
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorPage.tsx`
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorCanvas.tsx`
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx`
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx`

- [ ] **Step 1: Write the failing UI test**

```tsx
it('renders exact boundary graph overlays and selected boundary details', async () => {
  render(<CatalogInspectorPage data={fixture} />)

  expect(screen.getByRole('button', { name: /Exact boundaries/i })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /Exact boundaries/i }))
  await user.click(screen.getByText(/Boundary:/i))

  expect(screen.getByText(/Boundary kind/i)).toBeInTheDocument()
  expect(screen.getByText(/Source traces/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cmd /c npm --prefix frontend test -- src/features/catalogInspector/CatalogInspectorPage.test.tsx`
Expected: FAIL because exact boundary controls/details do not exist yet.

- [ ] **Step 3: Implement minimal UI wiring**

```tsx
const [showExactBoundaries, setShowExactBoundaries] = useState(false)
const [selectedBoundaryId, setSelectedBoundaryId] = useState<string | null>(null)
const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
```

```tsx
<ToggleButton pressed={showExactBoundaries} onPressedChange={setShowExactBoundaries}>
  Exact boundaries
</ToggleButton>
```

```tsx
{showExactBoundaries && boundaries.map((boundary) => (
  <ExactBoundaryOverlay key={boundary.boundary_id} ... />
))}
```

- [ ] **Step 4: Run UI tests to verify they pass**

Run: `cmd /c npm --prefix frontend test -- src/features/catalogInspector/CatalogInspectorPage.test.tsx src/App.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/catalogInspector/types.ts frontend/src/features/catalogInspector/CatalogInspectorPage.tsx frontend/src/features/catalogInspector/CatalogInspectorCanvas.tsx frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx
git commit -m "feat: show exact boundary graph in catalog inspector"
```

### Task 6: Document, verify, and hand off to the executor foundation

**Files:**
- Modify: `MVP.md`
- Modify: `docs/superpowers/specs/2026-04-22-exact-boundary-graph-v1-design.md`
- Modify: `D:\obsidian\vault\01 - Projects\Point.ai\Current State.md`
- Create: `D:\obsidian\vault\01 - Projects\Point.ai\Implementation\2026-04-22 - Exact boundary graph v1 implementation.md`

- [ ] **Step 1: Update docs with achieved metrics**

```md
- Exact boundary graph now derives canonical nodes and segments from raw wall traces.
- Seminole shared boundaries no longer rely on `bbox_inferred` provenance.
- Inspector can compare raw traces, wall graph, and exact boundaries.
```

- [ ] **Step 2: Run full verification suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_floor_plan_catalog_boundary_graph.py tests/test_floor_plan_catalog_wall_graph.py tests/test_floor_plan_catalog_opening_graph.py tests/test_floor_plan_catalog_topology.py tests/test_floor_plan_catalog_curator.py tests/test_floor_plan_catalog_audit.py -q`
Expected: PASS.

Run: `cmd /c npm --prefix frontend test -- src/App.test.tsx src/features/catalogInspector/CatalogInspectorPage.test.tsx`
Expected: PASS.

- [ ] **Step 3: Commit final verification/docs update**

```bash
git add MVP.md docs/superpowers/specs/2026-04-22-exact-boundary-graph-v1-design.md docs/superpowers/plans/2026-04-22-exact-boundary-graph-v1.md frontend/src/features/catalogInspector/catalogInspector.fixture.json tests/test_floor_plan_catalog_boundary_graph.py
# include any remaining files touched by the implementation
git commit -m "docs: record exact boundary graph v1 progress"
```

---

## Self-Review
- Spec coverage: the plan covers raw trace normalization, exact boundary graph, room reprojection through boundary ownership, inspector upgrade, and verification handoff.
- Placeholder scan: no TBD/TODO placeholders remain; every task includes file paths, code shape, and commands.
- Type consistency: names used consistently across tasks — `FloorPlanBoundaryGraphV1`, `CatalogBoundaryNode`, `CatalogBoundarySegment`, `derive_floor_plan_boundary_graph`.
