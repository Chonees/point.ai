from backend.plan_parser import parse_structure_payload

from tests.helpers import build_low_quality_structure, build_manual_structure


SAMPLE_PLAN = {
    "model": "Parser Sample",
    "rooms": [
        {
            "name": "LIVING",
            "x": 0,
            "y": 0,
            "w": 100,
            "h": 100,
            "doors": [{"wall": "right", "offset": 20, "width": 30, "type": "normal"}],
            "windows": [{"wall": "bottom", "offset": 20, "width": 24}],
        },
        {
            "name": "BED 1",
            "x": 100,
            "y": 0,
            "w": 80,
            "h": 100,
            "windows": [{"wall": "top", "offset": 16, "width": 20}],
        },
    ],
}


def test_parse_structure_from_legacy_rooms_builds_canonical_contract():
    parsed = parse_structure_payload(plan=SAMPLE_PLAN)
    structure = parsed["structure"]

    assert structure["source"] == "legacy_rooms_adapter"
    assert structure["structure_meta"]["scale_status"] == "calibrated"
    assert len(structure["walls"]) == 5
    assert len(structure["openings"]) == 3
    assert any(not wall["is_exterior"] for wall in structure["walls"])
    assert all(opening["wall_id"] for opening in structure["openings"])
    assert parsed["quality_metrics"]["quality_gate_passed"] is True
    assert parsed["needs_review"] is False


def test_parse_structure_from_manual_inference_passes_quality_gate():
    parsed = parse_structure_payload(structure=build_manual_structure(source="heuristic_local"))
    structure = parsed["structure"]

    assert structure["source"] == "heuristic_local"
    assert structure["structure_meta"]["unit"] == "pixel"
    assert structure["structure_meta"]["scale_status"] == "unverified"
    assert len(structure["walls"]) == 5
    assert len(structure["openings"]) == 2
    assert sum(1 for wall in structure["walls"] if wall["is_exterior"]) == 4
    assert any(not wall["is_exterior"] for wall in structure["walls"])
    assert all(opening["wall_id"] for opening in structure["openings"])
    assert parsed["quality_metrics"]["raw_wall_count"] == 5
    assert parsed["quality_metrics"]["merged_wall_count"] == 5
    assert parsed["quality_metrics"]["quality_gate_passed"] is True
    assert parsed["needs_review"] is False


def test_parse_structure_marks_low_quality_cases_for_review():
    parsed = parse_structure_payload(structure=build_low_quality_structure())

    assert parsed["needs_review"] is True
    assert parsed["quality_metrics"]["quality_gate_passed"] is False
    assert "no_openings_detected" in parsed["quality_metrics"]["quality_gate_reasons"]
