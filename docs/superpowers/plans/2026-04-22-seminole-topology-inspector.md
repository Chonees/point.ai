# Seminole Topology Inspector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Derivar una `Topology V1` real para `SEMINOLE2000` y montar una screen temporal de inspección visual que permita validar rooms, IDs, categorías, adjacency, exterior-touch e issues antes de avanzar al executor geométrico.

**Architecture:** El slice se divide en dos bounded contexts coordinados. En backend, `backend/floor_plan_catalog/topology.py` toma el `FloorPlanCatalogSeed` actual y deriva un `FloorPlanTopologyV1` con `room_id` estable, categoría, relaciones e issues. En frontend, una feature temporal `catalogInspector/` consume una fixture real exportada desde esa topología y la renderiza como plano real con inspector lateral y toggles de capas. La pantalla queda accesible por una entrada temporal explícita y removible, sin contaminar el flujo final del producto.

**Tech Stack:** Python, pydantic, pytest, existing `backend.floor_plan_catalog`, TypeScript, React 19, Vitest, Testing Library.

---

## File Structure

### New files
- `backend/floor_plan_catalog/topology.py` — derivación `FloorPlanTopologyV1` desde un `FloorPlanCatalogSeed`.
- `tests/test_floor_plan_catalog_topology.py` — tests de `room_id`, categoría, adjacency, exterior-touch e issues.
- `scripts/export_seminole_topology_fixture.py` — script offline que deriva topología real y la vuelca a fixture consumible por frontend.
- `frontend/src/features/catalogInspector/types.ts` — contratos TS del inspector temporal.
- `frontend/src/features/catalogInspector/catalogInspector.fixture.json` — fixture real exportada desde `SEMINOLE2000`.
- `frontend/src/features/catalogInspector/CatalogInspectorCanvas.tsx` — render del plano real con layers/toggles.
- `frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx` — panel lateral con detalle del room seleccionado.
- `frontend/src/features/catalogInspector/CatalogInspectorPage.tsx` — shell temporal completa del inspector.
- `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx` — tests de render e interacción del inspector.

### Existing files to modify
- `backend/floor_plan_catalog/contracts.py` — extender con modelos topológicos o re-exportar los nuevos desde `topology.py`.
- `frontend/src/App.tsx` — agregar entrada temporal explícita al inspector sin mezclarla con el producto final.
- `frontend/src/App.test.tsx` — cubrir la entrada temporal si se modifica el shell.
- `docs/superpowers/specs/2026-04-22-seminole-topology-inspector-design.md` — solo si al ejecutar aparece alguna contradicción que exija corrección menor.

---

### Task 1: Definir contratos `FloorPlanTopologyV1` y escribir tests rojos de derivación

**Files:**
- Create: `tests/test_floor_plan_catalog_topology.py`
- Modify: `backend/floor_plan_catalog/contracts.py`

- [ ] **Step 1: Write the failing topology contract + inference tests**

