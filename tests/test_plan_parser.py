from backend.plan_parser import parse_structure_payload

from tests.helpers import build_low_quality_structure, build_manual_structure


def _dxf_space_opening_fixture() -> dict:
    return {
        "model": "DXF Space Fixture",
        "source": "ensemble_local",
        "walls": [
            {
                "id": "wall-top",
                "orientation": "horizontal",
                "polyline": [{"x": 20.0, "y": 140.0}, {"x": 200.0, "y": 140.0}],
                "thickness": 8.0,
                "is_exterior": True,
                "confidence": 0.95,
            },
            {
                "id": "wall-interior",
                "orientation": "vertical",
                "polyline": [{"x": 110.0, "y": 20.0}, {"x": 110.0, "y": 140.0}],
                "thickness": 8.0,
                "is_exterior": False,
                "confidence": 0.9,
            },
        ],
        "openings": [],
        "_auto_annotations": [
            {
                "id": "ann-door",
                "type": "door",
                "x1": 110.0,
                "y1": 60.0,
                "x2": 110.0,
                "y2": 88.0,
                "wall_id": "wall-interior",
            },
            {
                "id": "ann-window",
                "type": "window",
                "x1": 136.0,
                "y1": 20.0,
                "x2": 166.0,
                "y2": 20.0,
                "wall_id": "wall-top",
            },
        ],
        "structure_meta": {
            "image_size": {"width": 220, "height": 160},
            "scale_status": "unverified",
            "unit": "pixel",
            "coordinate_space": "dxf_y_up",
        },
        "inference_debug": {
            "backend": "ensemble_local",
        },
    }


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


def _single_exterior_wall_with_windows(*, spans: list[float]) -> dict:
    positions = [40.0, 120.0, 200.0, 280.0, 360.0]
    openings = []
    for index, (cx, span) in enumerate(zip(positions, spans), start=1):
        openings.append(
            {
                "id": f"window-{index:02d}",
                "kind": "window",
                "wall_id": "wall-top",
                "position": {"x": cx, "y": 20.0},
                "span": span,
                "orientation": "horizontal",
                "confidence": 0.9,
            }
        )
    return {
        "model": "Exterior Window Density",
        "source": "fixture/window_density",
        "walls": [
            {
                "id": "wall-top",
                "orientation": "horizontal",
                "polyline": [{"x": 0.0, "y": 20.0}, {"x": 400.0, "y": 20.0}],
                "thickness": 8.0,
                "is_exterior": True,
                "confidence": 0.95,
            },
        ],
        "openings": openings,
        "structure_meta": {
            "image_size": {"width": 420, "height": 120},
            "scale_status": "unverified",
            "unit": "pixel",
        },
        "inference_debug": {
            "backend": "fixture/window_density",
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


def test_parse_structure_preserves_coordinate_space_metadata():
    structure = build_manual_structure(source="mitunet_local", with_openings=False)
    structure["structure_meta"]["coordinate_space"] = "dxf_y_up"

    parsed = parse_structure_payload(structure=structure)

    assert parsed["structure"]["structure_meta"]["coordinate_space"] == "dxf_y_up"


def test_parse_structure_materializes_auto_annotations_as_openings_in_dxf_space():
    parsed = parse_structure_payload(structure=_dxf_space_opening_fixture())

    openings = parsed["structure"]["openings"]
    wall_ids = {wall["id"] for wall in parsed["structure"]["walls"]}

    assert len(openings) == 2
    assert parsed["quality_metrics"]["raw_opening_count"] == 2
    door = next(opening for opening in openings if opening["kind"] == "door")
    window = next(opening for opening in openings if opening["kind"] == "window")
    assert door["wall_id"] in wall_ids
    assert round(door["position"]["x"], 1) == 110.0
    assert round(door["position"]["y"], 1) == 86.0
    assert window["wall_id"] in wall_ids
    assert round(window["position"]["x"], 1) == 151.0
    assert round(window["position"]["y"], 1) == 140.0


def test_parse_structure_marks_low_quality_cases_for_review():
    parsed = parse_structure_payload(structure=build_low_quality_structure())

    assert parsed["needs_review"] is True
    assert parsed["quality_metrics"]["quality_gate_passed"] is False
    assert "no_openings_detected" in parsed["quality_metrics"]["quality_gate_reasons"]


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


def test_parse_structure_keeps_multiple_legitimate_windows_on_long_exterior_wall():
    parsed = parse_structure_payload(structure=_single_exterior_wall_with_windows(spans=[40.0, 40.0, 40.0, 40.0, 40.0]))

    windows = [opening for opening in parsed["structure"]["openings"] if opening["kind"] == "window"]

    assert len(windows) == 5


def test_parse_structure_prunes_only_overdense_exterior_window_runs():
    parsed = parse_structure_payload(structure=_single_exterior_wall_with_windows(spans=[90.0, 90.0, 90.0, 90.0, 90.0]))

    windows = [opening for opening in parsed["structure"]["openings"] if opening["kind"] == "window"]

    assert len(windows) == 3
