# Mutability / Constraints v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a conservative, auditable mutability layer over rooms, boundaries, walls, and openings so the catalog becomes executor-prep instead of analysis-only.

**Architecture:** Extend the existing catalog contracts with mutability/constraint fields, derive them in a dedicated `mutability.py` module from the already-clean topology + wall + opening + boundary graphs, and surface the result in the inspector. Encode only an IRC-informed executor subset first: egress, sleeping-room rescue openings, garage separation, wet core, circulation, and conservative room minimums. Keep this slice structural only: no site-fit mutations yet.

**Tech Stack:** Python, pytest, Pydantic models, React, Vitest, JSON fixture export.

---

## File Structure

### Existing files to modify
- `backend/floor_plan_catalog/contracts.py` — add mutability/constraint fields to rooms, walls, boundaries, and openings.
- `scripts/export_seminole_topology_fixture.py` — run mutability derivation before exporting the payload.
- `frontend/src/features/catalogInspector/types.ts` — expose new mutability fields.
- `frontend/src/features/catalogInspector/CatalogInspectorPage.tsx` — render summary metrics.
- `frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx` — render mutability/rehost details for selected room, wall, boundary, and opening.
- `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx` — cover new metrics / labels.
- `frontend/src/features/catalogInspector/catalogInspector.fixture.json` — refreshed real fixture after backend derivation.

### New files to create
- `backend/floor_plan_catalog/mutability.py` — conservative derivation rules for room/boundary/wall/opening mutability.
- `tests/test_floor_plan_catalog_mutability.py` — focused RED/GREEN coverage for the new derivation layer.

### Existing files to read during implementation
- `backend/floor_plan_catalog/topology.py`
- `backend/floor_plan_catalog/wall_graph.py`
- `backend/floor_plan_catalog/opening_graph.py`
- `backend/floor_plan_catalog/boundary_graph.py`
- `backend/floor_plan_catalog/contracts.py`

### Current verified baseline (must not regress)
- `boundary kinds = { duplicate: 404, exterior: 182, artifact: 106, support: 40, unknown: 14, shared: 10 }`
- `opening confidence = { hosted: 70, opening_artifact: 47, unhosted: 4 }`
- `topology_issues = []`
- `wall_graph_issues = []`

### Code-informed baseline for this plan
- Treat ICC/IRC as **model code baseline**, not final jurisdictional truth.
- Use **IRC 2021** as the conservative default subset for executor-prep logic.
- Only encode constraints we can actually operationalize with current geometry:
  - required egress door
  - sleeping-room rescue/egress openings
  - garage/dwelling separation
  - wet core protection
  - critical circulation (`entry`, `hall`)
  - habitable room minimum area / width floors
- Explicitly defer what current data cannot support honestly:
  - ceiling-height compliance
  - full fixture clearance logic
  - structural span engineering

---

### Task 1: Lock the mutability contract with RED tests

**Files:**
- Create: `tests/test_floor_plan_catalog_mutability.py`
- Read: `backend/floor_plan_catalog/contracts.py`
- Read: `backend/floor_plan_catalog/opening_graph.py`

- [ ] **Step 1: Write a failing synthetic test for room-level mutability mapping**

```python
def test_derive_floor_plan_mutability_classifies_room_categories_conservatively():
    seed = build_seed_with_hostable_openings().model_copy(
        update={
            "rooms": [
                build_room("KITCHEN", 0, 0, 120, 120),
                build_room("MASTER BATH", 120, 0, 220, 120),
                build_room("ENTRY", 0, 120, 80, 200),
                build_room("LIVING ROOM", 80, 120, 220, 260),
                build_room("PATIO", 0, 260, 120, 320),
            ]
        }
    )
    topology = derive_floor_plan_topology(seed)
    boundary_graph = derive_floor_plan_boundary_graph(seed)
    wall_graph = derive_floor_plan_wall_graph(topology, seed.cad_traces, boundary_graph=boundary_graph)
    opening_graph = derive_floor_plan_opening_graph(topology, wall_graph, seed.cad_traces)

    topology, wall_graph, opening_graph, boundary_graph = derive_floor_plan_mutability(
        topology, wall_graph, opening_graph, boundary_graph
    )

    rooms = {room.name: room for room in topology.rooms}

    assert rooms["KITCHEN"].mutability == "protected"
    assert rooms["KITCHEN"].is_wet_zone is True
    assert rooms["MASTER BATH"].mutability == "protected"
    assert rooms["ENTRY"].mutability == "protected"
    assert rooms["LIVING ROOM"].mutability == "flexible"
    assert rooms["PATIO"].mutability == "locked"
    assert "wet_core" in rooms["KITCHEN"].constraint_reasons
```

