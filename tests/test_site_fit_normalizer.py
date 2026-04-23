from __future__ import annotations

import json
from pathlib import Path

from backend.site_fit.intake import build_site_fit_job
from backend.site_fit.normalizer import normalize_plan

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "frontend"
    / "src"
    / "features"
    / "catalogInspector"
    / "catalogInspector.fixture.json"
)


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _load_catalog_payload() -> dict:
    fixture = _load_fixture()
    return {
        "model": fixture["name"],
        "unit": fixture["canonical_unit"],
        "rooms": fixture["rooms"],
        "walls": fixture["walls"],
        "openings": fixture["openings"],
        "boundaries": fixture["boundaries"],
        "boundary_nodes": fixture["boundary_nodes"],
        "footprint_bbox": fixture["footprint_bbox"],
        "structure_meta": {"unit": fixture["canonical_unit"]},
    }


def _build_catalog_job():
    return build_site_fit_job(
        plan=_load_catalog_payload(),
        structure=None,
        site_constraints={"buildable_envelope": {"x": 0, "y": 0, "width": 5000, "height": 5000}},
        design_locks={},
        jurisdiction=None,
        ruleset_version="site_fit_contract_v1",
    )


def test_normalize_plan_exports_rich_catalog_assembly_without_raw_traces():
    fixture = _load_fixture()
    normalized = normalize_plan(_build_catalog_job())

    assert normalized.source_kind == "plan"
    assert normalized.room_count == len(fixture["rooms"])
    assert normalized.wall_count == len(fixture["walls"])
    assert normalized.opening_count == len(fixture["openings"])
    assert normalized.footprint_bbox == fixture["footprint_bbox"]


def test_normalize_plan_preserves_mutability_and_rehostability_in_rich_payload():
    fixture = _load_fixture()
    normalized = normalize_plan(_build_catalog_job())
    payload = normalized.payload

    flexible_room_ids = {
        room["room_id"]
        for room in payload["rooms"]
        if room["mutability"] == "flexible"
    }
    movable_boundary_ids = {
        boundary["boundary_id"]
        for boundary in payload["boundaries"]
        if boundary["mutability"] == "movable"
    }
    rehost_required_opening_ids = {
        opening["opening_id"]
        for opening in payload["openings"]
        if opening["rehost_required"] is True
    }

    assert flexible_room_ids == {
        room["room_id"]
        for room in fixture["rooms"]
        if room["mutability"] == "flexible"
    }
    assert {"boundary-4aad10008caa", "boundary-e6868d68bf3e"} <= movable_boundary_ids
    assert len(movable_boundary_ids) == 39
    assert {"opening-door-3b02e44a8af3", "opening-window-9a93c7f54172"} <= rehost_required_opening_ids
    assert len(rehost_required_opening_ids) == 12
