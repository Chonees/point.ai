from __future__ import annotations

import json
from pathlib import Path

from backend.site_fit.intake import build_site_fit_job
from backend.site_fit.normalizer import normalize_plan

FIXTURE_PATH = Path("frontend/src/features/catalogInspector/catalogInspector.fixture.json")


def _load_catalog_payload() -> dict:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
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
    normalized = normalize_plan(_build_catalog_job())

    assert normalized.source_kind == "plan"
    assert normalized.room_count == len(normalized.room_summaries)
    assert normalized.wall_count == len(normalized.wall_segments)
    assert normalized.opening_count == len(normalized.openings)
    assert normalized.boundary_segments
    assert normalized.wall_segments
    assert normalized.openings
    assert "cad_traces" not in normalized.payload


def test_normalize_plan_preserves_mutability_and_rehostability_in_rich_payload():
    normalized = normalize_plan(_build_catalog_job())

    assert any(room.mutability == "flexible" for room in normalized.room_summaries)
    assert any(boundary.mutability == "movable" for boundary in normalized.boundary_segments)
    assert any(opening.rehost_required is True for opening in normalized.openings)
    assert normalized.movable_boundary_count > 0
    assert normalized.rehostable_opening_count > 0