- [ ] **Step 2: Write a failing synthetic test for boundary/wall/opening mutability**

```python
def test_derive_floor_plan_mutability_marks_boundaries_and_openings_for_executor_use():
    seed = build_seed_with_hostable_openings()
    topology = derive_floor_plan_topology(seed)
    boundary_graph = derive_floor_plan_boundary_graph(seed)
    wall_graph = derive_floor_plan_wall_graph(topology, seed.cad_traces, boundary_graph=boundary_graph)
    opening_graph = derive_floor_plan_opening_graph(topology, wall_graph, seed.cad_traces)

    topology, wall_graph, opening_graph, boundary_graph = derive_floor_plan_mutability(
        topology, wall_graph, opening_graph, boundary_graph
    )

    boundaries = {boundary.boundary_id: boundary for boundary in boundary_graph.boundaries}
    walls = {wall.wall_id: wall for wall in wall_graph.walls}
    openings = {opening.opening_id: opening for opening in opening_graph.openings}

    assert any(boundary.mutability == "movable" for boundary in boundaries.values() if boundary.boundary_kind == "exterior")
    assert any(boundary.mutability == "movable_with_rehost" for boundary in boundaries.values() if boundary.opening_ids)
    assert all(boundary.mutability == "derived_only" for boundary in boundaries.values() if boundary.boundary_kind in {"duplicate", "artifact", "support"})
    assert any(wall.mutability in {"movable", "movable_with_rehost"} for wall in walls.values())
    assert any(opening.rehost_required is True for opening in openings.values() if opening.confidence == "hosted")
    assert all(opening.rehostable is False for opening in openings.values() if opening.confidence == "opening_artifact")
```

- [ ] **Step 3: Write a failing synthetic test for the IRC-informed hard locks**

```python
def test_derive_floor_plan_mutability_protects_code_informed_boundaries_and_openings():
    seed = build_seed_with_hostable_openings()
    topology = derive_floor_plan_topology(seed)
    boundary_graph = derive_floor_plan_boundary_graph(seed)
    wall_graph = derive_floor_plan_wall_graph(topology, seed.cad_traces, boundary_graph=boundary_graph)
    opening_graph = derive_floor_plan_opening_graph(topology, wall_graph, seed.cad_traces)

    topology, wall_graph, opening_graph, boundary_graph = derive_floor_plan_mutability(
        topology, wall_graph, opening_graph, boundary_graph
    )

    garage_boundaries = [
        boundary for boundary in boundary_graph.boundaries
        if boundary.boundary_kind in {"shared", "exterior"} and "garage_separation" in boundary.constraint_reasons
    ]
    bedroom_egress_openings = [
        opening for opening in opening_graph.openings
        if "required_egress_opening" in opening.constraint_reasons
    ]
    egress_door_openings = [
        opening for opening in opening_graph.openings
        if "required_egress_door" in opening.constraint_reasons
    ]

    assert garage_boundaries
    assert all(boundary.mutability == "protected" for boundary in garage_boundaries)
    assert bedroom_egress_openings
    assert all(opening.rehostable is False for opening in bedroom_egress_openings)
    assert egress_door_openings
    assert all(opening.rehostable is False for opening in egress_door_openings)
```

- [ ] **Step 4: Write a failing real Seminole regression test**

