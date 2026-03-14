import pytest

from backend.worker_contract import (
    WorkerError,
    WorkerRequest,
    WorkerResponse,
    WallDetection,
    OpeningDetection,
    validate_worker_response,
)


def _valid_raw_response():
    return {
        "model_name": "floortrans-v1",
        "model_version": "0.1.0",
        "image_size": {"width": 512, "height": 512},
        "walls": [
            {
                "polyline": [{"x": 10, "y": 10}, {"x": 200, "y": 10}],
                "thickness": 4.0,
                "is_exterior": True,
                "confidence": 0.9,
                "orientation": "horizontal",
            },
            {
                "polyline": [{"x": 10, "y": 10}, {"x": 10, "y": 200}],
                "thickness": 4.0,
                "confidence": 0.85,
            },
        ],
        "openings": [
            {
                "kind": "door",
                "position": {"x": 80, "y": 10},
                "span": 30,
                "orientation": "horizontal",
                "confidence": 0.88,
            },
        ],
        "inference_time_ms": 120.5,
        "debug_overlay_b64": "dGVzdA==",
    }


def test_worker_request_to_dict():
    req = WorkerRequest(image_b64="abc123", options={"debug": True})
    d = req.to_dict()
    assert d["image"] == "abc123"
    assert d["options"]["debug"] is True


def test_validate_valid_response():
    raw = _valid_raw_response()
    result = validate_worker_response(raw)

    assert isinstance(result, WorkerResponse)
    assert result.model_name == "floortrans-v1"
    assert len(result.walls) == 2
    assert len(result.openings) == 1
    assert result.inference_time_ms == 120.5


def test_validate_converts_to_structure_dict():
    raw = _valid_raw_response()
    result = validate_worker_response(raw)
    structure = result.to_structure_dict()

    assert structure["model"] == "floortrans-v1"
    assert structure["source"] == "remote_worker/0.1.0"
    assert len(structure["walls"]) == 2
    assert len(structure["openings"]) == 1
    assert structure["walls"][0]["id"] == "raw-wall-0001"
    assert structure["openings"][0]["id"] == "raw-opening-0001"
    assert structure["structure_meta"]["unit"] == "pixel"
    assert structure["inference_debug"]["debug_overlay_b64"] == "dGVzdA=="


def test_validate_rejects_missing_fields():
    raw = {"model_name": "test"}
    with pytest.raises(WorkerError) as exc_info:
        validate_worker_response(raw)
    assert exc_info.value.code == "INVALID_RESPONSE"


def test_validate_raises_on_error_response():
    raw = {"error": {"code": "INFERENCE_FAILED", "message": "GPU OOM"}}
    with pytest.raises(WorkerError) as exc_info:
        validate_worker_response(raw)
    assert exc_info.value.code == "INFERENCE_FAILED"
    assert "GPU OOM" in exc_info.value.message


def test_validate_rejects_invalid_opening_kind():
    raw = _valid_raw_response()
    raw["openings"][0]["kind"] = "stairs"

    with pytest.raises(WorkerError) as exc_info:
        validate_worker_response(raw)

    assert exc_info.value.code == "INVALID_RESPONSE"
