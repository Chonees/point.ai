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


def _sorted_by(items: list[dict], key: str) -> list[dict]:
    return sorted(items, key=lambda item: item[key])


def _asdict_items(items) -> list[dict]:
    return [asdict(item) for item in items]


def _expected_room_summaries(fixture: dict) -> list[dict]:
    boundary_ids_by_room: dict[str, list[str]] = {}
    for boundary in fixture["boundaries"]:
        for room_id in boundary.get("owner_room_ids") or []:
            boundary_ids_by_room.setdefault(room_id, []).append(boundary["boundary_id"])

    return _sorted_by(
        [
            {
                "room_id": room["room_id"],
                "name": room["name"],
                "category": room["category"],
                "mutability": room["mutability"],
                "min_width": room["min_width"],
                "min_height": room["min_height"],
                "min_area": room["min_area"],
                "bbox": room["bbox"],
                "owner_boundary_ids": boundary_ids_by_room.get(room["room_id"], []),
            }
            for room in fixture["rooms"]
        ],
        "room_id",
    )


def _expected_boundary_segments(fixture: dict) -> list[dict]:
    return _sorted_by(
        [
            {
                "boundary_id": boundary["boundary_id"],
                "boundary_kind": boundary["boundary_kind"],
                "owner_room_ids": boundary["owner_room_ids"],
                "mutability": boundary["mutability"],
                "movable": boundary["movable"],
                "constraint_reasons": boundary["constraint_reasons"],
                "start": boundary["start"],
                "end": boundary["end"],
                "length": boundary["length"],
                "opening_ids": boundary["opening_ids"],
            }
            for boundary in fixture["boundaries"]
            if boundary.get("boundary_kind") not in {"duplicate", "artifact"}
        ],
        "boundary_id",
    )


def _expected_wall_segments(fixture: dict) -> list[dict]:
    opening_ids_by_wall: dict[str, list[str]] = {}
    for opening in fixture["openings"]:
        host_wall_id = opening.get("host_wall_id")
        if host_wall_id:
            opening_ids_by_wall.setdefault(host_wall_id, []).append(opening["opening_id"])

    return _sorted_by(
        [
            {
                "wall_id": wall["wall_id"],
                "boundary_kind": wall["boundary_kind"],
                "owner_room_ids": wall["owner_room_ids"],
                "mutability": wall["mutability"],
                "movable": wall["movable"],
                "hosted_opening_ids": opening_ids_by_wall.get(wall["wall_id"], []),
                "start": wall["start"],
                "end": wall["end"],
                "length": wall["length"],
            }
            for wall in fixture["walls"]
        ],
        "wall_id",
    )


def _expected_openings(fixture: dict) -> list[dict]:
    return _sorted_by(
        [
            {
                "opening_id": opening["opening_id"],
                "opening_kind": opening["opening_kind"],
                "host_wall_id": opening["host_wall_id"],
                "owner_room_ids": opening["owner_room_ids"],
                "confidence": opening["confidence"],
                "rehost_required": opening["rehost_required"],
                "rehostable": opening["rehostable"],
                "constraint_reasons": opening["constraint_reasons"],
                "offset": opening["offset"],
                "span": opening["span"],
            }
            for opening in fixture["openings"]
        ],
        "opening_id",
    )


def test_normalize_plan_exposes_v2_assembly_from_catalog_fixture():
    fixture = _load_fixture()
    normalized = normalize_plan(_build_catalog_job())

    expected_room_summaries = _expected_room_summaries(fixture)
    expected_boundary_segments = _expected_boundary_segments(fixture)
    expected_wall_segments = _expected_wall_segments(fixture)
    expected_openings = _expected_openings(fixture)

    assert normalized.source_kind == "plan"
    assert normalized.canonical_unit == fixture["canonical_unit"]

    assert _asdict_items(normalized.room_summaries) == expected_room_summaries
    assert _asdict_items(normalized.boundary_segments) == expected_boundary_segments
    assert _asdict_items(normalized.wall_segments) == expected_wall_segments
    assert _asdict_items(normalized.openings) == expected_openings

    assert normalized.movable_boundary_count == sum(
        1 for boundary in fixture["boundaries"] if boundary["movable"]
    )
    assert normalized.rehostable_opening_count == sum(
        1 for opening in fixture["openings"] if opening["rehostable"]
    )
