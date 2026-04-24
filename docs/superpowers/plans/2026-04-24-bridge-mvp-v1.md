# Bridge MVP v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect runtime site-plan CAD upload to the curated `SEMINOLE2000` payload so chat can propose and apply one honest `site_fit` lane.

**Architecture:** Add one thin backend bridge that adapts `cad_workspace` extraction into `site_fit` inputs, then extend the chat shell with a dedicated site-fit artifact/action flow. The MVP lane stays intentionally narrow: fixed catalog plan, placement anchored from the extracted buildable bbox, and chat-driven propose/apply.

**Tech Stack:** FastAPI, Pydantic, Python pytest, React, TypeScript, Vitest, Testing Library.

---

## File Map

### Backend
- Create: `backend/site_fit_bridge/contracts.py` — combined request/response models for Bridge MVP v1.
- Create: `backend/services/site_fit_bridge_service.py` — orchestrates catalog-plan load, CAD extraction adapter, `site_fit` propose/apply.
- Create: `backend/data/site_fit/seminole-2000.plan.json` — backend-owned curated payload for the fixed MVP lane.
- Modify: `backend/app.py` — add bridge propose/apply endpoints.
- Test: `tests/test_site_fit_bridge_api.py` — end-to-end FastAPI tests for bridge propose/apply.

### Frontend
- Create: `frontend/src/features/siteFit/contracts.ts` — TS contracts for bridge responses and artifact data.
- Create: `frontend/src/features/chatThread/components/SiteFitProposalArtifactCard.tsx` — proposal summary + apply CTA.
- Create: `frontend/src/features/chatThread/components/SiteFitApplyArtifactCard.tsx` — applied-result summary.
- Modify: `frontend/src/features/chatThread/thread.types.ts` — add `site-fit-proposal` and `site-fit-apply` artifact kinds.
- Modify: `frontend/src/features/chatThread/components/ArtifactCard.tsx` — route new artifact kinds.
- Modify: `frontend/src/features/chatThread/components/ThreadMessageList.tsx` — give site-fit cards full-width treatment.
- Modify: `frontend/src/features/chatThread/chatAgent.ts` — call bridge propose endpoint for CAD + Seminole requests; expose apply action helper.
- Modify: `frontend/src/App.tsx` — wire artifact action callback, fix the `planId` catch bug, append apply responses.
- Test: `frontend/src/features/chatThread/chatAgent.test.ts` — bridge propose/apply behavior.
- Test: `frontend/src/features/chatThread/components/ThreadMessageList.test.tsx` — full-width proposal/apply card layout.
- Test: `frontend/src/App.test.tsx` — end-to-end chat submit + apply CTA flow; regression for catch-path thread id.

---

### Task 1: Backend bridge API and catalog lane

**Files:**
- Create: `backend/site_fit_bridge/contracts.py`
- Create: `backend/services/site_fit_bridge_service.py`
- Create: `backend/data/site_fit/seminole-2000.plan.json`
- Modify: `backend/app.py`
- Test: `tests/test_site_fit_bridge_api.py`

- [ ] **Step 1: Write the failing backend bridge tests**

Add `tests/test_site_fit_bridge_api.py` with two API tests:

```python
from pathlib import Path

import ezdxf
from fastapi.testclient import TestClient

from backend.app import app

client = TestClient(app)


def test_bridge_propose_returns_cad_review_site_constraints_and_baseline_candidate(tmp_path: Path):
    dxf_path = tmp_path / 'cad-sheet-dimensions.dxf'
    _write_dimensioned_sheet_dxf(dxf_path)

    with dxf_path.open('rb') as handle:
        response = client.post(
            '/api/v2/site-fit/bridge/propose',
            files={'file': (dxf_path.name, handle, 'application/dxf')},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['pipeline'] == 'site_fit_bridge_mvp_v1'
    assert payload['scope'] == 'seminole-2000-only'
    assert payload['plan_id'] == 'seminole-2000'
    assert payload['proposal']['status'] == 'fit_ready'
    assert payload['proposal']['candidates'][0]['candidate_id'] == 'baseline_preserved'
    assert payload['site_constraints']['placed_plan_footprint']['width'] == 468.0
    assert payload['cad_analysis']['fit_summary']['buildable_polygon']


def test_bridge_apply_reuses_site_constraints_and_applies_selected_candidate(tmp_path: Path):
    dxf_path = tmp_path / 'cad-sheet-dimensions.dxf'
    _write_dimensioned_sheet_dxf(dxf_path)

    with dxf_path.open('rb') as handle:
        propose_response = client.post(
            '/api/v2/site-fit/bridge/propose',
            files={'file': (dxf_path.name, handle, 'application/dxf')},
        )

    assert propose_response.status_code == 200, propose_response.text
    proposal = propose_response.json()
    apply_response = client.post(
        '/api/v2/site-fit/bridge/apply',
        json={
            'plan_id': proposal['plan_id'],
            'site_constraints': proposal['site_constraints'],
            'candidate_id': proposal['proposal']['candidates'][0]['candidate_id'],
        },
    )

    assert apply_response.status_code == 200, apply_response.text
    payload = apply_response.json()
    assert payload['pipeline'] == 'site_fit_bridge_mvp_v1'
    assert payload['apply']['apply_status'] == 'applied'
    assert payload['apply']['candidate_id'] == 'baseline_preserved'
    assert payload['apply']['compliance_summary']['status'] == 'pass'
```

Use the DXF helper by copying `_write_dimensioned_sheet_dxf` (and only the helper pieces it needs) from `tests/test_cad_workspace_api.py` into this test file. Keep the bridge test self-contained.

- [ ] **Step 2: Run the backend bridge tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_site_fit_bridge_api.py -q
```

Expected: FAIL with missing route/import/model errors for `/api/v2/site-fit/bridge/propose` and `/api/v2/site-fit/bridge/apply`.

- [ ] **Step 3: Add bridge contracts and orchestration code**

Create `backend/site_fit_bridge/contracts.py` with models shaped like this:

```python
from pydantic import BaseModel, Field

from ..cad_workspace.contracts import CadWorkspaceExtractResponse
from ..site_fit.contracts import SiteFitApplyResponse, SiteFitProposeResponse


class SiteFitBridgeApplyRequest(BaseModel):
    plan_id: str
    site_constraints: dict
    candidate_id: str


class SiteFitBridgeProposeResponse(BaseModel):
    pipeline: str = 'site_fit_bridge_mvp_v1'
    scope: str = 'seminole-2000-only'
    plan_id: str
    plan_name: str
    cad_analysis: CadWorkspaceExtractResponse
    site_constraints: dict = Field(default_factory=dict)
    proposal: SiteFitProposeResponse
    warnings: list[str] = Field(default_factory=list)


class SiteFitBridgeApplyResponse(BaseModel):
    pipeline: str = 'site_fit_bridge_mvp_v1'
    scope: str = 'seminole-2000-only'
    plan_id: str
    plan_name: str
    apply: SiteFitApplyResponse
    warnings: list[str] = Field(default_factory=list)
```

Create `backend/services/site_fit_bridge_service.py` with four responsibilities:

```python
import json
from pathlib import Path

from ..services.cad_workspace_service import extract_cad_workspace
from ..services.site_fit_service import apply_site_fit, propose_site_fit
from ..site_fit.contracts import SiteFitAnalyzeRequest, SiteFitApplyRequest

CATALOG_PLAN_ID = 'seminole-2000'
CATALOG_PLAN_NAME = 'SEMINOLE2000'
CATALOG_PLAN_PATH = Path(__file__).resolve().parents[1] / 'data' / 'site_fit' / 'seminole-2000.plan.json'


