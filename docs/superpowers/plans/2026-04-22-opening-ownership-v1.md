# Opening Ownership V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Derivar openings hosteadas sobre walls reales del catálogo para separar `door/window` como entidades operables y eliminar la heurística remanente `ENTRY ↔ LIVING ROOM`.

**Architecture:** Crear un `opening_graph` que tome `cad_traces` + `wall_graph`, hostee openings contra walls compatibles, agregue ownership/conectividad por opening y permita que `strengthen_floor_plan_topology(...)` deje de depender de heurísticas bbox cuando ya existe evidencia de wall/opening ownership.

**Tech Stack:** Python 3.14, Pydantic, pytest, React + TypeScript + Vitest, fixture JSON exportada por script.

---

### Task 1: Red tests para opening graph

**Files:**
- Create: `tests/test_floor_plan_catalog_opening_graph.py`
- Modify: `backend/floor_plan_catalog/contracts.py`
- Create: `backend/floor_plan_catalog/opening_graph.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_derive_floor_plan_opening_graph_hosts_door_and_window_traces():
    seed = build_seed_with_hostable_openings()
    topology = derive_floor_plan_topology(seed)
    wall_graph = derive_floor_plan_wall_graph(topology, seed.cad_traces)

    opening_graph = derive_floor_plan_opening_graph(topology, wall_graph, seed.cad_traces)

    assert opening_graph.openings
    assert any(opening.host_wall_id for opening in opening_graph.openings)
    assert any(opening.opening_kind == "door" for opening in opening_graph.openings)
    assert any(opening.opening_kind == "window" for opening in opening_graph.openings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_opening_graph.py -q`

Expected: FAIL because `opening_graph` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add:
- `CatalogOpening`
- `FloorPlanOpeningGraphV1`
- `derive_floor_plan_opening_graph(...)`

with fields:

```python
opening_id
opening_kind
host_wall_id
owner_room_ids
connected_room_ids
trace_ids
orientation
offset
span
confidence
issues
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_opening_graph.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/floor_plan_catalog/contracts.py backend/floor_plan_catalog/opening_graph.py tests/test_floor_plan_catalog_opening_graph.py
git commit -m "feat: derive opening ownership graph"
```

### Task 2: Reemplazar opening adjacency cruda por opening ownership

**Files:**
- Modify: `backend/floor_plan_catalog/topology.py`
- Modify: `tests/test_floor_plan_catalog_topology.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_strengthen_real_seminole_topology_uses_hosted_openings_and_drops_remaining_heuristics():
    seed = FloorPlanCatalogSeed.model_validate(...)
    topology = derive_floor_plan_topology(seed)
    wall_graph = derive_floor_plan_wall_graph(topology, seed.cad_traces)
    opening_graph = derive_floor_plan_opening_graph(topology, wall_graph, seed.cad_traces)

    strengthened = strengthen_floor_plan_topology(topology, wall_graph, opening_graph=opening_graph)
    rooms_by_name = {room.name: room for room in strengthened.rooms}

    assert rooms_by_name["ENTRY"].heuristic_adjacent_room_ids == []
    assert rooms_by_name["LIVING ROOM"].heuristic_adjacent_room_ids == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_topology.py -q`

Expected: FAIL because `strengthen_floor_plan_topology(...)` does not consume opening graph.

- [ ] **Step 3: Write minimal implementation**

Change the signature:

```python
def strengthen_floor_plan_topology(
    topology: FloorPlanTopologyV1,
    wall_graph: FloorPlanWallGraphV1,
    cad_traces: list[CatalogCadTrace] | None = None,
    opening_graph: FloorPlanOpeningGraphV1 | None = None,
) -> FloorPlanTopologyV1:
```

Rules:
- if `opening_graph` exists, opening adjacency comes from hosted openings
- once ownership evidence exists, residual bbox heuristic adjacency is dropped from canonical topology

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_topology.py tests/test_floor_plan_catalog_opening_graph.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/floor_plan_catalog/topology.py tests/test_floor_plan_catalog_topology.py
git commit -m "feat: use opening ownership for topology connectivity"
```

### Task 3: Exponer openings hosteadas en fixture e inspector

**Files:**
- Modify: `scripts/export_seminole_topology_fixture.py`
- Modify: `frontend/src/features/catalogInspector/types.ts`
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorPage.tsx`
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorCanvas.tsx`
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx`
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx`
- Modify: `frontend/src/features/catalogInspector/catalogInspector.fixture.json`

- [ ] **Step 1: Write the failing frontend test**

```tsx
it('renders hosted openings and highlights host wall ownership', () => {
  render(<CatalogInspectorPage topology={fixture} />)

  expect(screen.getByText(/hosted openings/i)).toBeInTheDocument()
  expect(screen.getAllByTestId(/^opening-/).length).toBeGreaterThan(0)
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cmd /c npm --prefix frontend test -- src/features/catalogInspector/CatalogInspectorPage.test.tsx`

Expected: FAIL because openings are not in the payload/UI.

- [ ] **Step 3: Write minimal implementation**

Export payload with:

```python
payload["openings"] = [opening.model_dump() for opening in opening_graph.openings]
payload["opening_graph_readiness"] = opening_graph.opening_graph_readiness.model_dump()
payload["opening_graph_issues"] = opening_graph.opening_graph_issues
```

Frontend:
- add `CatalogInspectorOpening`
- render derived openings on canvas
- show selected opening in sidebar with:
  - `opening_id`
  - `opening_kind`
  - `host_wall_id`
  - owner rooms
  - connected rooms
  - confidence

- [ ] **Step 4: Regenerate fixture and run tests**

Run:

```bash
.\.venv\Scripts\python.exe scripts/export_seminole_topology_fixture.py D:\PointAIData\PLANS\catalog\seminole-2000.json --output frontend/src/features/catalogInspector/catalogInspector.fixture.json
cmd /c npm --prefix frontend test -- src/App.test.tsx src/features/catalogInspector/CatalogInspectorPage.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/export_seminole_topology_fixture.py frontend/src/features/catalogInspector/types.ts frontend/src/features/catalogInspector/CatalogInspectorPage.tsx frontend/src/features/catalogInspector/CatalogInspectorCanvas.tsx frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx frontend/src/features/catalogInspector/catalogInspector.fixture.json
git commit -m "feat: expose hosted openings in topology inspector"
```

### Task 4: Verification + docs

**Files:**
- Modify: `MVP.md`
- Modify: `D:\obsidian\vault\01 - Projects\Point.ai\Current State.md`
- Create: `D:\obsidian\vault\01 - Projects\Point.ai\Implementation\2026-04-22 - Opening ownership v1.md`

- [ ] **Step 1: Run backend verification**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_curator.py tests/test_floor_plan_catalog_topology.py tests/test_floor_plan_catalog_wall_graph.py tests/test_floor_plan_catalog_opening_graph.py tests/test_floor_plan_catalog_audit.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend verification**

Run:

```bash
cmd /c npm --prefix frontend test -- src/App.test.tsx src/features/catalogInspector/CatalogInspectorPage.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Document**

Record:
- how openings are hosted
- why canonical topology dropped residual heuristics once wall/opening ownership existed
- what still remains before executor

- [ ] **Step 4: Commit**

```bash
git add MVP.md "D:\obsidian\vault\01 - Projects\\Point.ai\\Current State.md" "D:\obsidian\vault\01 - Projects\\Point.ai\\Implementation\\2026-04-22 - Opening ownership v1.md"
git commit -m "docs: record opening ownership v1"
```
