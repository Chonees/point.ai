# Assembly Inspector v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current topology inspector into an assembly-style technical surface that shows the floor plan as evidence, canonical graph pieces, and operable semantic parts.

**Architecture:** Keep all changes inside `frontend/src/features/catalogInspector/` and treat this as a temporary technical inspector, not product UX. Reuse the existing exported fixture and inspector route, but restructure the screen around three concepts: parts panel, layered assembly canvas, and piece inspector/glossary.

**Tech Stack:** React, TypeScript, Testing Library, Vitest, existing catalog inspector fixture and components.

---

## File Structure

### Existing files to modify
- `frontend/src/features/catalogInspector/CatalogInspectorPage.tsx` — page composition, counts, toggles, focus state
- `frontend/src/features/catalogInspector/CatalogInspectorCanvas.tsx` — draw order, selection affordances, boundary visibility
- `frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx` — selected piece details and glossary
- `frontend/src/features/catalogInspector/types.ts` — add any narrow UI-only selection helper types if needed
- `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx` — page-level behavior coverage

### Likely new files
- `frontend/src/features/catalogInspector/CatalogInspectorPartsPanel.tsx` — left-side grouped parts/layers list
- `frontend/src/features/catalogInspector/CatalogInspectorGlossary.tsx` — fixed glossary block explaining every piece type

### Existing verification targets
- `frontend/src/App.test.tsx`
- `frontend/src/features/catalogInspector/catalogInspector.fixture.json`

---

### Task 1: Add the failing tests for Assembly Inspector structure

