from backend.plan_parser import parse_structure_payload

from tests.helpers import build_low_quality_structure, build_manual_structure


def _pixel_box_structure() -> dict:
    return {
        "model": "Pixel Box",
        "source": "fixture/pixel_box",
        "walls": [
            {
                "id": "wall-top",
                "orientation": "horizontal",
                "polyline": [{"x": 20.0, "y": 20.0}, {"x": 200.0, "y": 20.0}],
                "thickness": 8.0,
                "is_exterior": True,
                "confidence": 0.95,
            },
            {
                "id": "wall-bottom",
                "orientation": "horizontal",
                "polyline": [{"x": 20.0, "y": 140.0}, {"x": 200.0, "y": 140.0}],
                "thickness": 8.0,
                "is_exterior": True,
                "confidence": 0.95,
            },
            {
                "id": "wall-left",
                "orientation": "vertical",
                "polyline": [{"x": 20.0, "y": 20.0}, {"x": 20.0, "y": 140.0}],
                "thickness": 8.0,
                "is_exterior": True,
                "confidence": 0.95,
            },
            {
                "id": "wall-right",
                "orientation": "vertical",
                "polyline": [{"x": 200.0, "y": 20.0}, {"x": 200.0, "y": 140.0}],
                "thickness": 8.0,
                "is_exterior": True,
                "confidence": 0.95,
            },
        ],
        "openings": [],
        "structure_meta": {
            "image_size": {"width": 220, "height": 160},
            "scale_status": "unverified",
            "unit": "pixel",
        },
        "inference_debug": {
            "backend": "fixture/pixel_box",
        },
    }


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
    assert "pipeline_debug" in structure
    assert "raw_segments" in structure["pipeline_debug"]
    assert "snapped_segments" in structure["pipeline_debug"]
    assert "merged_segments" in structure["pipeline_debug"]
    assert "anchored_openings" in structure["pipeline_debug"]
    assert parsed["quality_metrics"]["quality_gate_passed"] is True
    assert parsed["needs_review"] is False


def test_parse_structure_marks_low_quality_cases_for_review():
    parsed = parse_structure_payload(structure=build_low_quality_structure())

    assert parsed["needs_review"] is True
    assert parsed["quality_metrics"]["quality_gate_passed"] is False
    assert "no_openings_detected" in parsed["quality_metrics"]["quality_gate_reasons"]


def test_parse_structure_allows_missing_openings_when_detection_is_disabled():
    structure = build_manual_structure(source="heuristic_local", with_openings=False)
    structure["inference_debug"]["opening_detection_disabled"] = True
    structure["structure_meta"]["opening_detection_mode"] = "disabled"

    parsed = parse_structure_payload(structure=structure)

    assert parsed["needs_review"] is False
    assert parsed["quality_metrics"]["quality_gate_passed"] is True
    assert "no_openings_detected" not in parsed["quality_metrics"]["quality_gate_reasons"]


def test_parse_structure_keeps_short_thin_wall_when_it_forms_a_real_junction():
    structure = _pixel_box_structure()
    structure["walls"].append(
        {
            "id": "wall-thin-stub",
            "orientation": "vertical",
            "polyline": [{"x": 80.0, "y": 20.0}, {"x": 80.0, "y": 44.0}],
            "thickness": 1.5,
            "is_exterior": False,
            "confidence": 0.85,
        }
    )

    parsed = parse_structure_payload(structure=structure)

    assert parsed["quality_metrics"]["merged_wall_count"] == 5
    assert any(
        wall["orientation"] == "vertical"
        and abs(wall["polyline"][0]["x"] - 80.0) < 0.1
        and abs(wall["polyline"][1]["y"] - wall["polyline"][0]["y"]) >= 24.0
        for wall in parsed["structure"]["walls"]
    )


def test_parse_structure_keeps_short_wall_with_near_junction_support():
    structure = _pixel_box_structure()
    structure["walls"].append(
        {
            "id": "wall-supported-stub",
            "orientation": "vertical",
            "polyline": [{"x": 120.0, "y": 27.0}, {"x": 120.0, "y": 45.0}],
            "thickness": 8.0,
            "is_exterior": False,
            "confidence": 0.85,
        }
    )

    parsed = parse_structure_payload(structure=structure)

    assert parsed["quality_metrics"]["merged_wall_count"] == 5
    assert any(
        wall["orientation"] == "vertical"
        and abs(wall["polyline"][0]["x"] - 120.0) < 0.1
        and abs(wall["polyline"][1]["y"] - wall["polyline"][0]["y"]) >= 18.0
        for wall in parsed["structure"]["walls"]
    )