```python
def test_derive_floor_plan_mutability_covers_real_seminole_without_structural_regression():
    seed_payload = json.loads(Path(r"D:\PointAIData\PLANS\catalog\seminole-2000.json").read_text(encoding="utf-8"))
    seed = FloorPlanCatalogSeed.model_validate(seed_payload)
    topology = derive_floor_plan_topology(seed)
    boundary_graph = derive_floor_plan_boundary_graph(seed)
    wall_graph = derive_floor_plan_wall_graph(topology, seed.cad_traces, boundary_graph=boundary_graph)
    opening_graph = derive_floor_plan_opening_graph(topology, wall_graph, seed.cad_traces)

    topology, wall_graph, opening_graph, boundary_graph = derive_floor_plan_mutability(
        topology, wall_graph, opening_graph, boundary_graph
    )

    assert all(room.mutability in {"flexible", "protected", "locked"} for room in topology.rooms)
    assert all(boundary.mutability != "unknown" for boundary in boundary_graph.boundaries if boundary.boundary_kind in {"shared", "exterior", "duplicate", "artifact", "support"})
    assert all(wall.mutability != "unknown" for wall in wall_graph.walls)
    assert all(opening.rehostable is False for opening in opening_graph.openings if opening.confidence == "opening_artifact")
    assert any("required_egress_door" in opening.constraint_reasons for opening in opening_graph.openings)
    assert any("garage_separation" in boundary.constraint_reasons for boundary in boundary_graph.boundaries)

    boundary_kinds = Counter(boundary.boundary_kind for boundary in boundary_graph.boundaries)
    assert boundary_kinds["shared"] == 10
    assert boundary_kinds["exterior"] == 182
    assert boundary_kinds["support"] == 40
    assert boundary_kinds["unknown"] == 14
```

- [ ] **Step 5: Run the new mutability test file and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_mutability.py -q
```

Expected: FAIL because `derive_floor_plan_mutability` and the new contract fields do not exist yet.

- [ ] **Step 6: Commit the failing tests**

```bash
git add tests/test_floor_plan_catalog_mutability.py
git commit -m "test: cover mutability constraints"
```

---

### Task 2: Extend contracts and implement conservative derivation

**Files:**
- Modify: `backend/floor_plan_catalog/contracts.py`
- Create: `backend/floor_plan_catalog/mutability.py`

- [ ] **Step 1: Extend the contracts with explicit mutability fields**

```python
class CatalogRoomTopology(BaseModel):
    ...
    is_wet_zone: bool = False
    is_core: bool = False
    mutability: str = "unknown"
    min_width: float | None = None
    min_height: float | None = None
    min_area: float | None = None
    constraint_reasons: list[str] = Field(default_factory=list)

class CatalogWallBoundary(BaseModel):
    ...
    movable: bool = False
    mutability: str = "unknown"
    structural_unknown: bool = False
    constraint_reasons: list[str] = Field(default_factory=list)

class CatalogOpening(BaseModel):
    ...
    rehost_required: bool = False
    rehostable: bool = False
    constraint_reasons: list[str] = Field(default_factory=list)

class CatalogBoundarySegment(BaseModel):
    ...
    movable: bool = False
    mutability: str = "unknown"
    constraint_reasons: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: Create `backend/floor_plan_catalog/mutability.py` with conservative room rules**

```python
ROOM_RULES = {
    "bath": {"is_wet_zone": True, "is_core": True, "mutability": "protected"},
    "powder_room": {"is_wet_zone": True, "is_core": True, "mutability": "protected"},
    "kitchen": {"is_wet_zone": True, "is_core": True, "mutability": "protected"},
    "utility": {"is_wet_zone": True, "is_core": True, "mutability": "protected"},
    "entry": {"is_core": True, "mutability": "protected"},
    "hall": {"is_core": True, "mutability": "protected"},
    "closet": {"is_core": True, "mutability": "protected"},
    "patio": {"mutability": "locked"},
    "porch": {"mutability": "locked"},
}
```

Use a helper like:

```python
def _derive_room_constraints(room: CatalogRoomTopology) -> CatalogRoomTopology:
    ...
```

- [ ] **Step 3: Add conservative minimum geometry helpers**

```python
def _derive_room_minimums(room: CatalogRoomTopology, mutability: str) -> tuple[float | None, float | None, float | None]:
    if mutability in {"locked", "protected"}:
        return (room.width, room.height, room.area)

    width_floor = 96.0 if room.category in {"garage", "living_room", "dining"} else 84.0
    height_floor = 96.0 if room.category in {"bedroom", "living_room"} else 72.0
    area_floor = 9000.0 if room.category == "bedroom" else 6400.0

    return (
        round(max(width_floor, 84.0, room.width * 0.85), 3),
        round(max(height_floor, room.height * 0.85), 3),
        round(max(area_floor, 10080.0 if room.category != "kitchen" else 0.0, room.area * 0.8), 3),
    )
```

- [ ] **Step 4: Encode the IRC-informed special cases in helpers**

