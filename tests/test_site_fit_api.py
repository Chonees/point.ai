from copy import deepcopy

from fastapi.testclient import TestClient

from backend.app import app


SAMPLE_PLAN = {
    "model": "Site Fit Sample",
    "rooms": [
        {"name": "LIVING", "x": 0, "y": 0, "w": 120, "h": 80},
        {"name": "BED 1", "x": 120, "y": 0, "w": 80, "h": 80},
    ],
}

FITTING_SITE_CONSTRAINTS = {
    "buildable_envelope": {"x": -10, "y": -10, "width": 260, "height": 160},
    "setbacks": {"front": 25, "rear": 20, "left": 10, "right": 10},
}

REGISTERED_SITE_CONSTRAINTS = {
    "unit": "inch",
    "placed_plan_footprint": {"x": 30, "y": 40, "width": 200, "height": 80},
    "buildable_envelope": {"x": 0, "y": 0, "width": 260, "height": 160},
}

MISMATCHED_REGISTERED_SITE_CONSTRAINTS = {
    "unit": "inch",
    "placed_plan_footprint": {"x": 30, "y": 40, "width": 210, "height": 80},
    "buildable_envelope": {"x": 0, "y": 0, "width": 260, "height": 160},
}

TIGHT_SITE_CONSTRAINTS = {
    "buildable_envelope": {"x": 0, "y": 0, "width": 100, "height": 60},
}

DAWSON_PLAN_FEET = {
    "model": "Dawson Manual Reference",
    "unit": "ft",
    "rooms": [
        {"name": "GARAGE", "x": 0, "y": 0, "w": 22, "h": 22},
        {"name": "LIVING", "x": 22, "y": 0, "w": 24, "h": 28},
        {"name": "KITCHEN", "x": 46, "y": 0, "w": 16, "h": 18},
        {"name": "BED 2", "x": 46, "y": 18, "w": 16, "h": 10},
    ],
}

DAWSON_SITE_CONSTRAINTS_INCH = {
    "unit": "inch",
    "placed_plan_footprint": {"x": 360, "y": 240, "width": 744, "height": 336},
    "buildable_envelope": {"x": 300, "y": 180, "width": 900, "height": 520},
}

DAWSON_STRUCTURE_FEET = {
    "model": "Dawson Manual Structure",
    "walls": [
        {"x1": 0, "y1": 0, "x2": 62, "y2": 0},
        {"x1": 62, "y1": 0, "x2": 62, "y2": 28},
        {"x1": 62, "y1": 28, "x2": 0, "y2": 28},
        {"x1": 0, "y1": 28, "x2": 0, "y2": 0},
    ],
    "openings": [],
    "structure_meta": {"unit": "ft"},
}


client = TestClient(app)


