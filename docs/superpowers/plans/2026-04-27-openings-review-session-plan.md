# Openings Review Session Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore legacy-style automatic door/window annotations and add a minimal session-only review UI that lets users move or delete openings before regenerating the DXF.

**Architecture:** Re-enable the ensemble annotation-first openings path in the backend, expose those annotations through the API, and add a lightweight frontend editor on top of the uploaded image. Corrections remain in local component state and are sent back only when generating the DXF.

**Tech Stack:** FastAPI, Python 3.14, React 19, TypeScript, Vitest, pytest.

---

## File Map

- Modify: `backend/models.py` — recover request/response annotation contracts.
- Modify: `backend/app.py` — expose `auto_annotations` in v2 responses and pass reviewed annotations into DXF generation.
- Modify: `backend/services/parse_service.py` — preserve inference metadata needed by the review flow.
- Modify: `backend/services/generate_dxf_service.py` — prefer reviewed session annotations over backend auto annotations.
- Modify: `backend/ensemble_inference.py` — restore legacy-style opening auto-annotations with semantic fallbacks.
- Modify: `tests/test_ensemble_inference.py` — lock restored openings behavior.
- Modify: `tests/test_v2_api.py` — lock API contract for `auto_annotations` and reviewed annotations.
- Modify: `frontend/src/types.ts` — restore annotation types in the client contract.
- Modify: `frontend/src/features/workspace/useGenerateDxf.ts` — split detect/review state from DXF generation and send reviewed annotations when present.
- Modify: `frontend/src/components/UploadPanel.tsx` — own session-only reviewed openings state.
- Modify: `frontend/src/features/workspace/WorkspaceOutput.tsx` — render review UI and DXF regeneration action.
- Create: `frontend/src/features/workspace/openingsReview.ts` — pure helpers for filtering, translating, and serializing opening annotations.
- Create: `frontend/src/features/workspace/OpeningsReviewCanvas.tsx` — lightweight drag/delete editor for door/window annotations.
- Create/Modify: `frontend/src/features/workspace/openingsReview.test.ts` and `frontend/src/features/workspace/useGenerateDxf.test.ts` — frontend regression coverage.

### Task 1: Lock backend contract regressions with failing tests

**Files:**
- Modify: `tests/test_ensemble_inference.py`
- Modify: `tests/test_v2_api.py`

- [ ] **Step 1: Add a failing regression test that ensemble restores auto door/window annotations**

```python
def test_infer_ensemble_restores_auto_annotations_for_openings(monkeypatch):
    _patch_models(
        monkeypatch,
        cubicasa_openings=[
            {
                "id": "door-1",
                "kind": "door",
                "position": {"x": 110.0, "y": 74.0},
                "span": 28.0,
                "orientation": "vertical",
                "confidence": 0.9,
                "door_type": "normal",
                "swing": None,
            },
            {
                "id": "window-1",
                "kind": "window",
                "position": {"x": 60.0, "y": 20.0},
                "span": 24.0,
                "orientation": "horizontal",
                "confidence": 0.85,
            },
        ],
    )

    result = infer_ensemble("data:image/png;base64,AAAA")

    assert [ann["type"] for ann in result["_auto_annotations"]] == ["door", "window"]
```

- [ ] **Step 2: Add a failing regression test that generate-dxf accepts reviewed annotations**

```python
def test_generate_dxf_endpoint_uses_reviewed_opening_annotations(monkeypatch):
    captured = {}

    def fake_generate_dxf(*, parsed, out_path, dxf_mode, image_b64):
        captured["auto_annotations"] = parsed["_infer_result"].get("_auto_annotations", [])
        return {"dxf_preview": None}

    monkeypatch.setattr("backend.app.generate_dxf", fake_generate_dxf)
    monkeypatch.setattr("backend.services.parse_service.infer_structure", lambda image, **_: build_mitunet_infer_result())

    response = client.post(
        "/api/v2/generate-dxf",
        json={
            "image": build_synthetic_structure_image(),
            "model_variant": "ensemble",
            "annotations": [
                {"type": "window", "x1": 10.0, "y1": 20.0, "x2": 30.0, "y2": 20.0, "swing": "down"},
            ],
        },
    )

    assert response.status_code == 200, response.text
    assert captured["auto_annotations"][0]["x1"] == 10.0
```

