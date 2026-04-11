# Pre-deploy Modularization Audit

## Executive Summary

The app is already functional, but it is **not yet structured like a deployment-ready product**. The main risk is not one catastrophic bug: it is **accumulated coupling** across frontend UI flows, backend orchestration, and stale test/training artifacts.

The biggest problems are:

1. **Large multi-responsibility files** in both frontend and backend.
2. **Missing or broken boundaries** between UI, orchestration, persistence, and inference.
3. **Test suite drift**: several tests point to deleted training modules and currently fail at collection time.
4. **Pre-deploy config debt**: hardcoded CORS and deprecated FastAPI startup events.
5. **Frontend persistence typing debt**: the current Supabase type layer is not cleanly wired and TypeScript no-emit fails in `useProject.ts`.

This should be addressed **before deployment**.

---

## Verified Findings

### 1. Frontend shell is too coupled

#### `frontend/src/App.tsx`
- `frontend/src/App.tsx:17-23` wires auth, project list, plan list, page state, and save state in one component.
- `frontend/src/App.tsx:51-63` branches login/projects/editor in the same file.

**Problem**:
- App-level routing, persistence coordination, and page composition are mixed.
- This file is becoming a god-shell instead of a thin composition root.

**Refactor target**:
- `app-shell/`
  - `AppRouter.tsx`
  - `AuthGate.tsx`
  - `EditorPage.tsx`
  - `ProjectsPage.tsx`
  - `WorkspaceHeader.tsx`

---

### 2. Frontend persistence logic is bundled into one hook file

#### `frontend/src/hooks/useProject.ts`
- `frontend/src/hooks/useProject.ts:61` `useProjectList`
- `frontend/src/hooks/useProject.ts:130` `usePlanList`
- `frontend/src/hooks/useProject.ts:197` `usePlanSave`
- direct Supabase calls at `:113`, `:119`, `:180`, `:186`, `:222`

**Problem**:
- Data mapping, repository logic, and UI hooks live together.
- The file also contains the currently failing Supabase update typing path.

**Refactor target**:
- `frontend/src/features/projects/`
  - `project.types.ts`
  - `project.mappers.ts`
  - `project.repository.ts`
  - `useProjectList.ts`
  - `usePlanList.ts`
  - `usePlanSave.ts`

**Pre-deploy blocker**:
- `npx tsc -p tsconfig.app.json --noEmit` fails here because the Supabase generic types currently collapse to `never`.

---

### 3. UploadPanel is doing orchestration, state adaptation, persistence coordination, and UI

#### `frontend/src/components/UploadPanel.tsx`
- generation pipeline starts at `frontend/src/components/UploadPanel.tsx:101`
- computed room merging at `:162-171`
- 2D/3D editor branching at `:357-371`
- scene coordination through `notifySceneChange` at `:62`

**Problem**:
- Upload UI, request serialization, backend response normalization, label enrichment, and rendering are coupled.
- This makes the component hard to test and hard to evolve.

**Refactor target**:
- `frontend/src/features/workspace/`
  - `useGenerateDxf.ts`
  - `useComputedRoomMerge.ts`
  - `PlanSourceCard.tsx`
  - `PlanMetadataCard.tsx`
  - `WorkspaceOutput.tsx`
  - `RawStructurePanel.tsx`

---

### 4. ProjectList is effectively two screens in one file

#### `frontend/src/components/ProjectList/ProjectList.tsx`
- create project logic at `:68`
- create plan logic at `:77`
- rename logic at `:86`
- projects render loop at `:188`
- plans render loop at `:307`

**Problem**:
- Sidebar, project header, plan grid, editable naming, and CRUD actions live together.
- It is maintainable today only because the product is still small.

**Refactor target**:
- `frontend/src/features/projects/components/`
  - `ProjectsSidebar.tsx`
  - `ProjectStatsHeader.tsx`
  - `PlansGrid.tsx`
  - `PlanCard.tsx`
  - `EditableNameField.tsx`

---

### 5. OverlayEditor is a classic monolith

#### `frontend/src/components/OverlayEditor/OverlayEditor.tsx`
- root editor starts at `:9`
- render loop at `:203`
- mouse down at `:259`
- mouse move at `:364`
- mouse up at `:444`
- label popup state at `:440`
- toolbar config at `:567`

**Problem**:
- Canvas interaction state, painting, hit testing, fullscreen layout, toolbar, label dialog, and door swing flows live in one file.
- This is the kind of file that becomes unmaintainable FAST.

**Refactor target**:
- `frontend/src/components/OverlayEditor/`
  - `OverlayEditor.tsx` (thin composition)
  - `useOverlayEditorState.ts`
  - `useCanvasViewport.ts`
  - `usePaintLayer.ts`
  - `OverlayToolbar.tsx`
  - `OverlayCanvas.tsx`
  - `RoomLabelDialog.tsx`
  - `types.ts`