def test_site_fit_analyze_endpoint_returns_isolated_contract():
    response = client.post(
        "/api/v2/site-fit/analyze",
        json={
            "plan": SAMPLE_PLAN,
            "site_constraints": FITTING_SITE_CONSTRAINTS,
            "design_locks": {"locked_rooms": ["BED 1"]},
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "fit_ready"
    assert payload["isolation"]["pipeline"] == "site_fit"
    assert payload["isolation"]["separate_contracts"] is True
    assert payload["isolation"]["touched_existing_parse_generate_pipeline"] is False
    assert payload["plan_summary"]["source_kind"] == "plan"
    assert payload["plan_summary"]["room_count"] == 2
    assert payload["registration_summary"]["status"] == "plan_bbox_only"
    assert payload["registration_summary"]["scale_locked"] is True
    assert payload["compliance_summary"]["status"] == "pass"
    assert payload["compliance_summary"]["checked_rule_ids"] == ["buildable_envelope.bbox_contains_plan_bbox"]


def test_site_fit_analyze_reports_1_to_1_registration_when_site_placement_matches_plan_size():
    response = client.post(
        "/api/v2/site-fit/analyze",
        json={
            "plan": SAMPLE_PLAN,
            "site_constraints": REGISTERED_SITE_CONSTRAINTS,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "fit_ready"
    assert payload["registration_summary"]["status"] == "registered_1to1"
    assert payload["registration_summary"]["canonical_unit"] == "inch"
    assert payload["registration_summary"]["scale_locked"] is True
    assert payload["registration_summary"]["transform"]["scale"] == 1.0
    assert payload["registration_summary"]["transform"]["rotation_degrees"] == 0.0
    assert payload["registration_summary"]["transform"]["translate_x"] == 30.0
    assert payload["registration_summary"]["transform"]["translate_y"] == 40.0


def test_site_fit_analyze_rejects_site_placement_that_requires_rescaling():
    response = client.post(
        "/api/v2/site-fit/analyze",
        json={
            "plan": SAMPLE_PLAN,
            "site_constraints": MISMATCHED_REGISTERED_SITE_CONSTRAINTS,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "registration_scale_mismatch"
    assert payload["registration_summary"]["status"] == "scale_mismatch"
    assert payload["compliance_summary"]["status"] == "fail"
    assert payload["compliance_summary"]["violations"][0]["rule_id"] == "registration.scale_locked_1to1"


def test_site_fit_analyze_normalizes_mixed_cad_units_before_registration():
    response = client.post(
        "/api/v2/site-fit/analyze",
        json={
            "plan": DAWSON_PLAN_FEET,
            "site_constraints": DAWSON_SITE_CONSTRAINTS_INCH,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "fit_ready"
    assert payload["plan_summary"]["canonical_unit"] == "inch"
    assert payload["registration_summary"]["status"] == "registered_1to1"
    assert payload["registration_summary"]["canonical_unit"] == "inch"
    assert payload["registration_summary"]["transform"]["scale"] == 1.0
    assert payload["registration_summary"]["transform"]["translate_x"] == 360.0
    assert payload["registration_summary"]["transform"]["translate_y"] == 240.0


def test_site_fit_analyze_exposes_mutable_assembly_counts_for_catalog_payload():
    catalog_payload = {
        "model": "Catalog Sample",
        "unit": "inch",
        "rooms": [
            {
                "room_id": "room-living",
                "name": "LIVING ROOM",
                "category": "living_room",
                "bbox": {"x1": 0, "y1": 0, "x2": 120, "y2": 80, "width": 120, "height": 80},
                "centroid": {"x": 60, "y": 40},
                "width": 120,
                "height": 80,
                "area": 9600,
                "measurement_source": "catalog",
                "mutability": "flexible",
                "min_width": 84,
                "min_height": 84,
                "min_area": 10080,
                "constraint_reasons": [],
            }
        ],
        "boundaries": [
            {
                "boundary_id": "boundary-1",
                "boundary_kind": "exterior",
                "owner_room_ids": ["room-living"],
                "mutability": "movable",
                "movable": True,
                "constraint_reasons": [],
                "start": {"x": 0, "y": 0},
                "end": {"x": 120, "y": 0},
                "length": 120,
                "opening_ids": ["opening-1"],
            }
        ],
        "boundary_nodes": [
            {
                "node_id": "boundary-node-1",
                "boundary_id": "boundary-1",
                "point": {"x": 0, "y": 0},
            }
        ],
        "walls": [
            {
                "wall_id": "wall-1",
                "boundary_kind": "exterior",
                "owner_room_ids": ["room-living"],
                "mutability": "movable_with_rehost",
                "movable": True,
                "start": {"x": 0, "y": 0},
                "end": {"x": 120, "y": 0},
                "length": 120,
                "hosted_opening_ids": ["opening-1"],
            }
        ],
        "openings": [
            {
                "opening_id": "opening-1",
                "opening_kind": "window",
                "host_wall_id": "wall-1",
                "owner_room_ids": ["room-living"],
                "confidence": "hosted",
                "rehost_required": True,
                "rehostable": True,
                "constraint_reasons": ["opening_on_movable_wall"],
                "offset": 24,
                "span": 36,
                "start": {"x": 24, "y": 0},
                "end": {"x": 60, "y": 0},
            }
        ],
        "footprint_bbox": {"x1": 0, "y1": 0, "x2": 120, "y2": 80, "width": 120, "height": 80},
    }

    response = client.post(
        "/api/v2/site-fit/analyze",
        json={
            "plan": catalog_payload,
            "site_constraints": {"buildable_envelope": {"x": -10, "y": -10, "width": 260, "height": 160}},
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["plan_summary"]["movable_boundary_count"] == 1
    assert payload["plan_summary"]["protected_boundary_count"] == 0
    assert payload["plan_summary"]["locked_boundary_count"] == 0
    assert payload["plan_summary"]["rehostable_opening_count"] == 1


def test_site_fit_analyze_reads_structure_meta_unit_for_structure_payload():
    response = client.post(
        "/api/v2/site-fit/analyze",
        json={
            "structure": DAWSON_STRUCTURE_FEET,
            "site_constraints": DAWSON_SITE_CONSTRAINTS_INCH,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "fit_ready"
    assert payload["plan_summary"]["source_kind"] == "structure"
    assert payload["plan_summary"]["canonical_unit"] == "inch"
    assert payload["registration_summary"]["status"] == "registered_1to1"
    assert payload["registration_summary"]["registered_plan_bbox"]["width"] == 744.0


def test_site_fit_propose_returns_baseline_candidate_when_plan_fits():
    response = client.post(
        "/api/v2/site-fit/propose",
        json={
            "plan": SAMPLE_PLAN,
            "site_constraints": FITTING_SITE_CONSTRAINTS,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "fit_ready"
    assert len(payload["candidates"]) == 1
    candidate = payload["candidates"][0]
    assert candidate["candidate_id"] == "baseline_preserved"
    assert candidate["change_count"] == 0
    assert candidate["fit_status"] == "fit_ready"


def test_site_fit_apply_returns_original_plan_copy_for_baseline_candidate():
    original_plan = deepcopy(SAMPLE_PLAN)

    response = client.post(
        "/api/v2/site-fit/apply",
        json={
            "plan": original_plan,
            "site_constraints": FITTING_SITE_CONSTRAINTS,
            "candidate_id": "baseline_preserved",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["apply_status"] == "applied"
    assert payload["candidate_id"] == "baseline_preserved"
    assert payload["change_set"] == []
    assert payload["applied_plan"]["plan"] == SAMPLE_PLAN
    assert payload["applied_plan"]["site_fit_meta"]["pipeline"] == "site_fit"
    assert payload["registration_summary"]["scale_locked"] is True
    assert original_plan == SAMPLE_PLAN


def test_site_fit_validate_reports_conflict_when_plan_exceeds_buildable_envelope():
    response = client.post(
        "/api/v2/site-fit/validate",
        json={
            "plan": SAMPLE_PLAN,
            "site_constraints": TIGHT_SITE_CONSTRAINTS,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "buildable_conflict"
    assert payload["compliance_summary"]["status"] == "fail"
    assert payload["compliance_summary"]["violations"][0]["rule_id"] == "buildable_envelope.bbox_contains_plan_bbox"


def test_site_fit_analyze_requires_exactly_one_plan_input():
    response = client.post(
        "/api/v2/site-fit/analyze",
        json={
            "plan": SAMPLE_PLAN,
            "structure": {"walls": []},
            "site_constraints": FITTING_SITE_CONSTRAINTS,
        },
    )

    assert response.status_code == 422, response.text
    assert "Exactly one of plan or structure must be provided" in response.json()["detail"]
