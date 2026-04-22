# Site-Fit Scaffolding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar un bounded context `site_fit` dentro de Point.ai con contratos y endpoints aislados, sin acoplarlo al pipeline actual de parse/generate DXF.

**Architecture:** Mantener `backend/app.py` como controller fino y sumar un `backend/services/site_fit_service.py` que orqueste un paquete `backend/site_fit/` independiente. El nuevo flujo recibe contratos propios, normaliza un plan existente, evalúa constraints mínimas del site plan y responde con análisis/propuestas/aplicación/validación sin depender de `parse_service.py` ni `generate_dxf_service.py`.

**Tech Stack:** FastAPI, Pydantic, Python dataclasses, pytest.

---

## File Map

- Create: `backend/site_fit/__init__.py`
- Create: `backend/site_fit/contracts.py`
- Create: `backend/site_fit/models.py`
- Create: `backend/site_fit/intake.py`
- Create: `backend/site_fit/normalizer.py`
- Create: `backend/site_fit/constraints.py`
- Create: `backend/site_fit/mutators.py`
- Create: `backend/site_fit/solver.py`
- Create: `backend/site_fit/validator.py`
- Create: `backend/site_fit/scorer.py`
- Create: `backend/site_fit/reporter.py`
- Create: `backend/site_fit/exporters.py`
- Create: `backend/site_fit/README.md`
- Create: `backend/services/site_fit_service.py`
- Modify: `backend/app.py`
- Create: `tests/test_site_fit_api.py`

### Task 1: Definir el contrato aislado de site-fit en tests

**Files:**
- Create: `tests/test_site_fit_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_site_fit_analyze_endpoint_returns_isolated_contract():
    response = client.post(
        "/api/v2/site-fit/analyze",
        json={
            "plan": SAMPLE_PLAN,
            "site_constraints": {"buildable_envelope": {"x": 0, "y": 0, "width": 240, "height": 160}},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["isolation"]["pipeline"] == "site_fit"
    assert payload["isolation"]["touched_existing_parse_generate_pipeline"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_site_fit_api.py::test_site_fit_analyze_endpoint_returns_isolated_contract -q`
Expected: FAIL because the route and contract do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
@app.post("/api/v2/site-fit/analyze", response_model=SiteFitAnalysisResponse)
async def api_site_fit_analyze(req: SiteFitAnalyzeRequest):
    return analyze_site_fit(req)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_site_fit_api.py::test_site_fit_analyze_endpoint_returns_isolated_contract -q`
Expected: PASS

### Task 2: Implementar el bounded context y las propuestas baseline

**Files:**
- Create: `backend/site_fit/*`
- Create: `backend/services/site_fit_service.py`
- Modify: `backend/app.py`
- Modify: `tests/test_site_fit_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_site_fit_propose_returns_baseline_candidate_when_plan_fits():
    response = client.post(
        "/api/v2/site-fit/propose",
        json={
            "plan": SAMPLE_PLAN,
            "site_constraints": {"buildable_envelope": {"x": 0, "y": 0, "width": 240, "height": 160}},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["candidates"][0]["candidate_id"] == "baseline_preserved"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_site_fit_api.py::test_site_fit_propose_returns_baseline_candidate_when_plan_fits -q`
Expected: FAIL because proposal flow does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def propose_site_fit(req: SiteFitAnalyzeRequest) -> dict:
    analysis = analyze_site_fit(req)
    if analysis["status"] != "fit_ready":
        return {..., "candidates": []}
    return {..., "candidates": [{"candidate_id": "baseline_preserved", "change_count": 0}]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_site_fit_api.py::test_site_fit_propose_returns_baseline_candidate_when_plan_fits -q`
Expected: PASS

### Task 3: Agregar apply/validate y demostrar aislamiento del pipeline existente

**Files:**
- Modify: `backend/app.py`
- Modify: `backend/services/site_fit_service.py`
- Create: `backend/site_fit/exporters.py`
- Modify: `tests/test_site_fit_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_site_fit_apply_returns_original_plan_copy_for_baseline_candidate():
    response = client.post(
        "/api/v2/site-fit/apply",
        json={
            "plan": SAMPLE_PLAN,
            "site_constraints": {"buildable_envelope": {"x": 0, "y": 0, "width": 240, "height": 160}},
            "candidate_id": "baseline_preserved",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["apply_status"] == "applied"
    assert payload["change_set"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_site_fit_api.py::test_site_fit_apply_returns_original_plan_copy_for_baseline_candidate -q`
Expected: FAIL because apply flow/exporter do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def apply_site_fit(req: SiteFitApplyRequest) -> dict:
    proposal = propose_site_fit(req)
    return {
        "candidate_id": req.candidate_id,
        "apply_status": "applied",
        "applied_plan": export_applied_plan(req),
        "change_set": [],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_site_fit_api.py -q`
Expected: PASS