def load_mvp_catalog_plan() -> dict:
    payload = json.loads(CATALOG_PLAN_PATH.read_text(encoding='utf-8'))
    payload['unit'] = payload.get('unit') or payload.get('canonical_unit') or 'inch'
    payload['name'] = payload.get('name') or CATALOG_PLAN_NAME
    return payload


def build_mvp_site_constraints(cad_analysis: dict, plan_payload: dict) -> tuple[dict, list[str]]:
    fit = cad_analysis.get('fit_summary') or {}
    buildable_bbox = fit.get('buildable_bbox')
    if not buildable_bbox:
        raise ValueError('Bridge MVP v1 needs an extracted buildable bbox.')
    plan_bbox = plan_payload.get('footprint_bbox') or {}
    return {
        'unit': cad_analysis.get('canonical_unit') or 'inch',
        'placed_plan_footprint': {
            'x': buildable_bbox['x1'],
            'y': buildable_bbox['y1'],
            'width': plan_bbox['width'],
            'height': plan_bbox['height'],
        },
        'buildable_envelope': {
            'x': buildable_bbox['x1'],
            'y': buildable_bbox['y1'],
            'width': buildable_bbox['width'],
            'height': buildable_bbox['height'],
        },
        'buildable_polygon': fit.get('buildable_polygon') or [],
    }, [
        'Bridge MVP v1 anchors SEMINOLE2000 at the buildable bbox origin for a fixed 1:1 registration lane.',
    ]


def propose_mvp_site_fit(*, filename: str, data: bytes) -> dict:
    cad_analysis = extract_cad_workspace(filename=filename, data=data)
    plan_payload = load_mvp_catalog_plan()
    site_constraints, warnings = build_mvp_site_constraints(cad_analysis, plan_payload)
    proposal = propose_site_fit(SiteFitAnalyzeRequest(plan=plan_payload, site_constraints=site_constraints))
    return {
        'plan_id': CATALOG_PLAN_ID,
        'plan_name': plan_payload['name'],
        'cad_analysis': cad_analysis,
        'site_constraints': site_constraints,
        'proposal': proposal,
        'warnings': warnings + list(cad_analysis.get('warnings') or []),
    }


def apply_mvp_site_fit(req) -> dict:
    if req.plan_id != CATALOG_PLAN_ID:
        raise ValueError('Bridge MVP v1 only supports SEMINOLE2000.')
    plan_payload = load_mvp_catalog_plan()
    applied = apply_site_fit(
        SiteFitApplyRequest(
            plan=plan_payload,
            site_constraints=req.site_constraints,
            candidate_id=req.candidate_id,
        )
    )
    return {
        'plan_id': CATALOG_PLAN_ID,
        'plan_name': plan_payload['name'],
        'apply': applied,
        'warnings': [
            'Bridge MVP v1 is a fixed SEMINOLE2000 lane and does not generalize catalog selection yet.',
        ],
    }
```

Copy the backend-owned JSON payload from `frontend/src/features/catalogInspector/catalogInspector.fixture.json` into `backend/data/site_fit/seminole-2000.plan.json` and do not read frontend assets from backend code.

- [ ] **Step 4: Wire the backend endpoints**

Modify `backend/app.py` to add:

```python
from .site_fit_bridge.contracts import SiteFitBridgeApplyRequest, SiteFitBridgeApplyResponse, SiteFitBridgeProposeResponse
from .services.site_fit_bridge_service import apply_mvp_site_fit, propose_mvp_site_fit


@app.post('/api/v2/site-fit/bridge/propose', response_model=SiteFitBridgeProposeResponse)
async def api_site_fit_bridge_propose(file: UploadFile = File(...)):
    try:
        data = await file.read()
        return SiteFitBridgeProposeResponse(**propose_mvp_site_fit(filename=file.filename or 'upload.dxf', data=data))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post('/api/v2/site-fit/bridge/apply', response_model=SiteFitBridgeApplyResponse)
