# Assembly Inspector v1 Design

## Summary

Convert the current topology inspector from a mostly overlay-oriented debug screen into an **assembly inspector** that presents the floor plan as a system of rearmable parts. The screen must make the executor-facing model explicit: raw CAD evidence, canonical boundary graph, derived walls, hosted openings, and rooms, all cross-linked and explorable piece by piece.

This is not product-final UX. It is a technical validation surface that helps us answer:

- what exact pieces exist in the model
- where each piece came from
- what depends on it
- what would later be editable by the executor

## Problem

The current inspector already shows rooms, walls, boundaries, traces, and openings, but it still has three problems:

1. **Model semantics are implicit**
   The user can see lines and overlays, but not clearly distinguish evidence (`cad_traces`) from canonical pieces (`boundaries`) and derived semantic pieces (`walls`, `rooms`, `openings`).

2. **Visual layering hides important geometry**
   Exact boundaries can be partially hidden by room fills, making the graph look less complete than it really is.

3. **There is no “parts list”**
   We cannot inspect the floor plan like an assembly where every piece has an identity, role, provenance, and downstream impact.

Without this, the next jump toward executor-grade modeling is much harder to validate.

## Goals

- Show the plan as **evidence + graph + semantic model**, not just one blended overlay
- Make every executor-relevant piece selectable and inspectable
- Provide a persistent legend that explains what each type means
- Expose a left-side parts/layers panel that works like a structured bill of materials
- Improve visual truth by rendering canonical pieces above room fills
- Add focus modes for unresolved / high-value categories such as unknown boundaries and unhosted openings

## Non-Goals

- No final user-facing product shell changes
- No site-fit mutation execution yet
- No DXF recompilation yet
- No broad refactor of the whole inspector architecture unless needed to keep files understandable

## Current Model Vocabulary

Assembly Inspector v1 will standardize and explain these model layers:

### 1. Raw CAD traces

Purpose: source evidence extracted from DXF.

Kinds:
- wall trace
- door trace
- window trace

These are not yet the ideal editable unit. They are proof that the CAD contained that geometry.

### 2. Boundary nodes

Purpose: graph connection points.

Examples:
- corner
- tee
- opening cut

These are critical executor primitives because they allow boundaries to be split, moved, and reconnected deterministically.

### 3. Boundaries

Purpose: canonical rearmable segments between nodes.

Kinds:
- shared
- exterior
- unknown

This is the most important future executor unit. A boundary is closer to “what can be moved” than a raw trace or even a room.

### 4. Walls

Purpose: derived structural-semantic reading of the plan.

Walls preserve:
- ownership by room
- boundary kind
- provenance/confidence
- trace support status

Walls remain useful to humans and later to opening hosting, but they are not as atomic as boundaries.

### 5. Openings

Purpose: hosted cuts over walls / boundaries.

Kinds:
- door
- window

Openings preserve:
- host wall
- owner rooms
- connected rooms
- offset/span
- confidence

### 6. Rooms

Purpose: closed spaces formed by boundaries and openings.

Rooms preserve:
- identity
- semantic category
- topology
- wall ownership
- future mutability / constraint context

## Proposed UX

Assembly Inspector v1 will use a three-column structure.

### Left column: Parts / Layers panel

This panel answers: **what exists in the model?**

Sections:

#### Evidence
- Raw wall traces
- Raw door traces
- Raw window traces

#### Structural graph
- Boundary nodes
- Shared boundaries
- Exterior boundaries
- Unknown boundaries

#### Operable model
- Walls
- Hosted openings
- Unhosted openings
- Rooms

Each section shows:
- count
- visibility toggle
- optional focus shortcut

For sublists, selecting an item should select the exact object in the canvas and inspector.

### Center: Assembly canvas

This panel answers: **where is the piece and how does it relate visually?**

Required draw order:

1. raw traces at the back
2. room fills semi-transparent
3. boundaries above room fills
4. walls above boundaries when enabled
5. openings above their host geometry
6. nodes on top when enabled
7. labels / highlights on top

This ordering is mandatory because the current inspector can visually hide exact boundaries.

The canvas must make it easy to compare:
- evidence
- canonical graph
- derived semantic geometry

