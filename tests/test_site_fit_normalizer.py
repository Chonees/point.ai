from __future__ import annotations

from dataclasses import asdict
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
        "cad_traces": fixture["cad_traces"],
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


def _asdict_items(items) -> list[dict]:
    return [asdict(item) for item in items]


def _expected_room_summaries(fixture: dict) -> list[dict]:
    boundary_ids_by_room: dict[str, list[str]] = {}
    for boundary in fixture["boundaries"]:
        if boundary.get("boundary_kind") in {"duplicate", "artifact"}:
            continue
        for room_id in boundary.get("owner_room_ids") or []:
            boundary_ids_by_room.setdefault(room_id, []).append(boundary["boundary_id"])

    return [
        {
            "room_id": room["room_id"],
            "name": room["name"],
            "category": room["category"],
            "mutability": room["mutability"],
            "min_width": room["min_width"],
            "min_height": room["min_height"],
            "min_area": room["min_area"],
            "bbox": room["bbox"],
            "owner_boundary_ids": tuple(boundary_ids_by_room.get(room["room_id"], [])),
        }
        for room in fixture["rooms"]
    ]


def _expected_boundary_segments(fixture: dict) -> list[dict]:
    return [
        {
            "boundary_id": boundary["boundary_id"],
            "boundary_kind": boundary["boundary_kind"],
            "owner_room_ids": tuple(boundary["owner_room_ids"]),
            "mutability": boundary["mutability"],
            "movable": boundary["movable"],
            "constraint_reasons": tuple(boundary["constraint_reasons"]),
            "start": boundary["start"],
            "end": boundary["end"],
            "length": boundary["length"],
            "opening_ids": tuple(boundary["opening_ids"]),
        }
        for boundary in fixture["boundaries"]
        if boundary.get("boundary_kind") not in {"duplicate", "artifact"}
    ]


def _expected_wall_segments(fixture: dict) -> list[dict]:
    opening_ids_by_wall: dict[str, list[str]] = {}
    for opening in fixture["openings"]:
        host_wall_id = opening.get("host_wall_id")
        if host_wall_id:
            opening_ids_by_wall.setdefault(host_wall_id, []).append(opening["opening_id"])

    return [
        {
            "wall_id": wall["wall_id"],
            "boundary_kind": wall["boundary_kind"],
            "owner_room_ids": tuple(wall["owner_room_ids"]),
            "mutability": wall["mutability"],
            "movable": wall["movable"],
            "hosted_opening_ids": tuple(opening_ids_by_wall.get(wall["wall_id"], [])),
            "start": wall["start"],
            "end": wall["end"],
            "length": wall["length"],
        }
        for wall in fixture["walls"]
    ]


def _expected_openings(fixture: dict) -> list[dict]:
    return [
        {
            "opening_id": opening["opening_id"],
            "opening_kind": opening["opening_kind"],
            "host_wall_id": opening["host_wall_id"],
            "owner_room_ids": tuple(opening["owner_room_ids"]),
            "confidence": opening["confidence"],
            "rehost_required": opening["rehost_required"],
            "rehostable": opening["rehostable"],
            "constraint_reasons": tuple(opening["constraint_reasons"]),
            "offset": opening["offset"],
            "span": opening["span"],
        }
        for opening in fixture["openings"]
    ]


def test_normalize_plan_exposes_rich_assembly_in_fixture_order_and_strips_cad_traces():
    fixture = _load_fixture()
    normalized = normalize_plan(_build_catalog_job())

    expected_room_summaries = _expected_room_summaries(fixture)
    expected_boundary_segments = _expected_boundary_segments(fixture)
    expected_wall_segments = _expected_wall_segments(fixture)
    expected_openings = _expected_openings(fixture)

    assert normalized.source_kind == "plan"
    assert normalized.canonical_unit == fixture["canonical_unit"]

    assert normalized.movable_boundary_count == sum(
        1 for boundary in fixture["boundaries"] if boundary["mutability"] == "movable"
    )
    assert normalized.rehostable_opening_count == sum(
        1 for opening in fixture["openings"] if opening["rehostable"]
    )

    assert isinstance(normalized.room_summaries, tuple)
    assert isinstance(normalized.boundary_segments, tuple)
    assert isinstance(normalized.wall_segments, tuple)
    assert isinstance(normalized.openings, tuple)

    assert _asdict_items(normalized.room_summaries) == expected_room_summaries

    assert normalized.room_count == len(fixture["rooms"])
    assert normalized.wall_count == len(fixture["walls"])
    assert normalized.opening_count == len(fixture["openings"])
    assert normalized.footprint_bbox == fixture["footprint_bbox"]

    assert _asdict_items(normalized.boundary_segments) == expected_boundary_segments
    assert _asdict_items(normalized.wall_segments) == expected_wall_segments
    assert _asdict_items(normalized.openings) == expected_openings

    assert "cad_traces" not in normalized.payload
    assert "boundary_nodes" not in normalized.payload


