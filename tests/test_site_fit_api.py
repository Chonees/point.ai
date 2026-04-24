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

RICH_OVERFLOW_PLAN = {
    "model": "Rich Overflow Sample",
    "unit": "inch",
    "rooms": [
        {
            "room_id": "room-1",
            "name": "LIVING",
            "category": "living_room",
            "mutability": "flexible",
            "min_width": 60,
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
            "mutability": "movable_with_rehost",
            "movable": True,
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
            "mutability": "movable_with_rehost",
            "movable": True,
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
            "rehostable": True,
            "constraint_reasons": [],
            "offset": 20,
            "span": 20,
            "start": {"x": 120, "y": 20},
            "end": {"x": 120, "y": 40},
        }
    ],
    "footprint_bbox": {"x1": 0, "y1": 0, "x2": 120, "y2": 80, "width": 120, "height": 80},
}

RICH_OVERFLOW_SITE = {
    "buildable_envelope": {"x": 0, "y": 0, "width": 100, "height": 80},
}

REGISTERED_TRANSLATED_RICH_OVERFLOW_SITE = {
    "unit": "inch",
    "placed_plan_footprint": {"x": 30, "y": 0, "width": 120, "height": 80},
    "buildable_envelope": {"x": 0, "y": 0, "width": 130, "height": 80},
}

RICH_OVERFLOW_PLAN_FEET = {
    "model": "Rich Overflow Feet Sample",
    "unit": "ft",
    "rooms": [
        {
            "room_id": "room-1",
            "name": "LIVING",
            "category": "living_room",
            "mutability": "flexible",
            "min_width": 5,
            "min_height": 4,
            "min_area": 40,
            "bbox": {"x1": 0, "y1": 0, "x2": 10, "y2": 8, "width": 10, "height": 8},
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
            "end": {"x": 0, "y": 8},
            "length": 8,
            "opening_ids": [],
        },
        {
            "boundary_id": "east-boundary",
            "boundary_kind": "exterior",
            "owner_room_ids": ["room-1"],
            "mutability": "movable",
            "movable": True,
            "constraint_reasons": [],
            "start": {"x": 10, "y": 0},
            "end": {"x": 10, "y": 8},
            "length": 8,
            "opening_ids": [],
        },
    ],
    "walls": [
        {
            "wall_id": "wall-east",
            "boundary_kind": "exterior",
            "owner_room_ids": ["room-1"],
            "mutability": "movable",
            "movable": True,
            "start": {"x": 10, "y": 0},
            "end": {"x": 10, "y": 8},
            "length": 8,
            "hosted_opening_ids": [],
        }
    ],
    "openings": [],
    "footprint_bbox": {"x1": 0, "y1": 0, "x2": 10, "y2": 8, "width": 10, "height": 8},
}

RICH_OVERFLOW_SITE_INCH = {
    "unit": "inch",
    "buildable_envelope": {"x": 0, "y": 0, "width": 108, "height": 96},
}


