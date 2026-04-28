from fastapi.testclient import TestClient

from backend.app import app
from tests.helpers import (
    build_low_quality_structure,
    build_manual_structure,
    build_mitunet_infer_result,
    build_synthetic_structure_image,
)


SAMPLE_PLAN = {
    "model": "API Sample",
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


client = TestClient(app)


def test_parse_structure_endpoint_returns_v2_payload():
    response = client.post("/api/v2/parse-structure", json={"plan": SAMPLE_PLAN})

    assert response.status_code == 200
    payload = response.json()
    assert payload["structure"]["source"] == "legacy_rooms_adapter"
    assert payload["quality_metrics"]["wall_count"] == 5
    assert payload["needs_review"] is False
    assert payload["preview_url"].startswith("/artifacts/")
    assert payload["artifact_urls"]["structure_url"].startswith("/artifacts/")
    assert payload["auto_annotations"] == []

    preview = client.get(payload["preview_url"])
    assert preview.status_code == 200
    assert "image/png" in preview.headers["content-type"]


def test_generate_dxf_endpoint_writes_downloadable_file():
    response = client.post("/api/v2/generate-dxf", json={"plan": SAMPLE_PLAN})

    assert response.status_code == 200
    payload = response.json()
    assert payload["scale_status"] == "calibrated"
    assert payload["dxf_url"].startswith("/downloads/")
    assert payload["auto_annotations"] == []
    assert "computed_rooms" not in payload
    assert "region_overlay" not in payload

    download = client.get(payload["dxf_url"])
    assert download.status_code == 200
    assert "application/dxf" in download.headers["content-type"]


def test_parse_structure_endpoint_accepts_image_and_routes_through_worker_client(monkeypatch):
    monkeypatch.setattr("backend.services.parse_service.infer_structure", lambda image: build_manual_structure(source="cubicasa_local"))

    response = client.post("/api/v2/parse-structure", json={"image": build_synthetic_structure_image()})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["structure"]["source"] == "cubicasa_local"
    assert payload["quality_metrics"]["merged_wall_count"] == 5
    assert payload["quality_metrics"]["anchored_opening_count"] == 2
    assert payload["quality_metrics"]["inference_backend"] == "cubicasa_local"
    assert payload["quality_metrics"]["quality_gate_passed"] is True
    assert payload["preview_url"].startswith("/artifacts/")

    structure_artifact = client.get(payload["artifact_urls"]["structure_url"])
    assert structure_artifact.status_code == 200
    assert structure_artifact.json()["source"] == "cubicasa_local"


def test_generate_dxf_endpoint_accepts_image_and_produces_preview_and_dxf(monkeypatch):
    monkeypatch.setattr("backend.services.parse_service.infer_structure", lambda image: build_manual_structure(source="cubicasa_local"))

    response = client.post("/api/v2/generate-dxf", json={"image": build_synthetic_structure_image()})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["structure"]["source"] == "cubicasa_local"
    assert payload["scale_status"] == "unverified"
    assert payload["preview_url"].startswith("/artifacts/")
    assert payload["quality_metrics"]["quality_gate_passed"] is True

    preview = client.get(payload["preview_url"])
    assert preview.status_code == 200
    assert "image/png" in preview.headers["content-type"]

    download = client.get(payload["dxf_url"])
    assert download.status_code == 200
    assert "application/dxf" in download.headers["content-type"]


def test_generate_dxf_endpoint_marks_low_quality_image_results_for_review(monkeypatch):
    monkeypatch.setattr("backend.services.parse_service.infer_structure", lambda image: build_low_quality_structure())

    response = client.post("/api/v2/generate-dxf", json={"image": build_synthetic_structure_image()})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["needs_review"] is True
    assert payload["quality_metrics"]["quality_gate_passed"] is False
    assert "no_openings_detected" in payload["quality_metrics"]["quality_gate_reasons"]


def test_generate_dxf_endpoint_passes_model_variant_and_reports_it(monkeypatch):
    captured: dict[str, object] = {}

    def fake_infer(image: str, *, options=None):
        captured["options"] = options
        return build_manual_structure(source="cubicasa_local")

    monkeypatch.setattr("backend.services.parse_service.infer_structure", fake_infer)

    response = client.post(
        "/api/v2/generate-dxf",
        json={"image": build_synthetic_structure_image(), "model_variant": "baseline"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert captured["options"] == {"model_variant": "baseline"}
    assert payload["quality_metrics"]["model_variant"] == "baseline"


def test_generate_dxf_endpoint_uses_mask_regions_mode_for_mitunet(monkeypatch):
    def fake_infer(image: str, *, backend=None, options=None):
        return build_mitunet_infer_result()

    monkeypatch.setattr("backend.services.parse_service.infer_structure", fake_infer)

    response = client.post(
        "/api/v2/generate-dxf",
        json={"image": build_synthetic_structure_image(), "model_variant": "mitunet"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["quality_metrics"]["dxf_mode"] == "mask_regions"
    assert payload["structure"]["structure_meta"]["dxf_mode"] == "mask_regions"
    assert payload["structure"]["structure_meta"]["dxf_region_plan"]["meta"]["region_count"] > 0
    assert payload["structure"]["structure_meta"]["dxf_region_plan"]["meta"]["max_wall_thickness"] == 6.0
    assert payload["structure"]["structure_meta"]["mitunet_region_debug"]["stage_order"] == [
        "raw_wall_mask",
        "cleaned_wall_mask",
        "horizontal_extraction",
        "vertical_extraction",
        "trimmed_rectangles",
        "clamped_regions",
    ]
    assert payload["artifact_urls"]["dxf_region_plan_url"].startswith("/artifacts/")
    assert payload["artifact_urls"]["mitunet_region_debug_url"].startswith("/artifacts/")
    assert payload["artifact_urls"]["provenance_url"].startswith("/artifacts/")
    assert all(
        region["draw_thickness"] <= 6.0
        for region in payload["structure"]["structure_meta"]["dxf_region_plan"]["regions"]
    )
    region_debug = client.get(payload["artifact_urls"]["mitunet_region_debug_url"])
    assert region_debug.status_code == 200
    assert region_debug.json()["clamped_regions"]["region_count"] > 0
    provenance = client.get(payload["artifact_urls"]["provenance_url"])
    assert provenance.status_code == 200
    assert provenance.json()["backend"] == "mitunet_local"


def test_generate_dxf_endpoint_ignores_legacy_dxf_mode_override_for_mitunet(monkeypatch):
    def fake_infer(image: str, *, backend=None, options=None):
        return build_mitunet_infer_result()

    monkeypatch.setattr("backend.services.parse_service.infer_structure", fake_infer)

    response = client.post(
        "/api/v2/generate-dxf",
        json={
            "image": build_synthetic_structure_image(),
            "model_variant": "mitunet",
            "dxf_mode": "structural",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["quality_metrics"]["dxf_mode"] == "mask_regions"
    assert payload["structure"]["structure_meta"]["dxf_mode"] == "mask_regions"
    assert "dxf_region_plan" in payload["structure"]["structure_meta"]
    assert "mitunet_region_debug" in payload["structure"]["structure_meta"]


def test_parse_structure_endpoint_returns_auto_annotations_for_ensemble(monkeypatch):
    def fake_infer(image: str, *, backend=None, options=None):
        result = build_mitunet_infer_result()
        result["source"] = "ensemble_local"
        result["openings"] = []
        result["_auto_annotations"] = [
            {"type": "window", "x1": 10.0, "y1": 20.0, "x2": 30.0, "y2": 20.0, "swing": "down"},
        ]
        result["inference_debug"] = {"backend": "ensemble_local", "model_variant": "ensemble"}
        return result

    monkeypatch.setattr("backend.services.parse_service.infer_structure", fake_infer)

    response = client.post(
        "/api/v2/parse-structure",
        json={"image": build_synthetic_structure_image(), "model_variant": "ensemble"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["auto_annotations"][0]["type"] == "window"
    assert payload["quality_metrics"]["opening_count"] == 1
    assert "no_openings_detected" not in payload["quality_metrics"]["quality_gate_reasons"]


def test_generate_dxf_endpoint_uses_reviewed_opening_annotations(monkeypatch):
    captured: dict[str, object] = {}

    def fake_infer(image: str, *, backend=None, options=None):
        result = build_mitunet_infer_result()
        result["source"] = "ensemble_local"
        result["openings"] = []
        result["_auto_annotations"] = [
            {"type": "window", "x1": 10.0, "y1": 20.0, "x2": 30.0, "y2": 20.0, "swing": "down"},
        ]
        result["inference_debug"] = {"backend": "ensemble_local", "model_variant": "ensemble"}
        return result

    def fake_generate_dxf(*, parsed, out_path, dxf_mode, image_b64):
        captured["annotations"] = parsed["_infer_result"].get("_auto_annotations", [])
        return {"dxf_preview": None}

    monkeypatch.setattr("backend.services.parse_service.infer_structure", fake_infer)
    monkeypatch.setattr("backend.app.generate_dxf", fake_generate_dxf)

    response = client.post(
        "/api/v2/generate-dxf",
        json={
            "image": build_synthetic_structure_image(),
            "model_variant": "ensemble",
            "annotations": [
                {"type": "door", "x1": 50.0, "y1": 60.0, "x2": 50.0, "y2": 90.0, "swing": "left"},
            ],
        },
    )

    assert response.status_code == 200, response.text
    assert captured["annotations"] == [
        {"type": "door", "x1": 50.0, "y1": 60.0, "x2": 50.0, "y2": 90.0, "swing": "left"},
    ]