def test_normalize_plan_room_boundary_links_only_reference_retained_boundary_segments():
    normalized = normalize_plan(_build_catalog_job())

    retained_boundary_ids = {segment.boundary_id for segment in normalized.boundary_segments}

    assert retained_boundary_ids
    for room_summary in normalized.room_summaries:
        assert set(room_summary.owner_boundary_ids).issubset(retained_boundary_ids)


def test_normalize_plan_treats_rich_payload_with_empty_rooms_as_catalog_payload():
    payload = _load_catalog_payload()
    payload["rooms"] = []
    job = build_site_fit_job(
        plan=payload,
        structure=None,
        site_constraints={"buildable_envelope": {"x": 0, "y": 0, "width": 5000, "height": 5000}},
        design_locks={},
        jurisdiction=None,
        ruleset_version="site_fit_contract_v1",
    )

    normalized = normalize_plan(job)

    assert normalized.source_kind == "plan"
    assert normalized.room_count == 0
    assert len(normalized.boundary_segments) > 0
    assert len(normalized.wall_segments) == len(payload["walls"])
    assert len(normalized.openings) == len(payload["openings"])
    assert normalized.wall_count == len(payload["walls"])
    assert normalized.opening_count == len(payload["openings"])
    assert normalized.footprint_bbox == payload["footprint_bbox"]


def test_normalize_plan_does_not_double_normalize_bbox_derived_from_catalog_boundaries():
    payload = {
        "model": "catalog-like-ft",
        "unit": "ft",
        "rooms": [],
        "walls": [],
        "openings": [],
        "boundaries": [
            {
                "boundary_id": "boundary-1",
                "boundary_kind": "exterior",
                "owner_room_ids": [],
                "mutability": "protected",
                "movable": False,
                "constraint_reasons": [],
                "start": {"x": 0.0, "y": 0.0},
                "end": {"x": 12.0, "y": 0.0},
                "length": 12.0,
                "opening_ids": [],
            },
            {
                "boundary_id": "boundary-2",
                "boundary_kind": "exterior",
                "owner_room_ids": [],
                "mutability": "protected",
                "movable": False,
                "constraint_reasons": [],
                "start": {"x": 12.0, "y": 0.0},
                "end": {"x": 12.0, "y": 12.0},
                "length": 12.0,
                "opening_ids": [],
            },
            {
                "boundary_id": "boundary-3",
                "boundary_kind": "exterior",
                "owner_room_ids": [],
                "mutability": "protected",
                "movable": False,
                "constraint_reasons": [],
                "start": {"x": 12.0, "y": 12.0},
                "end": {"x": 0.0, "y": 12.0},
                "length": 12.0,
                "opening_ids": [],
            },
            {
                "boundary_id": "boundary-4",
                "boundary_kind": "exterior",
                "owner_room_ids": [],
                "mutability": "protected",
                "movable": False,
                "constraint_reasons": [],
                "start": {"x": 0.0, "y": 12.0},
                "end": {"x": 0.0, "y": 0.0},
                "length": 12.0,
                "opening_ids": [],
            },
        ],
        "boundary_nodes": [{"node_id": "node-1"}],
        "cad_traces": [],
        "structure_meta": {"unit": "ft"},
    }
    job = build_site_fit_job(
        plan=payload,
        structure=None,
        site_constraints={"buildable_envelope": {"x": 0, "y": 0, "width": 5000, "height": 5000}},
        design_locks={},
        jurisdiction=None,
        ruleset_version="site_fit_contract_v1",
    )

    normalized = normalize_plan(job)

    assert normalized.source_kind == "plan"
    assert normalized.footprint_bbox == {
        "x1": 0.0,
        "y1": 0.0,
        "x2": 144.0,
        "y2": 144.0,
        "width": 144.0,
        "height": 144.0,
    }