```python
def _is_required_egress_door(opening: CatalogOpening, rooms_by_id: dict[str, CatalogRoomTopology]) -> bool:
    return (
        opening.opening_kind == "door"
        and any(rooms_by_id.get(room_id) and rooms_by_id[room_id].category == "entry" for room_id in opening.owner_room_ids)
        and len(opening.connected_room_ids) == 1
    )

def _is_required_bedroom_egress_opening(opening: CatalogOpening, rooms_by_id: dict[str, CatalogRoomTopology], boundaries_by_id: dict[str, CatalogBoundarySegment]) -> bool:
    host_boundary = boundaries_by_id.get(opening.host_wall_id or "")
    return (
        opening.opening_kind == "window"
        and host_boundary is not None
        and host_boundary.boundary_kind == "exterior"
        and any(rooms_by_id.get(room_id) and rooms_by_id[room_id].category == "bedroom" for room_id in opening.owner_room_ids)
    )

def _is_garage_separation(boundary: CatalogBoundarySegment, rooms_by_id: dict[str, CatalogRoomTopology]) -> bool:
    categories = {rooms_by_id[room_id].category for room_id in boundary.owner_room_ids if room_id in rooms_by_id}
    return "garage" in categories and len(categories - {"garage"}) > 0
```

- [ ] **Step 5: Derive boundary mutability from canonical kind + room mutability + openings**

```python
def _derive_boundary_constraints(boundary: CatalogBoundarySegment, rooms_by_id: dict[str, CatalogRoomTopology], opening_ids: set[str]) -> CatalogBoundarySegment:
    if boundary.boundary_kind in {"duplicate", "artifact", "support"}:
        return boundary.model_copy(update={"movable": False, "mutability": "derived_only", "constraint_reasons": ["non_canonical_boundary"]})

    room_mutabilities = {rooms_by_id[room_id].mutability for room_id in boundary.owner_room_ids if room_id in rooms_by_id}

    reasons = []
    if _is_garage_separation(boundary, rooms_by_id):
        mutability = "protected"
        reasons.append("garage_separation")
    elif "locked" in room_mutabilities:
        mutability = "locked"
    elif "protected" in room_mutabilities:
        mutability = "protected"
    elif boundary.opening_ids or (opening_ids & set(boundary.opening_ids)):
        mutability = "movable_with_rehost"
    else:
        mutability = "movable"

    return boundary.model_copy(
        update={
            "movable": mutability in {"movable", "movable_with_rehost"},
            "mutability": mutability,
            "constraint_reasons": _boundary_reasons(boundary, room_mutabilities, mutability) + reasons,
        }
    )
```

- [ ] **Step 6: Reflect boundary mutability onto walls and openings**

```python
def _derive_wall_constraints(wall: CatalogWallBoundary, rooms_by_id: dict[str, CatalogRoomTopology], openings_by_host_wall: dict[str, list[CatalogOpening]]) -> CatalogWallBoundary:
    ...

def _derive_opening_constraints(opening: CatalogOpening, walls_by_id: dict[str, CatalogWallBoundary], boundaries_by_id: dict[str, CatalogBoundarySegment], rooms_by_id: dict[str, CatalogRoomTopology]) -> CatalogOpening:
    ...
```

Required behavior:

- `required_egress_door` → `rehost_required = False`, `rehostable = False`, reason appended
- `required_egress_opening` → `rehost_required = False`, `rehostable = False`, reason appended
- `opening_artifact` / `unhosted` → `rehostable = False`
- hosted opening on `movable_with_rehost` / `movable` wall → `rehost_required = True`, `rehostable = True`

- [ ] **Step 7: Expose the public derivation entrypoint**

```python
def derive_floor_plan_mutability(
    topology: FloorPlanTopologyV1,
    wall_graph: FloorPlanWallGraphV1,
    opening_graph: FloorPlanOpeningGraphV1,
    boundary_graph: FloorPlanBoundaryGraphV1,
) -> tuple[FloorPlanTopologyV1, FloorPlanWallGraphV1, FloorPlanOpeningGraphV1, FloorPlanBoundaryGraphV1]:
    ...
```