**Files:**
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx`
- Test: `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx`

- [ ] **Step 1: Write the failing test for the new parts panel**

```tsx
it('renders grouped parts panel counts for evidence, structural graph, and operable model', () => {
  render(<CatalogInspectorPage topology={fixture} />)

  expect(screen.getByText(/^Evidence$/i)).toBeInTheDocument()
  expect(screen.getByText(/^Structural graph$/i)).toBeInTheDocument()
  expect(screen.getByText(/^Operable model$/i)).toBeInTheDocument()
  expect(screen.getByText(/^Raw wall traces$/i)).toBeInTheDocument()
  expect(screen.getByText(/^Boundary nodes$/i)).toBeInTheDocument()
  expect(screen.getByText(/^Hosted openings$/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Write the failing test for the glossary**

```tsx
it('renders the assembly glossary explaining each piece type', () => {
  render(<CatalogInspectorPage topology={fixture} />)

  expect(screen.getByText(/raw trace = geometry evidence extracted from dxf/i)).toBeInTheDocument()
  expect(screen.getByText(/boundary = canonical rearmable segment/i)).toBeInTheDocument()
  expect(screen.getByText(/room = closed space formed by boundaries/i)).toBeInTheDocument()
})
```

- [ ] **Step 3: Write the failing test for unknown-boundary focus visibility**

```tsx
it('renders an unknown-boundary focus shortcut with the exact fixture count', () => {
  render(<CatalogInspectorPage topology={fixture} />)

  expect(screen.getByRole('button', { name: /unknown boundaries/i })).toBeInTheDocument()
  expect(screen.getByText(/^Unknown boundaries$/i)).toBeInTheDocument()
})
```

- [ ] **Step 4: Run test to verify it fails**

Run:

```bash
cmd /c npm --prefix frontend test -- src/features/catalogInspector/CatalogInspectorPage.test.tsx
```

Expected:
- FAIL because the grouped parts panel / glossary / unknown-boundary focus are not all present yet

- [ ] **Step 5: Commit the RED test**

```bash
git add frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx
git commit -m "test: cover assembly inspector structure"
```

---

### Task 2: Add the grouped parts panel

**Files:**
- Create: `frontend/src/features/catalogInspector/CatalogInspectorPartsPanel.tsx`
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorPage.tsx`
- Test: `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx`

- [ ] **Step 1: Write the minimal parts panel component**

```tsx
interface PartsGroupItem {
  label: string
  count: number
  active?: boolean
}

interface PartsGroup {
  title: string
  items: PartsGroupItem[]
}

export function CatalogInspectorPartsPanel({ groups }: { groups: PartsGroup[] }) {
  return (
    <section data-testid="assembly-parts-panel" className="rounded-[24px] border border-white/6 bg-zinc-950/80 p-5">
      {groups.map((group) => (
        <div key={group.title} className="mb-5 last:mb-0">
          <h3 className="text-sm font-semibold uppercase tracking-[0.22em] text-zinc-400">{group.title}</h3>
          <div className="mt-3 space-y-2">
            {group.items.map((item) => (
              <div key={item.label} className="rounded-xl border border-white/6 bg-black/20 px-3 py-2">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm text-zinc-100">{item.label}</span>
                  <span className="text-xs text-zinc-400">{item.count}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </section>
  )
}
```

- [ ] **Step 2: Wire the grouped counts in `CatalogInspectorPage.tsx`**

```tsx
const partsGroups = [
  {
    title: 'Evidence',
    items: [
      { label: 'Raw wall traces', count: rawWallTraces.length },
      { label: 'Raw door traces', count: doorTraces.length },
      { label: 'Raw window traces', count: windowTraces.length },
    ],
  },
  {
    title: 'Structural graph',
    items: [
      { label: 'Boundary nodes', count: boundaryNodes.length },
      { label: 'Shared boundaries', count: boundaries.filter((b) => b.boundary_kind === 'shared').length },
      { label: 'Exterior boundaries', count: boundaries.filter((b) => b.boundary_kind === 'exterior').length },
      { label: 'Unknown boundaries', count: unknownBoundaryCount },
    ],
  },
  {
    title: 'Operable model',
    items: [
      { label: 'Walls', count: topology.walls.length },
      { label: 'Hosted openings', count: hostedOpenings.filter((opening) => !!opening.host_wall_id).length },
      { label: 'Unhosted openings', count: hostedOpenings.filter((opening) => !opening.host_wall_id).length },
      { label: 'Rooms', count: topology.rooms.length },
    ],
  },
]
```

- [ ] **Step 3: Render the parts panel as the left column**

```tsx
<div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)_380px]">
  <CatalogInspectorPartsPanel groups={partsGroups} />
  <CatalogInspectorCanvas ... />
  <CatalogInspectorSidebar ... />
</div>
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cmd /c npm --prefix frontend test -- src/features/catalogInspector/CatalogInspectorPage.test.tsx
```

Expected:
- the grouped parts-panel assertions now pass

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/catalogInspector/CatalogInspectorPartsPanel.tsx frontend/src/features/catalogInspector/CatalogInspectorPage.tsx frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx
git commit -m "feat: add assembly parts panel"
```

---

### Task 3: Fix canvas layering so canonical pieces stay visible

**Files:**
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorCanvas.tsx`
- Test: `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx`

- [ ] **Step 1: Write the failing test for exact boundary visibility mode**

```tsx
it('keeps exact-boundary mode available alongside room selection and part inspection', () => {
  render(<CatalogInspectorPage topology={fixture} />)

  fireEvent.click(screen.getByRole('checkbox', { name: /exact boundaries/i }))
  expect(screen.getAllByTestId(/^boundary-/).length).toBeGreaterThan(0)
})
```

- [ ] **Step 2: Reorder the canvas draw stack**

Use this order inside the SVG:

```tsx
{visibleTraces.map(...)}
{topology.rooms.map(...)}
{showExactBoundaries && boundaries.map(...)}
{showWalls && visibleWalls.map(...)}
{showHostedOpenings && visibleOpenings.map(...)}
{showExactBoundaries && boundaryNodes.map(...)}
```

Important:
- room fill stays semi-transparent
- boundaries and nodes render over room polygons
- walls and hosted openings stay visually distinct above boundaries

- [ ] **Step 3: Keep room hit targets usable after reordering**

If direct room clickability degrades after changing order, wrap room label / polygon interaction in a dedicated group and preserve:

```tsx
role="button"
tabIndex={0}
aria-label={`Select ${room.name}`}
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cmd /c npm --prefix frontend test -- src/features/catalogInspector/CatalogInspectorPage.test.tsx
```

Expected:
- exact-boundary related tests stay green after the layering fix

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/catalogInspector/CatalogInspectorCanvas.tsx frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx
git commit -m "fix: keep exact boundaries visible in assembly canvas"
```

---

### Task 4: Add the glossary and piece semantics block

**Files:**
- Create: `frontend/src/features/catalogInspector/CatalogInspectorGlossary.tsx`
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx`
- Test: `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx`

- [ ] **Step 1: Write the glossary component**

```tsx
const glossaryItems = [
  { title: 'Raw trace', description: 'Geometry evidence extracted from DXF.' },
  { title: 'Node', description: 'Graph connection point used to split and reconnect boundaries.' },
  { title: 'Boundary', description: 'Canonical rearmable segment between nodes.' },
  { title: 'Wall', description: 'Derived structural reading built from graph + ownership.' },
  { title: 'Opening', description: 'Hosted cut in a wall or boundary.' },
  { title: 'Room', description: 'Closed space formed by boundaries and openings.' },
]
```

- [ ] **Step 2: Render the glossary under the right-side inspector**

```tsx
<CatalogInspectorGlossary />
```

- [ ] **Step 3: Add “derived from / supports” language to the selected-piece panels where possible**

Examples:

```tsx
<p className="mt-1 text-xs text-zinc-500">Supports traces: {selectedBoundary.source_trace_ids.join(', ') || 'None'}</p>
<p className="mt-1 text-xs text-zinc-500">Host wall: {selectedOpening.host_wall_id ?? 'Unhosted'}</p>
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cmd /c npm --prefix frontend test -- src/features/catalogInspector/CatalogInspectorPage.test.tsx
```

Expected:
- glossary assertions pass

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/catalogInspector/CatalogInspectorGlossary.tsx frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx
git commit -m "feat: add assembly glossary to inspector"
```

---

### Task 5: Add piece-oriented focus shortcuts

**Files:**
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorPage.tsx`
- Modify: `frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx`
- Test: `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx`

- [ ] **Step 1: Write the failing test for unknown-boundary focus shortcut**

```tsx
it('surfaces unknown boundaries as a first-class assembly problem area', () => {
  render(<CatalogInspectorPage topology={fixture} />)

  expect(screen.getByRole('button', { name: /unknown boundaries/i })).toBeInTheDocument()
})
```

- [ ] **Step 2: Add a lightweight problem shortcut section**

```tsx
const problemShortcuts = [
  { label: 'Unknown boundaries', count: unknownBoundaryCount },
  { label: 'Unhosted openings', count: unhostedOpeningCount },
]
```

Render them near the validation block so users can quickly see:
- what is unresolved
- how much remains

- [ ] **Step 3: If practical without large refactor, let shortcut click preselect the first unresolved item**

Example:

```tsx
onClick={() => {
  const firstUnknown = boundaries.find((boundary) => boundary.boundary_kind === 'unknown')
  if (firstUnknown) setSelectedBoundaryId(firstUnknown.boundary_id)
}}
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cmd /c npm --prefix frontend test -- src/features/catalogInspector/CatalogInspectorPage.test.tsx
```

Expected:
- unknown-boundary focus shortcut is rendered and selectable

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/catalogInspector/CatalogInspectorPage.tsx frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx
git commit -m "feat: add assembly problem shortcuts"
```

---

### Task 6: Final verification and docs sync

**Files:**
- Modify: `MVP.md` (if the temporary inspector workflow section needs one extra paragraph)
- Verify: `frontend/src/features/catalogInspector/catalogInspector.fixture.json`

- [ ] **Step 1: Run focused frontend verification**

```bash
cmd /c npm --prefix frontend test -- src/App.test.tsx src/features/catalogInspector/CatalogInspectorPage.test.tsx
```

Expected:
- PASS

- [ ] **Step 2: Check the visual route**

```bash
powershell -Command "try { (Invoke-WebRequest http://localhost:5173/?debug=seminole-topology -UseBasicParsing).StatusCode } catch { Write-Error $_; exit 1 }"
```

Expected:
- `200`

- [ ] **Step 3: Verify git state**

```bash
git status --short
```

Expected:
- only intended assembly-inspector files changed

- [ ] **Step 4: Commit final polish/docs if needed**

```bash
git add MVP.md frontend/src/features/catalogInspector/CatalogInspectorPage.tsx frontend/src/features/catalogInspector/CatalogInspectorCanvas.tsx frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx frontend/src/features/catalogInspector/CatalogInspectorPartsPanel.tsx frontend/src/features/catalogInspector/CatalogInspectorGlossary.tsx frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx
git commit -m "docs: document assembly inspector workflow"
```

---

## Self-Review

### Spec coverage
- Parts panel: covered in Task 2
- Layering fix: covered in Task 3
- Glossary / semantics: covered in Task 4
- Unknown-boundary visibility: covered in Tasks 1 and 5
- Piece-by-piece inspection remains in existing sidebar and is strengthened in Task 4

### Placeholder scan
- No TBD/TODO placeholders left in the plan
- Commands and expected outcomes are explicit

### Type consistency
- Uses existing inspector domain names:
  - `cad_traces`
  - `boundary_nodes`
  - `boundaries`
  - `walls`
  - `openings`
  - `rooms`

---

Plan complete and saved to `docs/superpowers/plans/2026-04-22-assembly-inspector-v1.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
