# Stronger Opening Hosting v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve opening hosting so significantly more door/window traces resolve to canonical hosts, reducing unhosted openings below the current `111` baseline.

**Architecture:** Keep the pipeline boundary-first. Strengthen `opening_graph.py` so host ranking prefers canonical graph-backed walls over duplicate/secondary pieces, improve grouping of fragmented traces, then regenerate the real fixture and surface the stronger hosting state in the inspector.

**Tech Stack:** Python 3.14, Pydantic, pytest, React, TypeScript, Vitest, existing Seminole fixture/export pipeline.

---

## File Structure

### Existing files to modify
- `backend/floor_plan_catalog/opening_graph.py` — stronger host ranking, duplicate-aware canonical preference, grouping improvements
- `tests/test_floor_plan_catalog_opening_graph.py` — RED/GREEN coverage for canonical preference and grouping
- `scripts/export_seminole_topology_fixture.py` — regenerate fixture after backend changes (likely no code change)
- `frontend/src/features/catalogInspector/catalogInspector.fixture.json` — updated real fixture
- `frontend/src/features/catalogInspector/CatalogInspectorPage.tsx` — if needed, tighten hosted/unhosted metrics wording
- `frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx` — if needed, surface richer opening confidence/issues
- `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx` — UI assertions if wording/metadata changes

### Verification targets
- `tests/test_floor_plan_catalog_opening_graph.py`
- `tests/test_floor_plan_catalog_boundary_graph.py`
- `tests/test_floor_plan_catalog_wall_graph.py`
- `tests/test_floor_plan_catalog_topology.py`
- `tests/test_floor_plan_catalog_curator.py`
- `tests/test_floor_plan_catalog_audit.py`
- `frontend/src/App.test.tsx`
- `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx`

---

### Task 1: Add the failing backend tests for stronger opening hosting

**Files:**
- Modify: `tests/test_floor_plan_catalog_opening_graph.py`
- Test: `tests/test_floor_plan_catalog_opening_graph.py`

- [ ] **Step 1: Add a synthetic canonical-vs-duplicate host preference test**

```python
def test_opening_graph_prefers_canonical_host_over_duplicate_wall_candidate():
    seed = build_seed_with_duplicate_host_candidates()
    topology = derive_floor_plan_topology(seed)
    wall_graph = derive_floor_plan_wall_graph(topology, seed.cad_traces)

    opening_graph = derive_floor_plan_opening_graph(topology, wall_graph, seed.cad_traces)
    door = next(opening for opening in opening_graph.openings if opening.opening_kind == "door")

    assert door.host_wall_id is not None
    assert door.confidence != "unhosted"
```

- [ ] **Step 2: Add a grouping test for fragmented traces on the same host**

```python
def test_opening_graph_groups_fragmented_window_traces_on_same_host():
    seed = build_seed_with_fragmented_window_traces()
    topology = derive_floor_plan_topology(seed)
    wall_graph = derive_floor_plan_wall_graph(topology, seed.cad_traces)

    opening_graph = derive_floor_plan_opening_graph(topology, wall_graph, seed.cad_traces)
    windows = [opening for opening in opening_graph.openings if opening.opening_kind == "window"]

    assert len(windows) == 1
    assert windows[0].host_wall_id is not None
    assert len(windows[0].trace_ids) == 2
```

- [ ] **Step 3: Tighten the Seminole regression assertion**

```python
def test_seminole_opening_graph_reduces_unhosted_openings_after_stronger_hosting():
    seed = load_seminole_seed()
    topology = derive_floor_plan_topology(seed)
    wall_graph = derive_floor_plan_wall_graph(topology, seed.cad_traces)

    opening_graph = derive_floor_plan_opening_graph(topology, wall_graph, seed.cad_traces)
    unhosted = [opening for opening in opening_graph.openings if opening.host_wall_id is None]

    assert len(unhosted) < 111
```

- [ ] **Step 4: Add the synthetic fixture builders**

Use the same file to add compact builders for:
- `build_seed_with_duplicate_host_candidates()`
- `build_seed_with_fragmented_window_traces()`

with small rectangular rooms and explicit duplicate/canonical wall conditions.

