"""Tests for the worker_client routing logic."""
import httpx
import pytest

from backend.worker_client import get_worker_health, infer_structure
from backend.worker_contract import WorkerError

from tests.helpers import build_manual_structure, build_synthetic_structure_image


def test_heuristic_backend_works_via_worker_client():
    """worker_client routes to heuristic_local by default."""
    result = infer_structure(build_synthetic_structure_image(), backend="heuristic_local")

    assert result["source"] == "heuristic_local"
    assert len(result["walls"]) >= 5
    assert len(result["openings"]) == 2


def test_unsupported_backend_raises():
    with pytest.raises(ValueError, match="Unsupported"):
        infer_structure("dummy", backend="nonexistent")


def test_remote_backend_raises_when_no_worker(monkeypatch):
    """Remote backend should raise WorkerError when worker is unreachable."""
    monkeypatch.setenv("POINTAI_WORKER_URL", "http://localhost:19999")
    with pytest.raises(WorkerError) as exc_info:
        infer_structure("dummy", backend="remote")
    assert exc_info.value.code == "WORKER_UNREACHABLE"


def test_cubicasa_backend_routes_to_local_model(monkeypatch):
    monkeypatch.setattr("backend.worker_client.cubicasa_available", lambda model_variant=None: (True, None))
    monkeypatch.setattr(
        "backend.worker_client.infer_cubicasa",
        lambda image, *, model_variant=None: build_manual_structure(source="cubicasa5k"),
    )

    result = infer_structure(build_synthetic_structure_image(), backend="cubicasa_local")

    assert result["source"] == "cubicasa5k"
    assert result["inference_debug"]["backend"] == "cubicasa_local"
    assert len(result["openings"]) == 2


def test_cubicasa_backend_passes_model_variant_to_local_model(monkeypatch):
    captured: dict[str, object] = {}

    def fake_infer(image: str, *, model_variant: str | None = None):
        captured["image"] = image
        captured["model_variant"] = model_variant
        return build_manual_structure(source=f"cubicasa5k:{model_variant or 'baseline'}")

    monkeypatch.setattr("backend.worker_client.cubicasa_available", lambda model_variant=None: (True, None))
    monkeypatch.setattr("backend.worker_client.infer_cubicasa", fake_infer)

    result = infer_structure(
        build_synthetic_structure_image(),
        backend="cubicasa_local",
        options={"model_variant": "experimental"},
    )

    assert captured["model_variant"] == "experimental"
    assert result["source"] == "cubicasa5k:experimental"


def test_remote_backend_succeeds_with_mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/infer/structure"
        payload = {
            "model_name": "floortrans-v1",
            "model_version": "1.2.3",
            "image_size": {"width": 220, "height": 160},
            "walls": [
                {
                    "polyline": [{"x": 20, "y": 24}, {"x": 200, "y": 24}],
                    "thickness": 8,
                    "orientation": "horizontal",
                    "is_exterior": True,
                    "confidence": 0.9,
                }
            ],
            "openings": [
                {
                    "kind": "door",
                    "position": {"x": 110, "y": 74},
                    "span": 28,
                    "orientation": "vertical",
                    "confidence": 0.88,
                }
            ],
            "debug_overlay_b64": "dGVzdA==",
        }
        return httpx.Response(200, json=payload)

    result = infer_structure(
        build_synthetic_structure_image(),
        backend="remote",
        worker_url="http://worker.test",
        transport=httpx.MockTransport(handler),
        options={"include_debug_overlay": True},
    )

    assert result["source"] == "remote_worker/1.2.3"
    assert result["inference_debug"]["debug_overlay_b64"] == "dGVzdA=="
    assert len(result["walls"]) == 1
    assert len(result["openings"]) == 1


def test_get_worker_health_uses_remote_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "ready": True,
                "model_name": "floortrans-v1",
                "model_version": "1.2.3",
                "backend": "remote",
            },
        )

    health = get_worker_health(
        worker_url="http://worker.test",
        transport=httpx.MockTransport(handler),
    )

    assert health.ready is True
    assert health.model_name == "floortrans-v1"
    assert health.backend == "remote"
