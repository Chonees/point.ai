from fastapi.testclient import TestClient

from backend.worker_contract import validate_worker_response
from backend.worker_server import worker_app
from tests.helpers import build_synthetic_structure_image


client = TestClient(worker_app)


def test_worker_health_endpoint_returns_ready_payload(monkeypatch):
    monkeypatch.setenv("POINTAI_WORKER_BACKEND", "heuristic_local")
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["backend"] == "heuristic_local"
    assert payload["model_name"]
    assert payload["model_version"]


def test_worker_infer_endpoint_returns_contract_payload(monkeypatch):
    monkeypatch.setenv("POINTAI_WORKER_BACKEND", "heuristic_local")
    response = client.post(
        "/infer/structure",
        json={"image": build_synthetic_structure_image(), "options": {"include_debug_overlay": True}},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    validated = validate_worker_response(payload)

    assert validated.model_name
    assert validated.model_version
    assert len(validated.walls) >= 6
    assert len(validated.openings) == 2
    assert validated.debug_overlay_b64 is not None


def test_worker_infer_endpoint_rejects_missing_image(monkeypatch):
    monkeypatch.setenv("POINTAI_WORKER_BACKEND", "heuristic_local")
    response = client.post("/infer/structure", json={"options": {}})

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "INVALID_IMAGE"


def test_worker_infer_endpoint_passes_model_variant_to_cubicasa(monkeypatch):
    captured: dict[str, object] = {}

    def fake_infer(image: str, *, model_variant: str | None = None):
        captured["model_variant"] = model_variant
        return {
            "model": "CubiCasa5k Baseline",
            "source": "cubicasa5k:baseline",
            "walls": [],
            "openings": [],
            "structure_meta": {"image_size": {"width": 10, "height": 10}},
        }

    monkeypatch.setenv("POINTAI_WORKER_BACKEND", "cubicasa_local")
    monkeypatch.setattr("backend.worker_server.cubicasa_available", lambda *args, **kwargs: (True, None))
    monkeypatch.setattr("backend.worker_server.infer_cubicasa", fake_infer)

    response = client.post(
        "/infer/structure",
        json={
            "image": build_synthetic_structure_image(),
            "options": {"model_variant": "baseline", "include_debug_overlay": False},
        },
    )

    assert response.status_code == 200, response.text
    assert captured["model_variant"] == "baseline"
