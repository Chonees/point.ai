# Wall Ownership V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Derivar ownership explícito de boundaries en `SEMINOLE2000` para que cada wall tenga tipo/owners claros y cada room sepa cuáles son sus paredes shared/exterior.

**Architecture:** Extender el `wall_graph` con metadata de ownership sin mentir geometría, y fortalecer la topología para exponer `owned_wall_ids` por room. El inspector temporal consumirá esa data para validar visualmente qué pared pertenece a quién antes de pasar a opening ownership o executor geométrico.

**Tech Stack:** Python 3.14, Pydantic models, pytest, React + TypeScript + Vitest, fixture JSON exportada desde `scripts/export_seminole_topology_fixture.py`.

---

### Task 1: Red tests para ownership de wall graph

**Files:**
- Modify: `tests/test_floor_plan_catalog_wall_graph.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_derive_floor_plan_wall_graph_assigns_boundary_kind_and_owner_room_ids():
    seed = build_seed()
    topology = derive_floor_plan_topology(seed)

    wall_graph = derive_floor_plan_wall_graph(topology, seed.cad_traces)
    walls = wall_graph.walls

    bedroom = next(room for room in topology.rooms if room.name == "BEDROOM 2")
    hall = next(room for room in topology.rooms if room.name == "HALL")
    shared_wall = next(
        wall
        for wall in walls
        if not wall.is_exterior and set(wall.room_ids) == {bedroom.room_id, hall.room_id}
    )

    assert shared_wall.boundary_kind == "shared"
    assert set(shared_wall.owner_room_ids) == {bedroom.room_id, hall.room_id}

    hall_exterior = next(
        wall
        for wall in walls
        if wall.is_exterior and wall.room_ids == [hall.room_id] and wall.orientation == "vertical"
    )
    assert hall_exterior.boundary_kind == "exterior"
    assert hall_exterior.owner_room_ids == [hall.room_id]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_wall_graph.py -q`

Expected: FAIL because `CatalogWallBoundary` does not expose `boundary_kind` / `owner_room_ids`.

- [ ] **Step 3: Write minimal implementation**

Add fields to `CatalogWallBoundary` and populate them from `derive_floor_plan_wall_graph(...)`:

```python
boundary_kind="shared"
owner_room_ids=list(pair_ids)
```

and for exterior:

```python
boundary_kind="exterior"
owner_room_ids=[room_id]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_wall_graph.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/floor_plan_catalog/contracts.py backend/floor_plan_catalog/wall_graph.py tests/test_floor_plan_catalog_wall_graph.py
git commit -m "feat: add wall boundary ownership metadata"
```

### Task 2: Red tests para ownership derivado por room

**Files:**
- Modify: `tests/test_floor_plan_catalog_topology.py`
- Modify: `backend/floor_plan_catalog/topology.py`
- Modify: `backend/floor_plan_catalog/contracts.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_strengthen_floor_plan_topology_assigns_owned_shared_and_exterior_wall_ids():
    seed = build_seed()
    topology = derive_floor_plan_topology(seed)
    wall_graph = derive_floor_plan_wall_graph(topology, seed.cad_traces)

    strengthened = strengthen_floor_plan_topology(topology, wall_graph, seed.cad_traces)
    room_by_name = {room.name: room for room in strengthened.rooms}

    bedroom = room_by_name["BEDROOM 2"]
    assert bedroom.owned_wall_ids
    assert bedroom.shared_wall_ids
    assert bedroom.exterior_wall_ids
    assert set(bedroom.shared_wall_ids).issubset(set(bedroom.owned_wall_ids))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_topology.py -q`

Expected: FAIL because `CatalogRoomTopology` does not expose owned/shared/exterior wall ids.

- [ ] **Step 3: Write minimal implementation**

Extend `CatalogRoomTopology`:

```python
owned_wall_ids: list[str] = Field(default_factory=list)
shared_wall_ids: list[str] = Field(default_factory=list)
exterior_wall_ids: list[str] = Field(default_factory=list)
```