```python
from backend.floor_plan_catalog.contracts import CatalogBBox, CatalogPoint, CatalogReadiness, CatalogRoom, FloorPlanCatalogSeed
from backend.floor_plan_catalog.topology import derive_floor_plan_topology


def build_seed() -> FloorPlanCatalogSeed:
    return FloorPlanCatalogSeed(
        floor_plan_id="seminole-2000",
        name="SEMINOLE2000",
        source_path="D:/PointAIData/PLANS/originalFloorPlans/SEMINOLE2000.dxf",
        canonical_unit="inch",
        footprint_bbox=CatalogBBox(x1=0, y1=0, x2=468, y2=792, width=468, height=792),
        rooms=[
            CatalogRoom(
                name="KITCHEN",
                polygon=[
                    CatalogPoint(x=0, y=500),
                    CatalogPoint(x=160, y=500),
                    CatalogPoint(x=160, y=792),
                    CatalogPoint(x=0, y=792),
                ],
                bbox=CatalogBBox(x1=0, y1=500, x2=160, y2=792, width=160, height=292),
                centroid=CatalogPoint(x=80, y=646),
                width=160,
                height=292,
                area=46720,
                measurement_source="room_region",
            ),
            CatalogRoom(
                name="BEDROOM 2",
                polygon=[
                    CatalogPoint(x=0, y=300),
                    CatalogPoint(x=160, y=300),
                    CatalogPoint(x=160, y=500),
                    CatalogPoint(x=0, y=500),
                ],
                bbox=CatalogBBox(x1=0, y1=300, x2=160, y2=500, width=160, height=200),
                centroid=CatalogPoint(x=80, y=400),
                width=160,
                height=200,
                area=32000,
                measurement_source="room_region",
            ),
            CatalogRoom(
                name="HALL",
                polygon=[
                    CatalogPoint(x=160, y=300),
                    CatalogPoint(x=240, y=300),
                    CatalogPoint(x=240, y=500),
                    CatalogPoint(x=160, y=500),
                ],
                bbox=CatalogBBox(x1=160, y1=300, x2=240, y2=500, width=80, height=200),
                centroid=CatalogPoint(x=200, y=400),
                width=80,
                height=200,
                area=16000,
                measurement_source="room_region",
            ),
        ],
        source_layers=["WALLS", "ROOM LBLS", "DOORS"],
        block_refs=["TOILET1"],
        readiness=CatalogReadiness(status="ready_for_catalog", issues=[]),
    )


def test_derive_floor_plan_topology_assigns_stable_room_ids_and_categories():
    topology = derive_floor_plan_topology(build_seed())

    kitchen = next(room for room in topology.rooms if room.name == "KITCHEN")
    bedroom = next(room for room in topology.rooms if room.name == "BEDROOM 2")

    assert kitchen.room_id == "room-kitchen-080-646"
    assert kitchen.category == "kitchen"
    assert bedroom.room_id == "room-bedroom-2-080-400"
    assert bedroom.category == "bedroom"


def test_derive_floor_plan_topology_marks_adjacency_and_exterior_touch():
    topology = derive_floor_plan_topology(build_seed())

    kitchen = next(room for room in topology.rooms if room.name == "KITCHEN")
    bedroom = next(room for room in topology.rooms if room.name == "BEDROOM 2")
    hall = next(room for room in topology.rooms if room.name == "HALL")

    assert bedroom.room_id in kitchen.adjacent_room_ids
    assert hall.room_id in bedroom.adjacent_room_ids
    assert kitchen.is_exterior_touching is True
    assert hall.is_exterior_touching is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_topology.py -q`
Expected: FAIL with `ModuleNotFoundError` for `backend.floor_plan_catalog.topology` and/or missing topology contracts.

- [ ] **Step 3: Extend the catalog contracts with topology models**

```python
class CatalogRoomTopology(BaseModel):
    room_id: str
    name: str
    category: str
    polygon: list[CatalogPoint] = Field(default_factory=list)
    bbox: CatalogBBox
    centroid: CatalogPoint
    width: float
    height: float
    area: float
    measurement_source: str
    adjacent_room_ids: list[str] = Field(default_factory=list)
    is_exterior_touching: bool = False
    issues: list[str] = Field(default_factory=list)


class TopologyReadiness(BaseModel):
    status: str
    issues: list[str] = Field(default_factory=list)


class FloorPlanTopologyV1(BaseModel):
    floor_plan_id: str
    name: str
    canonical_unit: str
    footprint_bbox: CatalogBBox
    rooms: list[CatalogRoomTopology] = Field(default_factory=list)
    topology_readiness: TopologyReadiness
    topology_issues: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Add the minimal topology derivation module**

```python
from __future__ import annotations

import math
import re

from .contracts import FloorPlanCatalogSeed, FloorPlanTopologyV1, CatalogRoomTopology, TopologyReadiness


def derive_floor_plan_topology(seed: FloorPlanCatalogSeed) -> FloorPlanTopologyV1:
    rooms = [_to_room_topology(seed, room) for room in seed.rooms]
    room_by_id = {room.room_id: room for room in rooms}

    for room in rooms:
        room.adjacent_room_ids = sorted(
            other.room_id for other in rooms if other.room_id != room.room_id and _rooms_are_adjacent(room, other)
        )
        room.is_exterior_touching = _touches_exterior(seed, room)
        if room.category == "unknown":
            room.issues.append("missing_category")
        if not room.adjacent_room_ids:
            room.issues.append("isolated_room")

    topology_issues = sorted({issue for room in rooms for issue in room.issues})
    readiness = TopologyReadiness(
        status="ready_for_topology_review" if not topology_issues else "needs_topology_review",
        issues=topology_issues,
    )

    return FloorPlanTopologyV1(
        floor_plan_id=seed.floor_plan_id,
        name=seed.name,
        canonical_unit=seed.canonical_unit,
        footprint_bbox=seed.footprint_bbox,
        rooms=rooms,
        topology_readiness=readiness,
        topology_issues=topology_issues,
    )


