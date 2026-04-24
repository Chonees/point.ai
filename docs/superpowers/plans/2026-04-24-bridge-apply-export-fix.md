# Bridge Apply Export Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the misleading bridge-lane CAD overlay export with a true export path from the applied `site_fit` result.

**Architecture:** Keep `cad-review` as a diagnostic-only artifact in bridge mode, then add a dedicated backend export path that persists the bridge apply snapshot and renders the applied `SEMINOLE2000` geometry using the `registration_summary.transform` plus the uploaded site-plan entities. Surface that real export URL only from the `site-fit-apply` artifact.

**Tech Stack:** FastAPI, Python, ezdxf, pytest, React, TypeScript, Vitest.

---

## File Map

### Backend
- Create: `backend/site_fit_bridge/exporter.py` — DXF exporter for applied bridge result.
- Modify: `backend/site_fit_bridge/contracts.py` — add `cad_analysis_id` to apply request and `apply_id`/`export_url` to apply response.
- Modify: `backend/services/site_fit_bridge_service.py` — persist apply snapshots, serve real export path, and use CAD snapshot + applied site-fit result.
- Modify: `backend/app.py` — add bridge export route.
- Modify: `tests/test_site_fit_bridge_api.py` — verify apply returns export URL and exported DXF reflects applied plan dimensions.

### Frontend
- Modify: `frontend/src/features/siteFit/contracts.ts` — add `cadAnalysisId` to proposal artifact data and `href`/`applyId` to apply artifact data.
- Modify: `frontend/src/features/chatThread/chatAgent.ts` — disable raw CAD export in bridge mode, send `cad_analysis_id` on apply, store returned `export_url` on the apply artifact.
- Modify: `frontend/src/features/chatThread/components/SiteFitApplyArtifactCard.tsx` — show the real export/open CTA.
- Modify: `frontend/src/features/chatThread/chatAgent.test.ts` — verify bridge-mode cad-review export is disabled and apply returns real export href.
- Modify: `frontend/src/App.test.tsx` — verify the applied artifact exposes the new export CTA in chat.

---

### Task 1: Backend real export from apply
- [ ] Write/extend failing API tests for `cad_analysis_id`, `export_url`, and `GET /api/v2/site-fit/bridge/export/{apply_id}`.
- [ ] Run backend bridge tests to verify RED.
- [ ] Implement bridge apply snapshot persistence and DXF export from `apply.applied_plan.plan` + `apply.registration_summary.transform` + uploaded site-plan entities.
- [ ] Add bridge export route and response fields.
- [ ] Run focused backend verification to GREEN.

### Task 2: Frontend wiring to the real export
- [ ] Write failing frontend tests for bridge-mode diagnostic-only cad review and real apply export CTA.
- [ ] Run focused frontend tests to verify RED.
- [ ] Disable/relabel the bridge-mode cad-review export, pass `cadAnalysisId` through proposal/apply payloads, and render the export CTA only on `site-fit-apply`.
- [ ] Run focused frontend verification to GREEN.

### Final verification
- [ ] Run backend: `./.venv/Scripts/python.exe -m pytest tests/test_site_fit_bridge_api.py tests/test_site_fit_api.py tests/test_cad_workspace_api.py -q`
- [ ] Run frontend: `cd frontend && npm test -- chatAgent.test.ts App.test.tsx`
- [ ] Manual smoke expectation: after bridge apply, the visible export comes from `site-fit-apply`, not from `cad-review`.