**Good news**:
- `geometry.ts` and `renderCanvas.ts` already exist. That means the file has already started to split. We should continue that direction hard.

---

### 6. FloorPlan3D is too large for one feature file

#### `frontend/src/components/FloorPlan3D/FloorPlan3D.tsx`
- 990 lines total
- major sections include:
  - `SceneRenderer` at `:108`
  - `SceneWorld` at `:130`
  - `SceneLighting` at `:208`
  - `FloorMesh` at `:357`
  - `GhostPreview` at `:391`
  - `WallMesh` at `:468`
  - `FurnitureMesh` at `:532`
  - `FloorPlan3D` root at `:583`

**Problem**:
- World rendering, mesh generation, placement state, ghost preview logic, scene effects, and furniture editing are all packed together.

**Refactor target**:
- `frontend/src/components/FloorPlan3D/scene/`
  - `SceneRenderer.tsx`
  - `SceneWorld.tsx`
  - `SceneLighting.tsx`
  - `SceneEffects.tsx`
- `frontend/src/components/FloorPlan3D/meshes/`
  - `FloorMesh.tsx`
  - `WallMesh.tsx`
  - `OpeningMesh.tsx`
  - `FurnitureMesh.tsx`
  - `GhostPreview.tsx`
- `frontend/src/components/FloorPlan3D/hooks/`
  - `usePlacementHandlers.ts`
  - `useSceneMaterials.ts`
  - `useScenePersistence.ts`

---

### 7. Backend API orchestration is too fat

#### `backend/app.py`
- hardcoded CORS at `backend/app.py:49`
- deprecated startup event at `:61`
- `/api/v2/generate-dxf` starts at `:129`
- endpoint does parsing, mode selection, region pipeline orchestration, DXF generation, preview generation, artifact persistence, and response shaping

**Problem**:
- HTTP layer is coordinating application services directly.
- This is the backend equivalent of a god-controller.

**Refactor target**:
- `backend/api/`
  - `routes.py`
  - `lifespan.py`
- `backend/services/`
  - `parse_structure_service.py`
  - `generate_dxf_service.py`
  - `artifact_service.py`
  - `preview_service.py`
- `backend/config.py`
  - env-driven CORS, DXF directory, feature flags

**Pre-deploy blockers**:
- hardcoded localhost CORS
- deprecated FastAPI `@app.on_event("startup")`

---

### 8. MitUNet inference file has too many responsibilities

#### `backend/mitunet_inference.py`
- inference at `:288`
- region planning at `:1125`
- DXF generation at `:1429`
- dimensions/labels injection at `:1510`

**Problem**:
- model runtime, image transforms, wall extraction, region extraction, DXF drawing, and label/dimension integration all sit in one file.
- This is too risky to evolve safely.

**Refactor target**:
- `backend/mitunet/`
  - `model.py`
  - `preprocess.py`
  - `wall_mask.py`
  - `regions.py`
  - `transform.py`
  - `dxf_writer.py`
  - `pipeline.py`

---

### 9. Dimension logic is still too centralized

#### `backend/components/dimensions.py`
- room metric logic at `backend/components/dimensions.py:396`
- room label rendering at `:548`
- all dimension generation at `:623`

**Problem**:
- formatting, exterior geometry, room metrics, DXF writing, and audit summarization are in one module.

**Refactor target**:
- `backend/components/dimensions/`
  - `formatting.py`
  - `coord_transform.py`
  - `exterior_segments.py`
  - `room_metrics.py`
  - `room_labels.py`
  - `audit.py`
  - `generator.py`

---

### 10. Scale calibration and room analysis should be separated

#### `backend/scale_calibrator.py`
- `calibrate_scale` at `:18`
- `analyze_labeled_rooms` at `:184`
- `flood_fill_room_region` at `:310`
- `generate_region_overlay` at `:414`

**Problem**:
- calibration, flood-fill room extraction, overlap analysis, and visualization are mixed.

**Refactor target**:
- `backend/measurement/`
  - `calibration.py`
  - `room_analysis.py`
  - `flood_fill.py`
  - `region_overlay.py`
  - `formatting.py`

---

### 11. Benchmark code should not live in the runtime backend root

#### `backend/benchmark.py`
- 1608 lines
- only referenced by itself and `tests/test_benchmark.py`

**Problem**:
- It bloats the runtime package namespace even though it is evaluation infrastructure, not request-serving code.
- Same issue for some dataset/training tooling nearby.

**Refactor target**:
- move to `backend/evaluation/benchmark.py` or `scripts/benchmark_pipeline.py`
- keep the production backend namespace focused on serving and generation

---

### 12. Test suite has real drift and false confidence risk

#### Broken collection
Running `python -m pytest tests --collect-only -q` produced 69 collected tests but **8 collection errors**.