def test_site_fit_propose_returns_shrink_candidate_for_single_side_rich_overflow():
    response = client.post(
        "/api/v2/site-fit/propose",
        json={
            "plan": RICH_OVERFLOW_PLAN,
            "site_constraints": RICH_OVERFLOW_SITE,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "buildable_conflict"
    assert payload["compliance_summary"]["mutation_hints"][0]["boundary_id"] == "east-boundary"
    assert payload["candidates"][0]["candidate_id"] == "shrink_boundary::east-boundary"
    assert payload["candidates"][0]["change_count"] == 1
    assert payload["candidates"][0]["changes"][0]["delta_x"] == -20.0


def test_site_fit_apply_applies_shrink_boundary_candidate_to_rich_plan_payload():
    response = client.post(
        "/api/v2/site-fit/apply",
        json={
            "plan": RICH_OVERFLOW_PLAN,
            "site_constraints": RICH_OVERFLOW_SITE,
            "candidate_id": "shrink_boundary::east-boundary",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    applied_plan = payload["applied_plan"]["plan"]
    assert payload["candidate_id"] == "shrink_boundary::east-boundary"
    assert payload["change_set"][0]["boundary_id"] == "east-boundary"
    assert applied_plan["footprint_bbox"]["x2"] == 100.0
    assert applied_plan["boundaries"][1]["start"]["x"] == 100.0
    assert applied_plan["boundaries"][1]["end"]["x"] == 100.0
    assert applied_plan["walls"][0]["start"]["x"] == 100.0
    assert applied_plan["openings"][0]["start"]["x"] == 100.0
    assert applied_plan["rooms"][0]["bbox"]["x2"] == 100.0


def test_site_fit_propose_keeps_mutation_hints_for_registered_1_to_1_translation_overflow():
    response = client.post(
        "/api/v2/site-fit/propose",
        json={
            "plan": RICH_OVERFLOW_PLAN,
            "site_constraints": REGISTERED_TRANSLATED_RICH_OVERFLOW_SITE,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "buildable_conflict"
    assert payload["registration_summary"]["status"] == "registered_1to1"
    assert payload["compliance_summary"]["mutation_hints"][0]["boundary_id"] == "east-boundary"
    assert payload["compliance_summary"]["mutation_hints"][0]["delta_x"] == -20.0
    assert payload["candidates"][0]["candidate_id"] == "shrink_boundary::east-boundary"


def test_site_fit_apply_revalidates_mutated_payload_before_returning_truth():
    response = client.post(
        "/api/v2/site-fit/apply",
        json={
            "plan": RICH_OVERFLOW_PLAN,
            "site_constraints": RICH_OVERFLOW_SITE,
            "candidate_id": "shrink_boundary::east-boundary",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["apply_status"] == "applied"
    assert payload["compliance_summary"]["status"] == "pass"
    assert payload["compliance_summary"]["violations"] == []
    assert payload["compliance_summary"]["mutation_hints"] == []


def test_site_fit_apply_converts_canonical_delta_back_to_raw_plan_units():
    response = client.post(
        "/api/v2/site-fit/apply",
        json={
            "plan": RICH_OVERFLOW_PLAN_FEET,
            "site_constraints": RICH_OVERFLOW_SITE_INCH,
            "candidate_id": "shrink_boundary::east-boundary",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    applied_plan = payload["applied_plan"]["plan"]
    assert payload["change_set"][0]["delta_x"] == -12.0
    assert applied_plan["footprint_bbox"]["x2"] == 9.0
    assert applied_plan["boundaries"][1]["start"]["x"] == 9.0
    assert applied_plan["boundaries"][1]["end"]["x"] == 9.0
    assert applied_plan["walls"][0]["start"]["x"] == 9.0
    assert applied_plan["rooms"][0]["bbox"]["x2"] == 9.0


def test_site_fit_apply_keeps_room_derived_geometry_consistent_after_shrink():
    rich_plan_with_derived_geometry = deepcopy(RICH_OVERFLOW_PLAN)
    rich_plan_with_derived_geometry["rooms"][0]["width"] = 120
    rich_plan_with_derived_geometry["rooms"][0]["height"] = 80
    rich_plan_with_derived_geometry["rooms"][0]["area"] = 9600
    rich_plan_with_derived_geometry["rooms"][0]["centroid"] = {"x": 60, "y": 40}

    response = client.post(
        "/api/v2/site-fit/apply",
        json={
            "plan": rich_plan_with_derived_geometry,
            "site_constraints": RICH_OVERFLOW_SITE,
            "candidate_id": "shrink_boundary::east-boundary",
        },
    )

    assert response.status_code == 200, response.text
    room = response.json()["applied_plan"]["plan"]["rooms"][0]
    assert room["bbox"]["width"] == 100.0
    assert room["width"] == 100.0
    assert room["height"] == 80.0
    assert room["area"] == 8000.0
    assert room["centroid"] == {"x": 50.0, "y": 40.0}


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