- [ ] **Step 8: Run the mutability tests and confirm GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_mutability.py -q
```

Expected: PASS

- [ ] **Step 9: Commit the backend implementation**

```bash
git add backend/floor_plan_catalog/contracts.py backend/floor_plan_catalog/mutability.py
git commit -m "feat: derive floor plan mutability constraints"
```

---

### Task 3: Thread mutability through fixture export and the real Seminole payload

**Files:**
- Modify: `scripts/export_seminole_topology_fixture.py`
- Modify: `frontend/src/features/catalogInspector/catalogInspector.fixture.json`

- [ ] **Step 1: Run mutability derivation during fixture export**

```python
from backend.floor_plan_catalog.mutability import derive_floor_plan_mutability

boundary_graph = derive_floor_plan_boundary_graph(seed)
topology = derive_floor_plan_topology(seed)
wall_graph = derive_floor_plan_wall_graph(topology, seed.cad_traces, boundary_graph=boundary_graph)
opening_graph = derive_floor_plan_opening_graph(topology, wall_graph, seed.cad_traces)
topology = strengthen_floor_plan_topology(topology, wall_graph, seed.cad_traces, opening_graph)
topology, wall_graph, opening_graph, boundary_graph = derive_floor_plan_mutability(topology, wall_graph, opening_graph, boundary_graph)
```

- [ ] **Step 2: Regenerate the real fixture**

Run:

```powershell
.\.venv\Scripts\python.exe scripts/export_seminole_topology_fixture.py D:\PointAIData\PLANS\catalog\seminole-2000.json --output frontend/src/features/catalogInspector/catalogInspector.fixture.json
```

Expected: fixture path printed successfully.

- [ ] **Step 3: Audit the fixture for mutability coverage**

Run:

```powershell
@'
import json
from collections import Counter
from pathlib import Path
p = Path("frontend/src/features/catalogInspector/catalogInspector.fixture.json")
data = json.loads(p.read_text())
print("room_mutability", Counter(room["mutability"] for room in data["rooms"]))
print("wall_mutability", Counter(wall["mutability"] for wall in data["walls"]))
print("boundary_mutability", Counter(boundary["mutability"] for boundary in data["boundaries"]))
print("opening_rehost_required", Counter((opening["confidence"], opening["rehost_required"]) for opening in data["openings"]))
'@ | .\.venv\Scripts\python.exe -
```

Expected:
- all rooms have non-`unknown` mutability
- all shared/exterior boundaries have non-`unknown` mutability
- `opening_artifact` stays non-rehostable
- at least one opening carries `required_egress_door`
- at least one boundary carries `garage_separation`

- [ ] **Step 4: Commit the fixture/export changes**

```bash
git add scripts/export_seminole_topology_fixture.py frontend/src/features/catalogInspector/catalogInspector.fixture.json
git commit -m "chore: export mutability constraints fixture"
```

---

### Task 4: Surface the constraint layer honestly in the inspector

**Files:**
- Modify: `frontend/src/features/catalogInspector/types.ts`
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorPage.tsx`
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx`
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx`

- [ ] **Step 1: Add a failing UI test for new mutability metrics**

