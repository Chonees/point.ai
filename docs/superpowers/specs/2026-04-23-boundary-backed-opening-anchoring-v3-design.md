# Boundary-backed Opening Anchoring v3 Design

## Context

`SEMINOLE2000` now has a mostly-clean structural model:

- `topology_issues = []`
- `wall_graph_issues = []`
- `boundary kinds = { duplicate: 404, exterior: 182, artifact: 106, support: 40, unknown: 14, shared: 10 }`
- `opening confidence = { hosted: 65, unhosted: 56 }`

This means the main bottleneck is no longer wall support or broad boundary ambiguity. The next limiting factor is the remaining `56` unhosted openings.

## Problem

The current opening pipeline still leaves too many door/window clusters unhosted even after canonical-first host ranking and cluster-first grouping.

The remaining unhosted openings are a mixture of:

1. **real openings** that should attach to a canonical boundary-backed host
2. **degenerate fragments / annotation-like geometry** that should not count as executor-grade openings
3. **boundary-adjacent clusters** whose host should be inferred from canonical boundary structure rather than a weaker wall-only view

If we jump to mutability or site-aware mutations now, we risk rehosting or preserving openings on an incomplete host model.

## Goal

Reduce `unhosted_openings` materially while preserving the current structural gains:

- keep `shared = 10`
- keep `exterior = 182`
- keep `support = 40`
- keep `unknown = 14`
- do not regress hosted openings that already attach correctly

## Non-goals

This slice does **not** implement:

- mutability / constraints
- site-aware mutators
- geometry executor
- DXF recompilation

It is strictly about making opening anchoring more canonical and more honest.

## Recommended Approach

### Option A — Boundary-backed Opening Anchoring v3 (**recommended**)

Use the boundary graph as the primary anchoring surface for remaining openings, then derive or confirm wall hosts from canonical structural ownership.

#### Pros
- attacks the current bottleneck directly
- reuses the cleaner boundary-first model
- prepares the model for later rehosting and executor work

#### Cons
- requires deeper logic in `opening_graph.py`
- may require stronger distinction between real openings and degenerate geometry

### Option B — Push directly into mutability

#### Pros
- feels closer to the end goal

#### Cons
- premature with `56` unhosted openings
- would blur diagnostics and execution concerns

### Option C — UI-only triage for unhosted openings

#### Pros
- useful visual debugging

#### Cons
- improves visibility, not the model itself

## Architecture Decision

Choose **Option A**.

The opening graph should become more boundary-aware before the project enters mutability and site-fit mutation work.

## Design

### 1. Canonical boundary-backed host selection

Opening hosting should prefer canonical structural evidence in this order:

1. canonical boundary-backed wall host
2. strong support-backed host
3. weaker inferred wall host
4. unhosted

This means host ranking should incorporate:

- boundary kind / family role when available through the wall host
- confidence and provenance of the wall
- spatial alignment of the opening cluster to the canonical boundary span

### 2. Cluster-first anchoring remains mandatory

The pipeline should continue grouping opening traces into spatial clusters **before** final host assignment.

That remains critical because one physical opening may appear as multiple trace fragments:

- frame lines
- swing lines
- polyline arcs
- duplicated drafting segments

### 3. Real opening vs degenerate opening separation

The pipeline should explicitly separate:

- `hosted` — valid host found
- `unhosted` — real candidate but no confident host yet
- `opening_artifact` or equivalent issue state — cluster is too degenerate to count as executor-grade opening

The exact contract can stay within the existing `issues`/`confidence` model as long as the distinction becomes explicit and auditable.

### 4. Boundary-aware anchoring heuristics

The host search should use not just wall candidates, but the stronger structure implied by:

- canonical boundary alignment
- family/canonical vs duplicate distinction
- support shell proximity when it improves confidence without inventing ownership

### 5. Regression guardrails

A slice only counts as improvement if all of these remain true:

- no regression in boundary graph structural counts
- no reduction in already-hosted opening quality
- lower `unhosted_openings`
- no fake hosts created for annotation/noise

## Files in Scope

### Backend
- `backend/floor_plan_catalog/opening_graph.py`
- `tests/test_floor_plan_catalog_opening_graph.py`

### Export / fixture
- `scripts/export_seminole_topology_fixture.py`
- `frontend/src/features/catalogInspector/catalogInspector.fixture.json`

### Optional UI follow-up if needed
- `frontend/src/features/catalogInspector/CatalogInspectorPage.tsx`
- `frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx`
- `frontend/src/features/catalogInspector/types.ts`

UI changes are secondary for this slice and should only be made if needed to surface the new audit states.

## Testing Strategy

### RED tests first

Add tests for:

1. canonical boundary-backed host preference over weaker alternatives
2. fragmented opening clusters that should resolve to one host
3. real Seminole regression proving `unhosted_openings < 56`
4. guardrail that structural boundary metrics do not regress

### GREEN implementation

Implement the minimal logic needed to satisfy those tests.

### Final verification

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_boundary_graph.py tests/test_floor_plan_catalog_wall_graph.py tests/test_floor_plan_catalog_opening_graph.py tests/test_floor_plan_catalog_topology.py tests/test_floor_plan_catalog_curator.py tests/test_floor_plan_catalog_audit.py -q
npx vitest run --config vitest.config.ts src/App.test.tsx src/features/catalogInspector/CatalogInspectorPage.test.tsx --pool=threads
cmd /c curl -I http://localhost:5173/?debug=seminole-topology
```

## Success Criteria

This slice is successful if:

- `unhosted_openings` drops below `56`
- current boundary graph gains remain intact
- no fake-host regression appears in synthetic tests
- the fixture and inspector reflect the stronger opening-host model honestly

## Why this is the smart next step

The project is already strong at understanding floor plan structure.

The next smartest move is not to rush into site-aware mutation. It is to finish the host model for openings so that later boundary moves and reconstruction rules operate on a more trustworthy plan.