- [ ] **Step 3: Run the targeted backend tests and verify RED**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_ensemble_inference.py tests/test_v2_api.py -q
```

Expected: FAIL because the current API no longer exposes reviewed opening annotations end-to-end.

### Task 2: Restore reviewed opening annotations in the backend

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/app.py`
- Modify: `backend/services/generate_dxf_service.py`
- Modify: `backend/ensemble_inference.py`

- [ ] **Step 1: Recover annotation fields in the API models**
- [ ] **Step 2: Thread optional request annotations from `/api/v2/generate-dxf` into the parsed payload**
- [ ] **Step 3: Make `mask_regions` DXF generation prefer reviewed request annotations when present**
- [ ] **Step 4: Restore ensemble `_auto_annotations` for `door/window` and auto-fill missing door/window semantics**
- [ ] **Step 5: Re-run the backend tests and verify GREEN**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_ensemble_inference.py tests/test_v2_api.py -q
```

Expected: PASS.

### Task 3: Lock frontend review-flow regressions with failing tests

**Files:**
- Create: `frontend/src/features/workspace/openingsReview.test.ts`
- Modify: `frontend/src/features/workspace/useGenerateDxf.test.ts`

- [ ] **Step 1: Add a failing helper test for filtering only door/window annotations**
- [ ] **Step 2: Add a failing helper test for translating an opening by drag delta**
- [ ] **Step 3: Add a failing hook test that reviewed annotations are sent on regenerate**
- [ ] **Step 4: Run only the frontend workspace tests and verify RED**

Run:

```bash
npm --prefix frontend test -- src/features/workspace/openingsReview.test.ts src/features/workspace/useGenerateDxf.test.ts
```

Expected: FAIL because no review helpers or reviewed-annotation request path exist yet.

### Task 4: Implement the minimal session-only review UI

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/features/workspace/useGenerateDxf.ts`
- Modify: `frontend/src/components/UploadPanel.tsx`
- Modify: `frontend/src/features/workspace/WorkspaceOutput.tsx`
- Create: `frontend/src/features/workspace/openingsReview.ts`
- Create: `frontend/src/features/workspace/OpeningsReviewCanvas.tsx`

- [ ] **Step 1: Restore shared annotation types for door/window review in the frontend contract**
- [ ] **Step 2: Add pure helper functions for filtering/serializing/translating opening annotations**
- [ ] **Step 3: Extend `useGenerateDxf` so it can send reviewed annotations on regenerate**
- [ ] **Step 4: Add session-only openings review state to `UploadPanel`**
- [ ] **Step 5: Render a lightweight review canvas in `WorkspaceOutput` with select/drag/delete only**
- [ ] **Step 6: Re-run the frontend workspace tests and verify GREEN**

Run:

```bash
npm --prefix frontend test -- src/features/workspace/openingsReview.test.ts src/features/workspace/useGenerateDxf.test.ts
```

Expected: PASS.

### Task 5: Verify the integrated workflow

**Files:**
- Test only

- [ ] **Step 1: Run the focused backend verification suite**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_ensemble_inference.py tests/test_v2_api.py tests/test_plan_parser.py tests/test_quality_gate.py -q
```

- [ ] **Step 2: Run the focused frontend verification suite**

```bash
npm --prefix frontend test -- src/features/workspace/openingsReview.test.ts src/features/workspace/useGenerateDxf.test.ts
```

- [ ] **Step 3: Review git diff for only the intended backend/frontend files**
- [ ] **Step 4: Commit with a conventional message**

```bash
git add backend frontend tests docs/superpowers/specs/2026-04-27-openings-review-design.md docs/superpowers/plans/2026-04-27-openings-review-session-plan.md
git commit -m "feat(openings): restore reviewed session annotations"
```
