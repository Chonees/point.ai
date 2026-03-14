from fastapi.testclient import TestClient

from backend.app import app
from tests.helpers import build_low_quality_structure, build_manual_structure, build_synthetic_structure_image


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

    preview = client.get(payload["preview_url"])
    assert preview.status_code == 200
    assert "image/png" in preview.headers["content-type"]


def test_generate_dxf_endpoint_writes_downloadable_file():
    response = client.post("/api/v2/generate-dxf", json={"plan": SAMPLE_PLAN})

    assert response.status_code == 200
    payload = response.json()
    assert payload["scale_status"] == "calibrated"
    assert payload["dxf_url"].startswith("/downloads/")

    download = client.get(payload["dxf_url"])
    assert download.status_code == 200
    assert "application/dxf" in download.headers["content-type"]


def test_parse_structure_endpoint_accepts_image_and_routes_through_worker_client(monkeypatch):
    monkeypatch.setattr("backend.app.infer_structure", lambda image: build_manual_structure(source="cubicasa_local"))

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
    monkeypatch.setattr("backend.app.infer_structure", lambda image: build_manual_structure(source="cubicasa_local"))

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
    monkeypatch.setattr("backend.app.infer_structure", lambda image: build_low_quality_structure())

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

    monkeypatch.setattr("backend.app.infer_structure", fake_infer)

    response = client.post(
        "/api/v2/generate-dxf",
        json={"image": build_synthetic_structure_image(), "model_variant": "experimental"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert captured["options"] == {"model_variant": "experimental"}
    assert payload["quality_metrics"]["model_variant"] == "experimental"