def _to_room_topology(seed: FloorPlanCatalogSeed, room):
    x = int(round(room.centroid.x))
    y = int(round(room.centroid.y))
    slug = re.sub(r"[^a-z0-9]+", "-", room.name.lower()).strip("-")
    return CatalogRoomTopology(
        room_id=f"room-{slug}-{x:03d}-{y:03d}",
        name=room.name,
        category=_infer_category(room.name),
        polygon=room.polygon,
        bbox=room.bbox,
        centroid=room.centroid,
        width=room.width,
        height=room.height,
        area=room.area,
        measurement_source=room.measurement_source,
    )


def _infer_category(name: str) -> str:
    upper = name.upper()
    if "KITCHEN" in upper:
        return "kitchen"
    if "BED" in upper:
        return "bedroom"
    if "BATH" in upper:
        return "bath"
    if "HALL" in upper:
        return "hall"
    if "PATIO" in upper:
        return "patio"
    if "GARAGE" in upper:
        return "garage"
    return "unknown"


def _rooms_are_adjacent(a: CatalogRoomTopology, b: CatalogRoomTopology, tolerance: float = 3.0) -> bool:
    horizontal_overlap = min(a.bbox.x2, b.bbox.x2) - max(a.bbox.x1, b.bbox.x1)
    vertical_overlap = min(a.bbox.y2, b.bbox.y2) - max(a.bbox.y1, b.bbox.y1)
    touches_vertically = horizontal_overlap > tolerance and min(abs(a.bbox.y2 - b.bbox.y1), abs(b.bbox.y2 - a.bbox.y1)) <= tolerance
    touches_horizontally = vertical_overlap > tolerance and min(abs(a.bbox.x2 - b.bbox.x1), abs(b.bbox.x2 - a.bbox.x1)) <= tolerance
    return touches_vertically or touches_horizontally