async def api_site_fit_bridge_apply(req: SiteFitBridgeApplyRequest):
    try:
        return SiteFitBridgeApplyResponse(**apply_mvp_site_fit(req))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
```

- [ ] **Step 5: Run the backend bridge tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_site_fit_bridge_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit the backend bridge slice**

```powershell
git add backend/app.py backend/site_fit_bridge/contracts.py backend/services/site_fit_bridge_service.py backend/data/site_fit/seminole-2000.plan.json tests/test_site_fit_bridge_api.py
git commit -m "feat(site-fit): add bridge mvp backend lane"
```

---

### Task 2: Chat artifact contracts and rendering

**Files:**
- Create: `frontend/src/features/siteFit/contracts.ts`
- Create: `frontend/src/features/chatThread/components/SiteFitProposalArtifactCard.tsx`
- Create: `frontend/src/features/chatThread/components/SiteFitApplyArtifactCard.tsx`
- Modify: `frontend/src/features/chatThread/thread.types.ts`
- Modify: `frontend/src/features/chatThread/components/ArtifactCard.tsx`
- Modify: `frontend/src/features/chatThread/components/ThreadMessageList.tsx`
- Test: `frontend/src/features/chatThread/components/ThreadMessageList.test.tsx`

- [ ] **Step 1: Write the failing artifact rendering tests**

Extend `frontend/src/features/chatThread/components/ThreadMessageList.test.tsx` with one proposal card case and one applied-result case:

```tsx
it('renders site-fit proposal artifacts full-width and exposes the apply action', () => {
  const onApply = vi.fn()
  const messages: ThreadMessage[] = [{
    id: 'm-1',
    role: 'assistant',
    content: 'Te dejo la propuesta.',
    createdAtIso: '2026-04-24T18:00:00.000Z',
    artifacts: [{
      id: 'proposal-1',
      kind: 'site-fit-proposal',
      title: 'SEMINOLE2000 proposal',
      proposal: {
        planId: 'seminole-2000',
        planName: 'SEMINOLE2000',
        candidateId: 'baseline_preserved',
        siteConstraints: { unit: 'inch' },
        summary: 'Keep the current plan unchanged.',
        fitStatus: 'fit_ready',
        warnings: [],
      },
    }],
  }]

  const { container } = render(<ThreadMessageList messages={messages} onApplySiteFitProposal={onApply} />)

  expect(container.querySelector('[data-artifact-kind="site-fit-proposal"]')).toHaveClass('md:col-span-2')
  fireEvent.click(screen.getByRole('button', { name: /apply proposal/i }))
  expect(onApply).toHaveBeenCalledWith(expect.objectContaining({ candidateId: 'baseline_preserved' }))
})
```

Add a second assertion for `kind: 'site-fit-apply'` with the same `md:col-span-2` layout.

- [ ] **Step 2: Run the artifact rendering test to verify RED**

Run:

```powershell
cd frontend; npm test -- ThreadMessageList.test.tsx --runInBand
```

Expected: FAIL because `site-fit-proposal` / `site-fit-apply` artifact kinds and props do not exist yet.

- [ ] **Step 3: Add site-fit contracts and cards**

Create `frontend/src/features/siteFit/contracts.ts`:

```ts
import type { CadReviewArtifactData } from '../cad/contracts'

export interface SiteFitBridgeProposalResult {
  pipeline: 'site_fit_bridge_mvp_v1'
  scope: 'seminole-2000-only'
  plan_id: string
  plan_name: string
  cad_analysis: { fit_summary?: { basis: string } | null }
  site_constraints: Record<string, unknown>
  proposal: {
    status: string
    candidates: Array<{
      candidate_id: string
      strategy: string
      summary: string
      fit_status: string
      change_count: number
    }>
    warnings: string[]
  }
  warnings: string[]
}

