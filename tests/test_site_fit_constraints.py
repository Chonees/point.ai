from copy import deepcopy

from backend.site_fit.constraints import evaluate_hard_constraints
from backend.site_fit.intake import build_site_fit_job
from backend.site_fit.normalizer import normalize_plan


def _rich_plan(*, boundary_mutability="movable", opening_rehostable=True, room_min_width=60):
    return {
        "model": "Rich Overflow Sample",
        "unit": "inch",
        "rooms": [
            {
                "room_id": "room-1",
                "name": "LIVING",
                "category": "living_room",
                "mutability": "flexible",
                "min_width": room_min_width,
                "min_height": 40,
                "min_area": 2400,
                "bbox": {"x1": 0, "y1": 0, "x2": 120, "y2": 80, "width": 120, "height": 80},
            }
        ],
        "boundaries": [
            {
                "boundary_id": "west-boundary",
                "boundary_kind": "exterior",
                "owner_room_ids": ["room-1"],
                "mutability": "protected",
                "movable": False,
                "constraint_reasons": [],
                "start": {"x": 0, "y": 0},
                "end": {"x": 0, "y": 80},
                "length": 80,
                "opening_ids": [],
            },
            {
                "boundary_id": "east-boundary",
                "boundary_kind": "exterior",
                "owner_room_ids": ["room-1"],
                "mutability": boundary_mutability,
                "movable": boundary_mutability in {"movable", "movable_with_rehost"},
                "constraint_reasons": [],
                "start": {"x": 120, "y": 0},
                "end": {"x": 120, "y": 80},
                "length": 80,
                "opening_ids": ["opening-1"],
            },
        ],
        "walls": [
            {
                "wall_id": "wall-east",
                "boundary_kind": "exterior",
                "owner_room_ids": ["room-1"],
                "mutability": boundary_mutability,
                "movable": boundary_mutability in {"movable", "movable_with_rehost"},
                "start": {"x": 120, "y": 0},
                "end": {"x": 120, "y": 80},
                "length": 80,
                "hosted_opening_ids": ["opening-1"],
            }
        ],
        "openings": [
            {
                "opening_id": "opening-1",
                "opening_kind": "window",
                "host_wall_id": "wall-east",
                "owner_room_ids": ["room-1"],
                "confidence": "hosted",
                "rehost_required": True,
                "rehostable": opening_rehostable,
                "constraint_reasons": [],
                "offset": 20,
                "span": 20,
                "start": {"x": 120, "y": 20},
                "end": {"x": 120, "y": 40},
            }
        ],
        "footprint_bbox": {"x1": 0, "y1": 0, "x2": 120, "y2": 80, "width": 120, "height": 80},
    }


def _evaluate(*, boundary_mutability="movable", opening_rehostable=True, room_min_width=60, locked_rooms=None):
    job = build_site_fit_job(
        plan=_rich_plan(
            boundary_mutability=boundary_mutability,
            opening_rehostable=opening_rehostable,
            room_min_width=room_min_width,
        ),
        structure=None,
        site_constraints={"buildable_envelope": {"x": 0, "y": 0, "width": 100, "height": 80}},
        design_locks={"locked_rooms": locked_rooms or []},
        jurisdiction=None,
        ruleset_version="site_fit_contract_v1",
    )
    normalized = normalize_plan(job)
    return evaluate_hard_constraints(normalized, job)


def test_evaluate_hard_constraints_marks_single_side_overflow_boundary_as_eligible():
    evaluation = _evaluate(boundary_mutability="movable_with_rehost", opening_rehostable=True)

    assert evaluation.status == "buildable_conflict"
    assert len(evaluation.boundary_diagnostics) == 1
    assert evaluation.boundary_diagnostics[0].boundary_id == "east-boundary"
    assert evaluation.boundary_diagnostics[0].status == "eligible"
    assert evaluation.boundary_diagnostics[0].overflow_delta == 20.0
    assert evaluation.boundary_diagnostics[0].requires_rehost is True
    assert len(evaluation.mutation_hints) == 1
    assert evaluation.mutation_hints[0].boundary_id == "east-boundary"
    assert evaluation.mutation_hints[0].delta_x == -20.0
    assert evaluation.mutation_hints[0].delta_y == 0.0


def test_evaluate_hard_constraints_blocks_boundary_when_room_minimum_would_break():
    evaluation = _evaluate(boundary_mutability="movable", opening_rehostable=True, room_min_width=110)

    assert evaluation.status == "buildable_conflict"
    assert evaluation.boundary_diagnostics[0].status == "blocked_room_minimum"
    assert evaluation.room_diagnostics[0].status == "blocked_room_minimum"
    assert evaluation.mutation_hints == ()


def test_evaluate_hard_constraints_blocks_boundary_with_non_rehostable_opening():
    evaluation = _evaluate(boundary_mutability="movable_with_rehost", opening_rehostable=False)

    assert evaluation.status == "buildable_conflict"
    assert evaluation.boundary_diagnostics[0].status == "blocked_non_rehostable_opening"
    assert evaluation.boundary_diagnostics[0].requires_rehost is True
    assert evaluation.mutation_hints == ()


def test_evaluate_hard_constraints_marks_non_axis_aligned_boundary_as_blocked():
    plan = deepcopy(_rich_plan(boundary_mutability="movable"))
    east_boundary = plan["boundaries"][1]
    east_boundary["start"] = {"x": 120, "y": 0}
    east_boundary["end"] = {"x": 110, "y": 80}
    east_boundary["opening_ids"] = []
    plan["walls"][0]["hosted_opening_ids"] = []
    plan["openings"] = []

    job = build_site_fit_job(
        plan=plan,
        structure=None,
        site_constraints={"buildable_envelope": {"x": 0, "y": 0, "width": 100, "height": 80}},
        design_locks={},
        jurisdiction=None,
        ruleset_version="site_fit_contract_v1",
    )
    normalized = normalize_plan(job)
    evaluation = evaluate_hard_constraints(normalized, job)

    assert evaluation.status == "buildable_conflict"
    assert len(evaluation.boundary_diagnostics) == 1
    assert evaluation.boundary_diagnostics[0].boundary_id == "east-boundary"
    assert evaluation.boundary_diagnostics[0].status == "blocked_non_axis_aligned"
    assert evaluation.boundary_diagnostics[0].reason == "boundary is not axis-aligned"
    assert evaluation.mutation_hints == ()


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