Populate them inside `strengthen_floor_plan_topology(...)` by grouping `wall_graph.walls` through `owner_room_ids`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_topology.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/floor_plan_catalog/contracts.py backend/floor_plan_catalog/topology.py tests/test_floor_plan_catalog_topology.py
git commit -m "feat: derive room wall ownership"
```

### Task 3: Exponer ownership en la fixture y en el inspector

**Files:**
- Modify: `scripts/export_seminole_topology_fixture.py`
- Modify: `frontend/src/features/catalogInspector/types.ts`
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorPage.tsx`
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx`
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx`
- Modify: `frontend/src/features/catalogInspector/catalogInspector.fixture.json`

- [ ] **Step 1: Write the failing frontend test**

```tsx
it('shows wall ownership metadata in the selected wall and room panels', () => {
  render(<CatalogInspectorPage topology={fixture} />)

  fireEvent.click(screen.getByRole('button', { name: /^Shared$/i }))
  expect(screen.getByText(/boundary kind/i)).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: /select bedroom 2/i }))
  expect(screen.getByText(/owned walls/i)).toBeInTheDocument()
  expect(screen.getByText(/shared walls/i)).toBeInTheDocument()
  expect(screen.getByText(/exterior walls/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cmd /c npm --prefix frontend test -- src/features/catalogInspector/CatalogInspectorPage.test.tsx`

Expected: FAIL because fixture/types/UI do not expose ownership fields.

- [ ] **Step 3: Write minimal implementation**

Update payload export and UI:

```python
payload["walls"] = [wall.model_dump() for wall in wall_graph.walls]
```

```ts
boundary_kind: 'shared' | 'exterior' | string
owner_room_ids: string[]
owned_wall_ids: string[]
shared_wall_ids: string[]
exterior_wall_ids: string[]
```

Render in sidebar:
- selected wall: boundary kind + owner rooms
- selected room: owned/shared/exterior wall counts

- [ ] **Step 4: Regenerate fixture and run tests**

Run:

```bash
.\.venv\Scripts\python.exe scripts/export_seminole_topology_fixture.py D:\PointAIData\PLANS\catalog\seminole-2000.json --output frontend/src/features/catalogInspector/catalogInspector.fixture.json
cmd /c npm --prefix frontend test -- src/App.test.tsx src/features/catalogInspector/CatalogInspectorPage.test.tsx
```

Expected: PASS and fixture updated with ownership data.

- [ ] **Step 5: Commit**

```bash
git add scripts/export_seminole_topology_fixture.py frontend/src/features/catalogInspector/types.ts frontend/src/features/catalogInspector/CatalogInspectorPage.tsx frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx frontend/src/features/catalogInspector/catalogInspector.fixture.json
git commit -m "feat: expose wall ownership in topology inspector"
```

### Task 4: Verificación final + docs

**Files:**
- Modify: `MVP.md`
- Modify: `D:\obsidian\vault\01 - Projects\Point.ai\Current State.md`
- Create: `D:\obsidian\vault\01 - Projects\Point.ai\Implementation\2026-04-22 - Wall ownership v1.md`

- [ ] **Step 1: Run backend verification**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_curator.py tests/test_floor_plan_catalog_topology.py tests/test_floor_plan_catalog_wall_graph.py tests/test_floor_plan_catalog_audit.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend verification**

Run:

```bash
cmd /c npm --prefix frontend test -- src/App.test.tsx src/features/catalogInspector/CatalogInspectorPage.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Document the slice**

Record:
- what ownership fields were added
- why `left/right_room_id` was intentionally avoided if ambiguous
- how to inspect ownership visually in `?debug=seminole-topology`

- [ ] **Step 4: Commit**

```bash
git add MVP.md "D:\obsidian\vault\01 - Projects\Point.ai\Current State.md" "D:\obsidian\vault\01 - Projects\Point.ai\Implementation\2026-04-22 - Wall ownership v1.md"
git commit -m "docs: record wall ownership v1"
```