- [ ] **Step 5: Run the backend RED test**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_opening_graph.py -q
```

Expected:
- FAIL because the current hoster does not yet prefer canonical hosts strongly enough and does not reduce Seminole `unhosted` below `111`

- [ ] **Step 6: Commit the RED test**

```bash
git add tests/test_floor_plan_catalog_opening_graph.py
git commit -m "test: cover stronger opening hosting"
```

---

### Task 2: Implement canonical-first host selection and stronger grouping

**Files:**
- Modify: `backend/floor_plan_catalog/opening_graph.py`
- Test: `tests/test_floor_plan_catalog_opening_graph.py`

- [ ] **Step 1: Add host ranking helpers**

Implement helpers that rank candidates by:
1. canonical over duplicate
2. better boundary kind for the opening kind
3. lower axis gap
4. higher overlap

- [ ] **Step 2: Make `_find_host_wall(...)` canonical-first**

Update the score to explicitly penalize walls that map to duplicate family members and reward stronger host semantics.

- [ ] **Step 3: Tighten grouping of fragmented traces**

Adjust the grouping key so fragmented traces on the same host and near-contiguous interval bucket together more reliably without mixing different opening kinds.

- [ ] **Step 4: Improve opening confidence / issues**

If needed, emit clearer values such as:
- `hosted`
- `unhosted`

plus issues like:
- `ambiguous_host_candidates`
- `host_only_duplicate_candidate`
- `insufficient_host_overlap`

only when they are actually justified by the match.

- [ ] **Step 5: Run the backend GREEN test**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_opening_graph.py -q
```

Expected:
- PASS
- synthetic canonical-preference/grouping cases pass
- Seminole unhosted count drops below `111`

- [ ] **Step 6: Commit**

```bash
git add backend/floor_plan_catalog/opening_graph.py tests/test_floor_plan_catalog_opening_graph.py
git commit -m "feat: strengthen opening host selection"
```

---

### Task 3: Regenerate fixture and surface the stronger hosting state in the inspector

**Files:**
- Modify: `frontend/src/features/catalogInspector/catalogInspector.fixture.json`
- Modify if needed: `frontend/src/features/catalogInspector/CatalogInspectorPage.tsx`
- Modify if needed: `frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx`
- Modify if needed: `frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx`

- [ ] **Step 1: Regenerate the real Seminole fixture**

Run:

```bash
.\.venv\Scripts\python.exe scripts/export_seminole_topology_fixture.py D:\PointAIData\PLANS\catalog\seminole-2000.json --output frontend/src/features/catalogInspector\catalogInspector.fixture.json
```

- [ ] **Step 2: Inspect the new hosting breakdown**

Check and note:
- `hosted openings`
- `unhosted openings`
- hosted doors vs windows

- [ ] **Step 3: If the UI needs it, add clearer hosted/unhosted messaging**

If changed, keep it minimal and aligned with the current inspector.

- [ ] **Step 4: Run the focused frontend test**

Run:

```bash
cmd /c npm --prefix frontend test -- src/features/catalogInspector/CatalogInspectorPage.test.tsx
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/catalogInspector/catalogInspector.fixture.json frontend/src/features/catalogInspector/CatalogInspectorPage.tsx frontend/src/features/catalogInspector/CatalogInspectorSidebar.tsx frontend/src/features/catalogInspector/CatalogInspectorPage.test.tsx
git commit -m "feat: refresh inspector with stronger opening hosting"
```

---

### Task 4: Run full verification and capture the new state

**Files:**
- Modify: `D:\obsidian\vault\01 - Projects\Point.ai\Current State.md`
- Create: `D:\obsidian\vault\01 - Projects\Point.ai\Implementation\2026-04-22 - Stronger Opening Hosting v2.md`

- [ ] **Step 1: Run the full backend regression suite**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_boundary_graph.py tests/test_floor_plan_catalog_wall_graph.py tests/test_floor_plan_catalog_opening_graph.py tests/test_floor_plan_catalog_topology.py tests/test_floor_plan_catalog_curator.py tests/test_floor_plan_catalog_audit.py -q
```

Expected:
- PASS
- no regression in wall/boundary support

- [ ] **Step 2: Run the frontend verification**

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

Append the actual hosted/unhosted delta and what changed in host selection.

- [ ] **Step 5: Confirm clean git status**

Run:

```bash
git status --short
```

Expected:
- empty output

---

## Self-Review

### Spec coverage
- canonical-first hosting: covered in Task 2
- grouping fragmented opening traces: covered in Tasks 1 and 2
- Seminole reduction of unhosted openings: covered in Tasks 1, 2, and 4
- inspector visibility of stronger hosting state: covered in Task 3

### Placeholder scan
- No TBD/TODO placeholders remain
- Exact files, commands, and expected outcomes are present

### Type consistency
- The plan consistently refers to the current `CatalogOpening` contract and existing inspector fixture schema
- No invented API names outside the proposed helper/refinement scope
