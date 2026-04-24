# Site Fit Buildable Polygon Honesty Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `site_fit` from treating `buildable_polygon` as a loose bbox and make polygon fit truthful at the current footprint-rectangle level.

**Architecture:** Keep the current `NormalizedPlan` contract and implement polygon fit inside `backend/site_fit/constraints.py` by testing the normalized footprint rectangle against the normalized polygon. If both `buildable_envelope` and `buildable_polygon` are present, both must pass. Polygon conflicts remain analysis-only in this slice: no mutation hints are emitted from polygon failures.

**Tech Stack:** Python, FastAPI, dataclasses, pytest

---

## File map

- Modify: `tests/test_site_fit_constraints.py` — add RED unit coverage for polygon-only conflict and polygon+envelope AND semantics.
- Modify: `tests/test_site_fit_api.py` — add API regression coverage for truthful polygon fit.
- Modify: `backend/site_fit/constraints.py` — add real polygon containment helpers and polygon rule evaluation.

### Task 1: Add RED tests for polygon honesty

**Files:**
- Modify: `tests/test_site_fit_constraints.py`
- Modify: `tests/test_site_fit_api.py`
- Read: `backend/site_fit/constraints.py`

- [ ] **Step 1: Add failing unit tests for polygon-only conflict and polygon pass**

Append these tests to `tests/test_site_fit_constraints.py`:

```python
def test_evaluate_hard_constraints_rejects_footprint_that_spills_outside_buildable_polygon():
    plan = _rich_plan(boundary_mutability="movable", opening_rehostable=True, room_min_width=60)
    plan["footprint_bbox"] = {"x1": 0, "y1": 0, "x2": 120, "y2": 80, "width": 120, "height": 80}
    job = build_site_fit_job(
        plan=plan,
        structure=None,
        site_constraints={
            "buildable_polygon": [
                {"x": 0, "y": 0},
                {"x": 100, "y": 0},
                {"x": 100, "y": 30},
                {"x": 30, "y": 30},
                {"x": 30, "y": 80},
                {"x": 0, "y": 80},
            ]
        },
        design_locks={},
        jurisdiction=None,
        ruleset_version="site_fit_contract_v1",
    )
    normalized = normalize_plan(job)

    evaluation = evaluate_hard_constraints(normalized, job)

    assert evaluation.status == "buildable_conflict"
    assert evaluation.violations[0]["rule_id"] == "buildable_polygon.contains_plan_footprint"
    assert evaluation.mutation_hints == ()


def test_evaluate_hard_constraints_accepts_footprint_inside_buildable_polygon():
    plan = _rich_plan(boundary_mutability="movable", opening_rehostable=True, room_min_width=60)
    plan["footprint_bbox"] = {"x1": 10, "y1": 10, "x2": 90, "y2": 70, "width": 80, "height": 60}
    job = build_site_fit_job(
        plan=plan,
        structure=None,
        site_constraints={
            "buildable_polygon": [
                {"x": 0, "y": 0},
                {"x": 100, "y": 0},
                {"x": 100, "y": 80},
                {"x": 0, "y": 80},
            ]
        },
        design_locks={},
        jurisdiction=None,
        ruleset_version="site_fit_contract_v1",
    )
    normalized = normalize_plan(job)

    evaluation = evaluate_hard_constraints(normalized, job)

    assert evaluation.status == "fit_ready"
    assert evaluation.checked_rule_ids == ("buildable_polygon.contains_plan_footprint",)
```

- [ ] **Step 2: Add failing API tests for polygon-only truthfulness and AND semantics**

Append these tests to `tests/test_site_fit_api.py`:

```python
def test_site_fit_analyze_reports_polygon_conflict_when_bbox_would_have_passed():
    response = client.post(
        "/api/v2/site-fit/analyze",
        json={
            "plan": RICH_OVERFLOW_PLAN,
            "site_constraints": {
                "buildable_polygon": [
                    {"x": 0, "y": 0},
                    {"x": 100, "y": 0},
                    {"x": 100, "y": 30},
                    {"x": 30, "y": 30},
                    {"x": 30, "y": 80},
                    {"x": 0, "y": 80},
                ]
            },
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "buildable_conflict"
    assert payload["compliance_summary"]["violations"][0]["rule_id"] == "buildable_polygon.contains_plan_footprint"


def test_site_fit_analyze_requires_polygon_and_envelope_when_both_are_present():
    response = client.post(
        "/api/v2/site-fit/analyze",
        json={
            "plan": RICH_OVERFLOW_PLAN,
            "site_constraints": {
                "buildable_envelope": {"x": 0, "y": 0, "width": 130, "height": 90},
                "buildable_polygon": [
                    {"x": 0, "y": 0},
                    {"x": 100, "y": 0},
                    {"x": 100, "y": 30},
                    {"x": 30, "y": 30},
                    {"x": 30, "y": 80},
                    {"x": 0, "y": 80},
                ],
            },
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "buildable_conflict"
    assert "buildable_polygon.contains_plan_footprint" in payload["compliance_summary"]["checked_rule_ids"]
```

- [ ] **Step 3: Run RED commands**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_site_fit_constraints.py -q -k polygon
..\..\.venv\Scripts\python.exe -m pytest tests/test_site_fit_api.py -q -k polygon
```

Expected: FAIL because polygon fit is still reduced to bbox behavior.

### Task 2: Implement real polygon containment for the normalized footprint rectangle

**Files:**
- Modify: `backend/site_fit/constraints.py`
- Test: `tests/test_site_fit_constraints.py`
- Test: `tests/test_site_fit_api.py`

- [ ] **Step 1: Add polygon normalization and geometry helpers**

Add helpers in `backend/site_fit/constraints.py` for:

```python
BUILDABLE_POLYGON_RULE_ID = "buildable_polygon.contains_plan_footprint"
```

and:

```python
def _resolve_buildable_polygon(site_constraints: dict, *, source_unit: str, to_unit: str) -> list[dict[str, float]]:
    polygon = site_constraints.get("buildable_polygon") or []
    return normalize_polygon(polygon, from_unit=source_unit, to_unit=to_unit)


def _footprint_corners(bbox: dict[str, float]) -> list[dict[str, float]]:
    return [
        {"x": bbox["x1"], "y": bbox["y1"]},
        {"x": bbox["x2"], "y": bbox["y1"]},
        {"x": bbox["x2"], "y": bbox["y2"]},
        {"x": bbox["x1"], "y": bbox["y2"]},
    ]
```

plus small helpers for point-in-polygon, point-on-segment, and segment intersection.

- [ ] **Step 2: Evaluate polygon fit truthfully**

In `evaluate_hard_constraints(...)`:

- resolve normalized `buildable_polygon`
- if polygon exists, test the footprint rectangle by:
  - all 4 corners inside/on polygon
  - no rectangle edge intersects a polygon edge
- if polygon-only constraints are present, return `fit_ready` or `buildable_conflict` from the polygon result
- if both envelope and polygon are present, require both checks to pass
- if polygon fails, emit:

```python
{
    "rule_id": BUILDABLE_POLYGON_RULE_ID,
    "message": "The normalized plan footprint exceeds the buildable polygon.",
    "plan_bbox": plan_bbox_for_fit,
    "buildable_polygon": buildable_polygon,
}
```

and do not emit mutation hints for that polygon conflict path.

- [ ] **Step 3: Run GREEN verification**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_site_fit_constraints.py -q -k polygon
..\..\.venv\Scripts\python.exe -m pytest tests/test_site_fit_api.py -q -k polygon
..\..\.venv\Scripts\python.exe -m pytest tests/test_site_fit_constraints.py tests/test_site_fit_normalizer.py tests/test_site_fit_api.py -q
```

Expected: PASS.

## Self-review

- Spec coverage: the plan covers truthful polygon-only evaluation plus AND semantics when envelope and polygon coexist.
- Placeholder scan: no TODO/TBD placeholders remain.
- Type consistency: `buildable_polygon.contains_plan_footprint` is used consistently in tests and implementation.