export interface SiteFitBridgeApplyResult {
  pipeline: 'site_fit_bridge_mvp_v1'
  scope: 'seminole-2000-only'
  plan_id: string
  plan_name: string
  apply: {
    candidate_id: string
    apply_status: string
    compliance_summary: { status: string }
    warnings: string[]
  }
  warnings: string[]
}

export interface SiteFitProposalArtifactData {
  planId: string
  planName: string
  candidateId: string | null
  siteConstraints: Record<string, unknown>
  summary: string
  fitStatus: string
  warnings: string[]
}

export interface SiteFitApplyArtifactData {
  planId: string
  planName: string
  candidateId: string
  applyStatus: string
  complianceStatus: string
  warnings: string[]
}
```

Create two cards:
- `SiteFitProposalArtifactCard.tsx` — show plan name, fit status, summary, warnings, and an `Apply proposal` button when `candidateId` exists.
- `SiteFitApplyArtifactCard.tsx` — show apply status, candidate id, compliance status, warnings.

- [ ] **Step 4: Extend chat artifact routing**

Modify `thread.types.ts`, `ArtifactCard.tsx`, and `ThreadMessageList.tsx` to support the new kinds.

Use these exact type additions in `thread.types.ts`:

```ts
import type { SiteFitApplyArtifactData, SiteFitProposalArtifactData } from '../siteFit/contracts'

export interface ThreadSiteFitProposalArtifact extends ThreadArtifactBase {
  kind: 'site-fit-proposal'
  proposal: SiteFitProposalArtifactData
}