def _touches_exterior(seed: FloorPlanCatalogSeed, room: CatalogRoomTopology, tolerance: float = 3.0) -> bool:
    bbox = seed.footprint_bbox
    return (
        abs(room.bbox.x1 - bbox.x1) <= tolerance
        or abs(room.bbox.y1 - bbox.y1) <= tolerance
        or abs(room.bbox.x2 - bbox.x2) <= tolerance
        or abs(room.bbox.y2 - bbox.y2) <= tolerance
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_topology.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/floor_plan_catalog/contracts.py backend/floor_plan_catalog/topology.py tests/test_floor_plan_catalog_topology.py
git commit -m "feat: derive floor plan topology v1"
```

---

### Task 2: Endurecer la derivación topológica con casos rojos de issues y estabilidad

**Files:**
- Modify: `tests/test_floor_plan_catalog_topology.py`
- Modify: `backend/floor_plan_catalog/topology.py`

- [ ] **Step 1: Write the failing regression tests for unknown category and deterministic output**

```python
def test_derive_floor_plan_topology_marks_unknown_category_and_isolation_issue():
    seed = build_seed()
    seed.rooms = seed.rooms[:1]
    seed.rooms[0].name = "SPACE X"

    topology = derive_floor_plan_topology(seed)
    room = topology.rooms[0]

    assert room.category == "unknown"
    assert "missing_category" in room.issues
    assert "isolated_room" in room.issues
    assert topology.topology_readiness.status == "needs_topology_review"


def test_derive_floor_plan_topology_is_deterministic_between_runs():
    first = derive_floor_plan_topology(build_seed()).model_dump()
    second = derive_floor_plan_topology(build_seed()).model_dump()

    assert first == second
```

- [ ] **Step 2: Run test to verify it fails**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_topology.py -q`
Expected: FAIL because current implementation will not yet surface all issues/readiness transitions cleanly.

- [ ] **Step 3: Tighten topology readiness and issue aggregation**

```python
def derive_floor_plan_topology(seed: FloorPlanCatalogSeed) -> FloorPlanTopologyV1:
    rooms = [_to_room_topology(seed, room) for room in seed.rooms]

    for room in rooms:
        room.adjacent_room_ids = sorted(
            other.room_id for other in rooms if other.room_id != room.room_id and _rooms_are_adjacent(room, other)
        )
        room.is_exterior_touching = _touches_exterior(seed, room)

        if room.category == "unknown":
            room.issues.append("missing_category")
        if not room.adjacent_room_ids:
            room.issues.append("isolated_room")
        if room.area <= 0 or len(room.polygon) < 4:
            room.issues.append("suspicious_polygon")

        room.issues = sorted(set(room.issues))

    topology_issues = sorted({issue for room in rooms for issue in room.issues})
    status = "ready_for_topology_review" if not topology_issues else "needs_topology_review"

    return FloorPlanTopologyV1(
        floor_plan_id=seed.floor_plan_id,
        name=seed.name,
        canonical_unit=seed.canonical_unit,
        footprint_bbox=seed.footprint_bbox,
        rooms=rooms,
        topology_readiness=TopologyReadiness(status=status, issues=topology_issues),
        topology_issues=topology_issues,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_topology.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/floor_plan_catalog/topology.py tests/test_floor_plan_catalog_topology.py
git commit -m "feat: harden topology readiness rules"
```

---

### Task 3: Exportar una fixture REAL de `SEMINOLE2000` para el inspector temporal

**Files:**
- Create: `scripts/export_seminole_topology_fixture.py`
- Create: `frontend/src/features/catalogInspector/catalogInspector.fixture.json`
- Test: `tests/test_floor_plan_catalog_topology.py`

- [ ] **Step 1: Write the failing export test**

```python
from pathlib import Path
from subprocess import run
import json


def test_export_seminole_topology_fixture_writes_frontend_json(tmp_path: Path):
    input_path = Path(r"D:\PointAIData\PLANS\catalog\seminole-2000.json")
    output_path = tmp_path / "catalogInspector.fixture.json"

    result = run(
        [
            ".\\.venv\\Scripts\\python.exe",
            "scripts/export_seminole_topology_fixture.py",
            str(input_path),
            "--output",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=Path(__file__).resolve().parents[1],
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["floor_plan_id"] == "seminole-2000"
    assert payload["rooms"]
    assert "topology_readiness" in payload
```

- [ ] **Step 2: Run test to verify it fails**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_topology.py -q`
Expected: FAIL because the export script does not exist.

- [ ] **Step 3: Write the export script and generate the real fixture**

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.floor_plan_catalog.contracts import FloorPlanCatalogSeed
from backend.floor_plan_catalog.topology import derive_floor_plan_topology


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("seed_json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    seed_payload = json.loads(Path(args.seed_json).read_text(encoding="utf-8"))
    seed = FloorPlanCatalogSeed.model_validate(seed_payload)
    topology = derive_floor_plan_topology(seed)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(topology.model_dump(), indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Run after writing the script:

```bash
.\.venv\Scripts\python.exe scripts/export_seminole_topology_fixture.py D:\PointAIData\PLANS\catalog\seminole-2000.json --output frontend/src/features/catalogInspector/catalogInspector.fixture.json
```

- [ ] **Step 4: Run test to verify it passes**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_topology.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/export_seminole_topology_fixture.py frontend/src/features/catalogInspector/catalogInspector.fixture.json tests/test_floor_plan_catalog_topology.py
git commit -m "feat: export seminole topology fixture"
```

---

### Task 4: Construir el inspector visual temporal con plano real y panel lateral

**Files:**
- Create: `frontend/src/features/catalogInspector/types.ts`
- Create: `frontend/src/features/catalogInspector/CatalogInspectorCanvas.tsx`
- Create: `frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx`
- Create: `frontend/src/features/catalogInspector/CatalogInspectorPage.tsx`
- Create: `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx`

- [ ] **Step 1: Write the failing frontend interaction test**

```tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CatalogInspectorPage } from './CatalogInspectorPage'
import topology from './catalogInspector.fixture.json'

describe('CatalogInspectorPage', () => {
  it('renders the real topology fixture and updates the sidebar when selecting a room', () => {
    render(<CatalogInspectorPage topology={topology} />)

    expect(screen.getByText(/SEMINOLE2000/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /room ids/i })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /select room-kitchen/i }))

    expect(screen.getByText(/room-kitchen/i)).toBeInTheDocument()
    expect(screen.getByText(/category/i)).toBeInTheDocument()
    expect(screen.getByText(/adjacent/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cmd /c npm --prefix frontend test -- src/features/catalogInspector/CatalogInspectorPage.test.tsx`
Expected: FAIL because the feature files do not exist.

- [ ] **Step 3: Add the TS contracts and inspector shell**

```ts
export interface CatalogInspectorPoint { x: number; y: number }

export interface CatalogInspectorBBox {
  x1: number
  y1: number
  x2: number
  y2: number
  width: number
  height: number
}

export interface CatalogInspectorRoom {
  room_id: string
  name: string
  category: string
  polygon: CatalogInspectorPoint[]
  bbox: CatalogInspectorBBox
  centroid: CatalogInspectorPoint
  width: number
  height: number
  area: number
  measurement_source: string
  adjacent_room_ids: string[]
  is_exterior_touching: boolean
  issues: string[]
}

export interface CatalogInspectorTopology {
  floor_plan_id: string
  name: string
  canonical_unit: string
  footprint_bbox: CatalogInspectorBBox
  rooms: CatalogInspectorRoom[]
  topology_readiness: { status: string; issues: string[] }
  topology_issues: string[]
}
```

```tsx
import { useMemo, useState } from 'react'
import type { CatalogInspectorTopology } from './types'
import { CatalogInspectorCanvas } from './CatalogInspectorCanvas'
import { CatalogInspectorSidebar } from './CatalogInspectorSidebar'

interface CatalogInspectorPageProps {
  topology: CatalogInspectorTopology
}

export function CatalogInspectorPage({ topology }: CatalogInspectorPageProps) {
  const [selectedRoomId, setSelectedRoomId] = useState(topology.rooms[0]?.room_id ?? null)
  const [showIds, setShowIds] = useState(true)
  const [showAdjacency, setShowAdjacency] = useState(true)
  const selectedRoom = useMemo(
    () => topology.rooms.find((room) => room.room_id === selectedRoomId) ?? null,
    [selectedRoomId, topology.rooms],
  )

  return (
    <div className="grid gap-6 xl:grid-cols-[1.35fr_360px]">
      <section className="rounded-[28px] border border-white/6 bg-zinc-950/80 p-5">
        <div className="flex flex-wrap gap-3 border-b border-white/6 pb-4">
          <button type="button" aria-pressed={showIds} onClick={() => setShowIds((value) => !value)}>Room IDs</button>
          <button type="button" aria-pressed={showAdjacency} onClick={() => setShowAdjacency((value) => !value)}>Adjacency</button>
        </div>
        <CatalogInspectorCanvas
          topology={topology}
          selectedRoomId={selectedRoomId}
          onSelectRoom={setSelectedRoomId}
          showIds={showIds}
          showAdjacency={showAdjacency}
        />
      </section>
      <CatalogInspectorSidebar topology={topology} selectedRoom={selectedRoom} />
    </div>
  )
}
```

- [ ] **Step 4: Implement the real-plan canvas and sidebar**

```tsx
import type { CatalogInspectorTopology } from './types'

interface CatalogInspectorCanvasProps {
  topology: CatalogInspectorTopology
  selectedRoomId: string | null
  onSelectRoom: (roomId: string) => void
  showIds: boolean
  showAdjacency: boolean
}

export function CatalogInspectorCanvas({ topology, selectedRoomId, onSelectRoom, showIds, showAdjacency }: CatalogInspectorCanvasProps) {
  const box = topology.footprint_bbox
  return (
    <svg viewBox={`${box.x1 - 32} ${box.y1 - 32} ${box.width + 64} ${box.height + 64}`} className="mt-4 h-[760px] w-full rounded-[24px] bg-[#050505]">
      <rect x={box.x1} y={box.y1} width={box.width} height={box.height} fill="rgba(8,8,8,.2)" stroke="rgba(255,255,255,.08)" />
      {topology.rooms.map((room) => {
        const isSelected = room.room_id === selectedRoomId
        return (
          <g key={room.room_id}>
            <polygon
              points={room.polygon.map((point) => `${point.x},${point.y}`).join(' ')}
              fill={isSelected ? 'rgba(34,211,238,.24)' : 'rgba(34,211,238,.12)'}
              stroke={room.is_exterior_touching ? '#34d399' : '#67e8f9'}
              strokeWidth={isSelected ? 4 : 2}
              onClick={() => onSelectRoom(room.room_id)}
              style={{ cursor: 'pointer' }}
            />
            {showIds && (
              <text x={room.centroid.x} y={room.centroid.y} textAnchor="middle" fill="#f8fafc" fontSize={10}>
                {room.room_id}
              </text>
            )}
          </g>
        )
      })}
      {showAdjacency && topology.rooms.flatMap((room) => room.adjacent_room_ids.map((adjacentId) => {
        const other = topology.rooms.find((candidate) => candidate.room_id === adjacentId)
        if (!other || room.room_id > other.room_id) return null
        return (
          <line
            key={`${room.room_id}-${adjacentId}`}
            x1={room.centroid.x}
            y1={room.centroid.y}
            x2={other.centroid.x}
            y2={other.centroid.y}
            stroke="rgba(244,114,182,.9)"
            strokeDasharray="8 8"
          />
        )
      }))}
      {topology.rooms.map((room) => (
        <foreignObject key={`button-${room.room_id}`} x={room.centroid.x - 1} y={room.centroid.y - 1} width={1} height={1}>
          <button aria-label={`Select ${room.room_id}`} onClick={() => onSelectRoom(room.room_id)} />
        </foreignObject>
      ))}
    </svg>
  )
}
```

```tsx
import type { CatalogInspectorRoom, CatalogInspectorTopology } from './types'

interface CatalogInspectorSidebarProps {
  topology: CatalogInspectorTopology
  selectedRoom: CatalogInspectorRoom | null
}

export function CatalogInspectorSidebar({ topology, selectedRoom }: CatalogInspectorSidebarProps) {
  return (
    <aside className="flex flex-col gap-4 rounded-[28px] border border-white/6 bg-zinc-950/80 p-5">
      <section>
        <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Floor plan</p>
        <h2 className="mt-2 text-2xl font-semibold text-zinc-100">{topology.name}</h2>
        <p className="mt-2 text-sm text-zinc-400">{topology.rooms.length} rooms · {topology.topology_readiness.status}</p>
      </section>
      {selectedRoom && (
        <section>
          <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Room seleccionado</p>
          <h3 className="mt-2 text-xl font-semibold text-zinc-100">{selectedRoom.name}</h3>
          <p className="mt-2 text-sm text-zinc-300">{selectedRoom.room_id}</p>
          <p className="mt-2 text-sm text-zinc-300">Category: {selectedRoom.category}</p>
          <p className="mt-2 text-sm text-zinc-300">Adjacent: {selectedRoom.adjacent_room_ids.join(', ') || 'None'}</p>
          <p className="mt-2 text-sm text-zinc-300">Exterior touch: {selectedRoom.is_exterior_touching ? 'yes' : 'no'}</p>
        </section>
      )}
    </aside>
  )
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cmd /c npm --prefix frontend test -- src/features/catalogInspector/CatalogInspectorPage.test.tsx`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/catalogInspector/types.ts frontend/src/features/catalogInspector/catalogInspector.fixture.json frontend/src/features/catalogInspector/CatalogInspectorCanvas.tsx frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx frontend/src/features/catalogInspector/CatalogInspectorPage.tsx frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx
git commit -m "feat: add temporary topology inspector ui"
```

---

### Task 5: Exponer la screen temporal desde `App.tsx` sin contaminar el producto final

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Write the failing app entry test**

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('./hooks/useAuth', () => ({ useAuth: () => ({ loading: false, user: null, signIn: vi.fn(), signUp: vi.fn(), signInWithGoogle: vi.fn(), signOut: vi.fn() }) }))
vi.mock('./hooks/useProject', () => ({ useProjectList: () => ({ projects: [], loading: false, createProject: vi.fn(), deleteProject: vi.fn(), renameProject: vi.fn(), refresh: vi.fn() }) }))
vi.mock('./features/threads', () => ({ useThreadList: () => ({ threads: [], loading: false, createThread: vi.fn(), deleteThread: vi.fn(), renameThread: vi.fn(), refresh: vi.fn() }), useThreadSave: () => ({ saving: false, lastSaved: null, saveNow: vi.fn() }), threadToInitialMessages: () => [], threadToThreadSummary: () => [] }))

import App from './App'

describe('App debug inspector route', () => {
  it('renders the temporary seminole topology inspector when query flag is present', async () => {
    window.history.replaceState({}, '', '/?debug=seminole-topology')
    render(<App />)
    expect(await screen.findByText(/SEMINOLE2000/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cmd /c npm --prefix frontend test -- src/App.test.tsx src/features/catalogInspector/CatalogInspectorPage.test.tsx`
Expected: FAIL because `App.tsx` does not yet branch to the temporary inspector.

- [ ] **Step 3: Wire the temporary entry in `App.tsx`**

```tsx
import inspectorTopology from './features/catalogInspector/catalogInspector.fixture.json'
import { CatalogInspectorPage } from './features/catalogInspector/CatalogInspectorPage'

const isSeminoleTopologyInspector = (() => {
  if (typeof window === 'undefined') return false
  return new URLSearchParams(window.location.search).get('debug') === 'seminole-topology'
})()

export default function App() {
  if (isSeminoleTopologyInspector) {
    return (
      <div className="min-h-screen bg-[#090909] px-6 py-6 text-zinc-100">
        <CatalogInspectorPage topology={inspectorTopology} />
      </div>
    )
  }

  // existing app code continues unchanged
}
```

- [ ] **Step 4: Run tests to verify the temporary entry and relevant regressions pass**

Run: `cmd /c npm --prefix frontend test -- src/App.test.tsx src/features/catalogInspector/CatalogInspectorPage.test.tsx src/features/chatThread/ThreadWorkspacePage.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "feat: expose temporary seminole topology inspector"
```

---

### Task 6: Verify end-to-end artifact generation and document how to use the inspector

**Files:**
- Modify: `MVP.md`
- Modify: `docs/superpowers/specs/2026-04-22-seminole-topology-inspector-design.md` (only if needed for clarity)

- [ ] **Step 1: Regenerate the real fixture from current catalog data**

Run:

```bash
.\.venv\Scripts\python.exe scripts/export_seminole_topology_fixture.py D:\PointAIData\PLANS\catalog\seminole-2000.json --output frontend/src/features/catalogInspector/catalogInspector.fixture.json
```

Expected: command exits `0` and rewrites the JSON fixture.

- [ ] **Step 2: Run backend and frontend tests for this slice**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_topology.py tests/test_floor_plan_catalog_curator.py tests/test_floor_plan_catalog_audit.py -q
cmd /c npm --prefix frontend test -- src/App.test.tsx src/features/catalogInspector/CatalogInspectorPage.test.tsx
```

Expected:
- pytest: PASS
- vitest: PASS

- [ ] **Step 3: Document the temporary entry and its purpose**

Add this section to `MVP.md`:

```md
## Temporary topology inspector

For curation/debug only:
- derive topology from `SEMINOLE2000`
- export fixture with `scripts/export_seminole_topology_fixture.py`
- open the React app with `?debug=seminole-topology`

This screen is intentionally temporary and exists to validate that room identity, category, adjacency and exterior-touch are coherent before building the executor.
```

- [ ] **Step 4: Commit**

```bash
git add MVP.md docs/superpowers/specs/2026-04-22-seminole-topology-inspector-design.md frontend/src/features/catalogInspector/catalogInspector.fixture.json
git commit -m "docs: document temporary topology inspector workflow"
```

---

## Self-Review

### Spec coverage
- `FloorPlanTopologyV1` derivation -> covered by Tasks 1 and 2.
- temporary visual inspector using real geometry -> covered by Tasks 3, 4 and 5.
- removable / non-product-final entry -> covered by Task 5.
- validation workflow before executor -> documented in Task 6.

### Placeholder scan
- No `TODO`, `TBD`, or “implement later” placeholders remain in tasks.
- Every task includes exact file paths, test commands, and concrete code snippets.

### Type consistency
- `FloorPlanTopologyV1`, `CatalogRoomTopology`, `topology_readiness`, `adjacent_room_ids`, and `is_exterior_touching` are named consistently across backend, fixture export, and frontend.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-22-seminole-topology-inspector.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
