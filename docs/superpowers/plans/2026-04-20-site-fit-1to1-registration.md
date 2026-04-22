# Site-Fit 1:1 Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first real site-fit behavior: normalize floor-plan and site-plan placement into the same canonical unit, lock scale at 1:1, and report registration/scale mismatches before any intelligent adjustment.

**Architecture:** Keep the existing `backend/site_fit/` bounded context isolated and introduce a dedicated registration step inside it. The analyze/validate flow should first normalize plan units, compare the floor-plan footprint against a site-plan placement footprint, and only allow translation/rotation registration with `scale = 1.0`; any size mismatch becomes a first-class failure state.

**Tech Stack:** FastAPI, Pydantic, Python dataclasses, pytest.

---

## File Map

- Modify: `backend/site_fit/models.py`
- Create: `backend/site_fit/registration.py`
- Modify: `backend/site_fit/contracts.py`
- Modify: `backend/site_fit/normalizer.py`
- Modify: `backend/site_fit/constraints.py`
- Modify: `backend/site_fit/reporter.py`
- Modify: `backend/services/site_fit_service.py`
- Modify: `tests/test_site_fit_api.py`

### Task 1: Expose 1:1 registration in the API contract

**Files:**
- Modify: `tests/test_site_fit_api.py`
- Modify: `backend/site_fit/contracts.py`
- Modify: `backend/site_fit/reporter.py`

- [ ] **Step 1: Write the failing test**

```python
def test_site_fit_analyze_reports_1_to_1_registration_when_site_placement_matches_plan_size():
    response = client.post(
        "/api/v2/site-fit/analyze",
        json={
            "plan": SAMPLE_PLAN,
            "site_constraints": {
                "unit": "inch",
                "placed_plan_footprint": {"x": 30, "y": 40, "width": 200, "height": 80},
                "buildable_envelope": {"x": 0, "y": 0, "width": 260, "height": 160},
            },
        },
    )

    payload = response.json()
    assert payload["registration_summary"]["status"] == "registered_1to1"
    assert payload["registration_summary"]["canonical_unit"] == "inch"
    assert payload["registration_summary"]["transform"]["scale"] == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_site_fit_api.py::test_site_fit_analyze_reports_1_to_1_registration_when_site_placement_matches_plan_size -q`
Expected: FAIL because `registration_summary` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
class SiteFitRegistrationSummaryResponse(BaseModel):
    status: str
    canonical_unit: str
    scale_locked: bool = True
    transform: dict = Field(default_factory=dict)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_site_fit_api.py::test_site_fit_analyze_reports_1_to_1_registration_when_site_placement_matches_plan_size -q`
Expected: PASS

### Task 2: Fail fast when registration would require scaling

**Files:**
- Create: `backend/site_fit/registration.py`
- Modify: `backend/site_fit/models.py`
- Modify: `backend/site_fit/constraints.py`
- Modify: `tests/test_site_fit_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_site_fit_analyze_rejects_site_placement_that_requires_rescaling():
    response = client.post(
        "/api/v2/site-fit/analyze",
        json={
            "plan": SAMPLE_PLAN,
            "site_constraints": {
                "unit": "inch",
                "placed_plan_footprint": {"x": 30, "y": 40, "width": 210, "height": 80},
                "buildable_envelope": {"x": 0, "y": 0, "width": 260, "height": 160},
            },
        },
    )

    payload = response.json()
    assert payload["status"] == "registration_scale_mismatch"
    assert payload["compliance_summary"]["violations"][0]["rule_id"] == "registration.scale_locked_1to1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_site_fit_api.py::test_site_fit_analyze_rejects_site_placement_that_requires_rescaling -q`
Expected: FAIL because registration mismatch is not implemented yet.

- [ ] **Step 3: Write minimal implementation**

```python
def register_plan_placement(plan: NormalizedPlan, job: SiteFitJob) -> RegistrationResult:
    # compare normalized plan bbox vs placed_plan_footprint bbox in canonical unit
    # allow only translation/rotation=0, scale must remain exactly 1.0 within tolerance
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_site_fit_api.py::test_site_fit_analyze_rejects_site_placement_that_requires_rescaling -q`
Expected: PASS

### Task 3: Keep existing site-fit behavior green

**Files:**
- Modify: `backend/services/site_fit_service.py`
- Modify: `tests/test_site_fit_api.py`

- [ ] **Step 1: Write/update the regression expectations**

```python
def test_site_fit_apply_returns_original_plan_copy_for_baseline_candidate():
    ...
    assert payload["registration_summary"]["scale_locked"] is True
```

- [ ] **Step 2: Run the isolated + regression suites**

Run: `python -m pytest tests/test_site_fit_api.py tests/test_v2_api.py -q`
Expected: PASS