export interface ThreadSiteFitApplyArtifact extends ThreadArtifactBase {
  kind: 'site-fit-apply'
  apply: SiteFitApplyArtifactData
}
```

Update the `ThreadArtifact` union to include both.

In `ThreadMessageList.tsx`, treat both new kinds like `cad-review`:

```tsx
const isFullWidthArtifact = artifact.kind === 'cad-review' || artifact.kind === 'site-fit-proposal' || artifact.kind === 'site-fit-apply'
```

- [ ] **Step 5: Run the artifact rendering test to verify GREEN**

Run:

```powershell
cd frontend; npm test -- ThreadMessageList.test.tsx --runInBand
```

Expected: PASS.

- [ ] **Step 6: Commit the artifact rendering slice**

```powershell
git add frontend/src/features/siteFit/contracts.ts frontend/src/features/chatThread/thread.types.ts frontend/src/features/chatThread/components/ArtifactCard.tsx frontend/src/features/chatThread/components/ThreadMessageList.tsx frontend/src/features/chatThread/components/SiteFitProposalArtifactCard.tsx frontend/src/features/chatThread/components/SiteFitApplyArtifactCard.tsx frontend/src/features/chatThread/components/ThreadMessageList.test.tsx
git commit -m "feat(chat): add site-fit artifact cards"
```

---

### Task 3: Chat agent propose/apply wiring

**Files:**
- Modify: `frontend/src/features/chatThread/chatAgent.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/features/chatThread/components/ArtifactCard.tsx`
- Test: `frontend/src/features/chatThread/chatAgent.test.ts`
- Test: `frontend/src/App.test.tsx`

- [ ] **Step 1: Write the failing chat wiring tests**

Extend `frontend/src/features/chatThread/chatAgent.test.ts` with:

```ts
it('routes CAD + Seminole prompts through the bridge propose endpoint', async () => {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve({
      pipeline: 'site_fit_bridge_mvp_v1',
      scope: 'seminole-2000-only',
      plan_id: 'seminole-2000',
      plan_name: 'SEMINOLE2000',
      cad_analysis: {
        analysis_id: 'cad-123',
        source_name: 'site.dxf',
        source_format: 'dxf',
        canonical_unit: 'inch',
        conversion_status: 'native_dxf',
        floor_plan: { role: 'floor_plan', bbox: null, summary: { entity_count: 0, line_count: 0, polyline_count: 0, text_count: 0 }, entities: [], rooms: [], measurements: null },
        site_plan: { role: 'site_plan', bbox: null, summary: { entity_count: 0, line_count: 0, polyline_count: 0, text_count: 0 }, entities: [], rooms: [], measurements: null },
        side_by_side: { canonical_unit: 'inch', gap: 0, floor_width: 0, site_width: 0, max_height: 0 },
        fit_summary: { comparison_unit: 'inch', basis: 'buildable_polygon', fits_within_buildable_polygon: true, fits_within_buildable_bbox: true },
        warnings: [],
      },
      site_constraints: { unit: 'inch' },
      proposal: {
        status: 'fit_ready',
        candidates: [{ candidate_id: 'baseline_preserved', strategy: 'preserve_existing_layout', summary: 'Keep the current plan unchanged.', fit_status: 'fit_ready', change_count: 0 }],
        warnings: [],
      },
      warnings: [],
    }),
  })

  const file = new File(['cad'], 'site.dxf', { type: 'application/dxf' })
  const result = await runChatAgentTool({ prompt: 'Fit Seminole 2000 on this site plan', attachment: file, planName: 'Fit Dawson' })

  expect(mockFetch).toHaveBeenCalledWith('/api/v2/site-fit/bridge/propose', expect.objectContaining({ method: 'POST', body: expect.any(FormData) }))
  expect(result.assistantMessage.artifacts).toEqual(expect.arrayContaining([
    expect.objectContaining({ kind: 'cad-review' }),
    expect.objectContaining({ kind: 'site-fit-proposal' }),
  ]))
})
```

Add an `apply` helper test around a new exported function:

```ts
const result = await runSiteFitApplyTool({
  planId: 'seminole-2000',
  planName: 'SEMINOLE2000',
  candidateId: 'baseline_preserved',
  siteConstraints: { unit: 'inch' },
})
expect(mockFetch).toHaveBeenCalledWith('/api/v2/site-fit/bridge/apply', expect.objectContaining({ method: 'POST' }))
expect(result.assistantMessage.artifacts).toEqual(expect.arrayContaining([
  expect.objectContaining({ kind: 'site-fit-apply' }),
]))
```

Extend `frontend/src/App.test.tsx` with a UI flow test:

```tsx
it('lets the user apply a Bridge MVP proposal from inside the chat', async () => {
  runChatAgentTool.mockResolvedValueOnce({
    assistantMessage: {
      id: 'assistant-1',
      role: 'assistant',
      content: 'Te dejo la propuesta de site-fit.',
      createdAtIso: '2026-04-24T00:00:00.000Z',
      artifacts: [{
        id: 'proposal-1',
        kind: 'site-fit-proposal',
        title: 'SEMINOLE2000 proposal',
        proposal: {
          planId: 'seminole-2000',
          planName: 'SEMINOLE2000',
          candidateId: 'baseline_preserved',
          siteConstraints: { unit: 'inch' },
          summary: 'Keep the current plan unchanged.',
          fitStatus: 'fit_ready',
          warnings: [],
        },
      }],
    },
  })
  runSiteFitApplyTool.mockResolvedValueOnce({
    assistantMessage: {
      id: 'assistant-2',
      role: 'assistant',
      content: 'Aplique la propuesta baseline.',
      createdAtIso: '2026-04-24T00:01:00.000Z',
      artifacts: [{
        id: 'apply-1',
        kind: 'site-fit-apply',
        title: 'Applied site-fit result',
        apply: {
          planId: 'seminole-2000',
          planName: 'SEMINOLE2000',
          candidateId: 'baseline_preserved',
          applyStatus: 'applied',
          complianceStatus: 'pass',
          warnings: [],
        },
      }],
    },
  })

  // open thread, submit prompt, click Apply proposal, assert applied message appears
})
```

- [ ] **Step 2: Run the chat wiring tests to verify RED**

Run:

```powershell
cd frontend; npm test -- chatAgent.test.ts App.test.tsx --runInBand
```

Expected: FAIL because the bridge route selection, apply helper, proposal artifact rendering, and `runSiteFitApplyTool` wiring do not exist yet.

- [ ] **Step 3: Implement bridge propose/apply chat helpers**

Update `chatAgent.ts` with:
- `wantsSeminoleSiteFit(prompt: string)` regex check (`/seminole|site-fit|fit .*seminole/i`)
- `runSiteFitBridgeTool(file, prompt)` using `/api/v2/site-fit/bridge/propose`
- `runSiteFitApplyTool({ planId, planName, candidateId, siteConstraints })` using `/api/v2/site-fit/bridge/apply`
- keep the existing fallback to plain CAD review when the prompt does not ask for Seminole/site-fit

The assistant message returned from bridge propose must include **both**:
1. a `cad-review` artifact built from `payload.cad_analysis`
2. a `site-fit-proposal` artifact built from `payload.proposal.candidates[0] ?? null`

- [ ] **Step 4: Wire the apply button in App and fix the catch bug**

In `App.tsx`:
- import `runSiteFitApplyTool`
- add `handleApplySiteFitProposal`
- pass `onApplySiteFitProposal` into `ThreadWorkspacePage` ? `ThreadMessageList` ? `ArtifactCard`
- append the assistant apply message to the same thread
- fix `appendThreadMessages(planId, ...)` to `appendThreadMessages(threadId, ...)`

Use this exact catch-path fix:

```tsx
appendThreadMessages(threadId, [{
  id: `assistant-${Math.random().toString(36).slice(2, 10)}`,
  role: 'assistant',
  content: error instanceof Error ? error.message : 'No pude ejecutar la herramienta del chat.',
  createdAtIso: new Date().toISOString(),
  artifacts: [],
}])
```

- [ ] **Step 5: Run the chat wiring tests to verify GREEN**

Run:

```powershell
cd frontend; npm test -- chatAgent.test.ts App.test.tsx --runInBand
```

Expected: PASS.

- [ ] **Step 6: Commit the chat wiring slice**

```powershell
git add frontend/src/features/chatThread/chatAgent.ts frontend/src/App.tsx frontend/src/features/chatThread/components/ArtifactCard.tsx frontend/src/features/chatThread/chatAgent.test.ts frontend/src/App.test.tsx
git commit -m "feat(chat): wire bridge mvp propose apply flow"
```

---

## Final verification

- [ ] **Step 1: Run the focused backend verification**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_site_fit_bridge_api.py tests/test_site_fit_api.py tests/test_cad_workspace_api.py -q
```

Expected: PASS.

- [ ] **Step 2: Run the focused frontend verification**

```powershell
cd frontend; npm test -- chatAgent.test.ts ThreadMessageList.test.tsx App.test.tsx --runInBand
```

Expected: PASS.

- [ ] **Step 3: Commit final integration if needed**

```powershell
git status --short
```

If there are integration-only fixes, commit them with:

```powershell
git add <exact-files>
git commit -m "feat(mvp): integrate bridge v1 chat lane"
```

## Self-review

- Spec coverage: the plan covers the fixed SEMINOLE2000 resolver, CAD extraction adapter, backend bridge orchestration, chat proposal/apply artifacts, and one honest apply lane.
- Placeholder scan: no `TODO` / `TBD` placeholders remain; every task names exact files, commands, and expected outputs.
- Type consistency: backend bridge models use `plan_id`, `plan_name`, `cad_analysis`, `site_constraints`, `proposal`, and `apply`; frontend TS contracts mirror those exact field names from the API and translate them into artifact data with `planId`, `planName`, `candidateId`, `siteConstraints`, `summary`, `fitStatus`, `applyStatus`, and `complianceStatus`.