### Right column: Selected part inspector + glossary

This panel answers:
- what is this thing
- where did it come from
- what depends on it
- is it executor-relevant

Selection modes:

#### Raw trace selection
Show:
- trace id
- kind
- source layer
- bbox
- whether it supports any boundary / wall / opening

#### Boundary selection
Show:
- boundary id
- kind
- owner rooms
- source traces
- start / end node
- confidence
- issues
- linked opening ids
- later-editability placeholder (read-only for now)

#### Wall selection
Show:
- wall id
- owner rooms
- boundary kind
- provenance
- confidence
- trace support
- related openings

#### Opening selection
Show:
- opening id
- opening kind
- host wall
- connected rooms
- owner rooms
- span / offset
- confidence
- issues

#### Room selection
Show:
- room id
- category
- area / size
- supported adjacency
- opening adjacency
- owned walls
- boundaries touching room
- openings touching room
- issues

#### Persistent glossary
A fixed “What you are seeing” block should explain:

- Raw trace = geometry evidence extracted from DXF
- Node = graph connection point
- Boundary = canonical rearmable segment
- Wall = derived structural reading
- Opening = hosted cut in a wall/boundary
- Room = closed space formed by boundaries

## Focus Modes

Assembly Inspector v1 should extend focus beyond walls.

Required focus categories:
- Unknown boundaries
- Shared boundaries
- Exterior boundaries
- Boundary nodes
- Unhosted openings
- Hosted openings

Existing wall focus can remain, but it should no longer be the only queue mechanism.

## Data Requirements

No new domain objects are required to start this slice. The current exported fixture already includes:

- `rooms`
- `walls`
- `openings`
- `cad_traces`
- `boundaries`
- `boundary_nodes`

Assembly Inspector v1 is therefore primarily:
- presentation restructuring
- cross-linking
- layering fixes
- better surfacing of existing model semantics

## Technical Approach

### Frontend

Primary files likely affected:
- `frontend/src/features/catalogInspector/CatalogInspectorPage.tsx`
- `frontend/src/features/catalogInspector/CatalogInspectorCanvas.tsx`
- `frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx`
- `frontend/src/features/catalogInspector/types.ts`
- `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx`

Likely additions:
- a small presentational component for the parts panel
- a small presentational component for the glossary

### Backend

No backend algorithm change is required for v1 unless we discover missing cross-links while rendering the assembly view.

## Success Criteria

Assembly Inspector v1 is successful when:

1. a user can identify every visible element as one of:
   - raw trace
   - node
   - boundary
   - wall
   - opening
   - room

2. exact boundaries are no longer visually hidden by room fills

3. the left panel gives a structured count and toggle list of model pieces

4. selecting any piece reveals what it is, what supports it, and what it supports

5. the screen makes it obvious which pieces are canonical executor candidates (`boundary + node`) versus evidence (`raw trace`) or derived semantics (`wall`, `room`)

## Testing Strategy

### Frontend tests

Add or extend tests to verify:
- parts panel renders the expected section labels
- glossary renders the expected explanations
- exact boundaries remain visible when enabled
- selecting a boundary / node / trace / opening / room updates the inspector
- unknown-boundary focus queue exists

### Manual verification

Use:
- `http://localhost:5173/?debug=seminole-topology`

Validate:
- layered rendering order
- parts panel counts
- glossary correctness
- piece-by-piece selection behavior

## Risks

### Risk 1: UI overload

The screen could become too dense.

Mitigation:
- group parts by evidence / graph / operable model
- preserve toggles and collapsible sections

### Risk 2: ambiguous cross-links

Some pieces may not yet have perfect links.

Mitigation:
- show “None” honestly where links are still missing
- do not invent ownership

### Risk 3: over-investing in temporary UI

Mitigation:
- keep this contained inside `catalogInspector`
- avoid coupling it to the final chat-first product UX

## Recommendation

Proceed with **Assembly Inspector v1** before pushing deeper into executor work.

Reason:
- it turns the current model into a true inspection surface for rearmable pieces
- it exposes the exact unit that the future executor should operate on
- it helps us detect modeling gaps with much less ambiguity than the current overlay-first screen