Broken imports include:
- `tests/test_cubicasa_conversion.py:9` -> `training.convert_cubicasa`
- `tests/test_dataset_audit.py:9` -> `training.convert_resplan`
- `tests/test_materialize_dataset.py:6` -> `training.convert_resplan`
- `tests/test_prepare_combined_training.py:10` -> `training.convert_resplan`
- `tests/test_prepare_curated_training.py:5` -> `training.convert_resplan`
- `tests/test_resplan_conversion.py:9` -> `training.convert_resplan`
- `tests/test_training_export.py:8` -> `training.export_lmdb`

Those modules do **not** exist anymore in `training/`.

**Problem**:
- the suite is partially stale
- CI cannot be trusted if collection itself is broken
- this is exactly how teams think ?we have tests? while actually shipping blind

**Refactor target**:
- split tests into suites:
  - `tests/unit/`
  - `tests/integration/`
  - `tests/evaluation/`
  - `tests/training/`
- quarantine or delete stale tests referencing removed training modules
- make the default suite green before deployment

---

### 13. There are currently no frontend tests

Verified from `frontend/package.json`:
- scripts: `dev`, `build`, `lint`, `preview`
- no `test` script
- no Vitest/Jest setup

**Problem**:
- the most interaction-heavy surfaces in the product (`UploadPanel`, `OverlayEditor`, `ProjectList`) have no automated safety net.

**Refactor target**:
- add Vitest + Testing Library
- minimum pre-deploy coverage:
  - `useProject` hooks
  - `UploadPanel` request shaping and computed room merge
  - `ProjectList` basic CRUD view behavior
  - `LoginPage` auth mode switching

---

## What can be deleted, quarantined, or moved

### Quarantine from production concerns
- `backend/benchmark.py`
- `tests/test_benchmark.py` and related evaluation helpers should live with evaluation tooling, not be mentally mixed with product-serving tests
- stale training tests referencing removed converters/exporters

### Move out of core runtime mental model
- dataset/training preparation scripts under `training/`
- evaluation/benchmark tooling under `backend/`

### Keep, but split
- `OverlayEditor`
- `FloorPlan3D`
- `UploadPanel`
- `mitunet_inference.py`
- `dimensions.py`
- `scale_calibrator.py`

---

## Pre-deploy Priority Order

### P0 ? Must fix before deploy
1. **Make backend config deployable**
   - remove hardcoded CORS from `backend/app.py`
   - replace deprecated startup event with lifespan
2. **Make the default test run trustworthy**
   - either delete stale tests or move them behind an optional training suite
3. **Fix frontend persistence typing**
   - clean Supabase type integration so TypeScript no-emit passes for real
4. **Define product/runtime boundaries**
   - separate runtime backend from evaluation/training code mentally and structurally

### P1 ? Structural modularization
1. Split `UploadPanel`
2. Split `ProjectList`
3. Split `OverlayEditor`
4. Split `FloorPlan3D`
5. Split `useProject.ts`

### P2 ? Backend service boundaries
1. service layer for parse/generate
2. split MitUNet pipeline by concern
3. split dimensions and calibration packages

### P3 ? Test architecture
1. frontend tests
2. backend suite partitioning
3. evaluation suite separated from product unit tests

---

## Recommended File/Folder Target Architecture

### Frontend

```text
frontend/src/
  app/
    AppRouter.tsx
    AuthGate.tsx
    WorkspaceShell.tsx
  features/
    auth/
      LoginPage.tsx
    projects/
      components/
      hooks/
      repository/
      types/
    workspace/
      components/
      hooks/
      api/
    overlay-editor/
      components/
      hooks/
      canvas/
      geometry/
    floorplan-3d/
      components/
      hooks/
      scene/
      meshes/
      catalog/
  lib/
  utils/
```

### Backend

```text
backend/
  api/
    routes.py
    lifespan.py
  services/
    parse_structure_service.py
    generate_dxf_service.py
    artifact_service.py
    preview_service.py
  mitunet/
    model.py
    preprocess.py
    wall_mask.py
    regions.py
    transform.py
    dxf_writer.py
    pipeline.py
  measurement/
    calibration.py
    room_analysis.py
    flood_fill.py
    region_overlay.py
  components/
    dimensions/
      formatting.py
      coord_transform.py
      exterior_segments.py
      room_metrics.py
      room_labels.py
      audit.py
      generator.py
  evaluation/
    benchmark.py
```

---

## Hard Recommendation

Do **not** deploy first and ?clean later?. That?s the trap.

The serious move is:
1. **stabilize runtime/test/config boundaries**
2. **split the biggest god-files**
3. **only then ship**

If we skip this, every next feature is going to cost more, break more, and take longer.

That?s not architecture. That?s debt with makeup.