```tsx
it('renders mutability metrics from the fixture', () => {
  render(<CatalogInspectorPage topology={fixture} />)

  expect(screen.getByText(/^Flexible rooms$/i)).toBeInTheDocument()
  expect(screen.getByText(/^Protected rooms$/i)).toBeInTheDocument()
  expect(screen.getByText(/^Locked rooms$/i)).toBeInTheDocument()
  expect(screen.getByText(/^Movable boundaries$/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Add a failing UI test for sidebar constraint details**

```tsx
it('shows mutability and constraint reasons for selected room, wall, boundary, and opening', () => {
  render(<CatalogInspectorPage topology={fixture} />)

  fireEvent.click(screen.getByRole('button', { name: /select kitchen/i }))
  expect(screen.getByText(/mutability/i)).toBeInTheDocument()
  expect(screen.getByText(/constraint reasons/i)).toBeInTheDocument()
})
```

- [ ] **Step 3: Run the focused frontend test and confirm RED**

Run from `frontend/`:

```powershell
npx vitest run --config vitest.config.ts src/features/catalogInspector/CatalogInspectorPage.test.tsx --pool=threads
```

Expected: FAIL on missing mutability UI.

- [ ] **Step 4: Extend types and render the new metrics**

```ts
export interface CatalogInspectorRoom {
  ...
  is_wet_zone: boolean
  is_core: boolean
  mutability: string
  min_width?: number | null
  min_height?: number | null
  min_area?: number | null
  constraint_reasons: string[]
}
```

```tsx
const flexibleRoomCount = topology.rooms.filter((room) => room.mutability === 'flexible').length
const protectedRoomCount = topology.rooms.filter((room) => room.mutability === 'protected').length
const lockedRoomCount = topology.rooms.filter((room) => room.mutability === 'locked').length
const movableBoundaryCount = boundaries.filter((boundary) => boundary.mutability === 'movable').length
const movableWithRehostBoundaryCount = boundaries.filter((boundary) => boundary.mutability === 'movable_with_rehost').length
```

- [ ] **Step 5: Render mutability/rehost details in the sidebar**

```tsx
<p className="mt-1 text-zinc-100">{selectedRoom.mutability}</p>
<p className="mt-1 text-zinc-100">{selectedRoom.constraint_reasons.join(', ') || 'None'}</p>
...
<p className="mt-1 text-zinc-100">{selectedBoundary.mutability}</p>
<p className="mt-1 text-zinc-100">{selectedOpening.rehost_required ? 'Yes' : 'No'}</p>
<p className="mt-1 text-zinc-100">{selectedOpening.constraint_reasons.join(', ') || 'None'}</p>
```

- [ ] **Step 6: Run the focused frontend test and confirm GREEN**

Run from `frontend/`:

```powershell
npx vitest run --config vitest.config.ts src/features/catalogInspector/CatalogInspectorPage.test.tsx --pool=threads
```

Expected: PASS

- [ ] **Step 7: Commit the UI changes**

```bash
git add frontend/src/features/catalogInspector/types.ts frontend/src/features/catalogInspector/CatalogInspectorPage.tsx frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx
git commit -m "feat: surface mutability constraints in inspector"
```

---

### Task 5: Full verification and documentation

**Files:**
- Modify: `D:\obsidian\vault\01 - Projects\Point.ai\Current State.md`
- Create/Modify: `D:\obsidian\vault\01 - Projects\Point.ai\Implementation\2026-04-23 - Mutability constraints v1.md`

- [ ] **Step 1: Run the full backend verification suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_boundary_graph.py tests/test_floor_plan_catalog_wall_graph.py tests/test_floor_plan_catalog_opening_graph.py tests/test_floor_plan_catalog_mutability.py tests/test_floor_plan_catalog_topology.py tests/test_floor_plan_catalog_curator.py tests/test_floor_plan_catalog_audit.py -q
```

Expected: PASS

- [ ] **Step 2: Run the frontend verification suite from `frontend/`**

Run:

```powershell
npx vitest run --config vitest.config.ts src/App.test.tsx src/features/catalogInspector/CatalogInspectorPage.test.tsx --pool=threads
```

Expected: PASS

- [ ] **Step 3: Verify the visual route still loads**

Run:

```powershell
cmd /c curl -I http://localhost:5173/?debug=seminole-topology
```

Expected: `HTTP/1.1 200 OK`

- [ ] **Step 4: Update Obsidian with the verified result**

```md
## 2026-04-23 - Mutability / Constraints v1
- Added conservative room, wall, boundary, and opening mutability constraints.
- Rooms now expose `flexible / protected / locked` plus minimum geometry.
- Boundaries now expose `movable / movable_with_rehost / protected / locked / derived_only`.
- Openings now expose `rehost_required` / `rehostable`.
- The first code-informed subset now explicitly protects egress door, sleeping-room rescue openings, garage separation, wet core, and critical circulation.
```

- [ ] **Step 5: Final cleanliness check**

Run:

```powershell
git status --short
```

Expected: no output

---

## Self-Review

### Spec coverage
- Room mutability: Task 2
- Boundary/wall mutability: Task 2
- Opening rehost flags: Task 2
- Code-informed egress / garage separation rules: Tasks 1-2
- Fixture export: Task 3
- Inspector surfacing: Task 4
- Final verification + docs: Task 5

### Placeholder scan
- No `TODO`, `TBD`, or “handle appropriately” placeholders remain.
- All code-touching steps include file paths and concrete snippets.

### Type consistency
- Uses one consistent vocabulary across the plan: `flexible | protected | locked` for rooms, `movable | movable_with_rehost | protected | locked | derived_only` for boundaries/walls, and `rehost_required / rehostable` for openings.
