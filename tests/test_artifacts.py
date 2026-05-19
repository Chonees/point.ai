from __future__ import annotations

import base64
import json

import numpy as np

import backend.artifacts as artifacts
from backend.artifacts import build_preview_image, save_structure_artifacts
from backend.image_utils import encode_png_data


def _png_data_uri(image: np.ndarray) -> str:
    return "data:image/png;base64," + base64.b64encode(encode_png_data(image)).decode("ascii")


def test_build_preview_image_draws_ensemble_openings_in_image_coordinates():
    image = np.full((100, 100, 3), 255, dtype=np.uint8)
    structure = {
        "source": "ensemble_local",
        "walls": [],
        "openings": [
            {
                "kind": "window",
                "position": {"x": 40.0, "y": 20.0},
                "span": 16.0,
                "orientation": "horizontal",
            }
        ],
        "structure_meta": {
            "image_size": {"width": 100, "height": 100},
        },
    }

    preview = build_preview_image(structure, image_b64=_png_data_uri(image))

    expected_region = preview[72:89, 32:49]
    mirrored_region = preview[12:29, 32:49]
    assert np.any(expected_region != 255)
    assert np.all(mirrored_region == 255)


def test_save_structure_artifacts_writes_opening_debug_entries_and_crops(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "ARTIFACT_DIR", tmp_path / "pointai_artifacts")
    artifacts.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    image = np.full((120, 120, 3), 255, dtype=np.uint8)
    image[40:80, 40:80] = 230
    opening_debug = [
        {
            "id": "door-1",
            "kind": "door",
            "raw": {
                "id": "door-1",
                "kind": "door",
                "position": {"x": 60.0, "y": 60.0},
                "span": 24.0,
                "orientation": "horizontal",
                "polygon": [[48.0, 55.0], [72.0, 55.0], [72.0, 70.0], [48.0, 70.0]],
            },
            "reanchored": {
                "id": "door-1",
                "kind": "door",
                "position": {"x": 60.0, "y": 60.0},
                "span": 24.0,
                "orientation": "horizontal",
                "wall_id": "wall-1",
            },
            "annotation": {
                "type": "door",
                "x1": 48.0,
                "y1": 60.0,
                "x2": 72.0,
                "y2": 60.0,
                "swing": "down",
            },
        }
    ]

    urls = save_structure_artifacts(
        request_id="req123",
        structure={"source": "ensemble_local", "walls": [], "openings": [], "structure_meta": {}},
        quality_metrics={"opening_count": 1},
        image_b64=_png_data_uri(image),
        auto_annotations=[opening_debug[0]["annotation"]],
        opening_debug=opening_debug,
    )

    debug_path = artifacts.ARTIFACT_DIR / "req123" / "openings_debug.json"
    payload = json.loads(debug_path.read_text(encoding="utf-8"))

    assert urls["openings_debug_url"] == "/artifacts/req123/openings_debug.json"
    assert payload["entries"][0]["id"] == "door-1"
    assert payload["entries"][0]["crop_url"] == "/artifacts/req123/opening_crops/door-1.png"
    crop_path = artifacts.ARTIFACT_DIR / "req123" / "opening_crops" / "door-1.png"
    assert crop_path.exists()
    crop = artifacts.cv2.imdecode(np.frombuffer(crop_path.read_bytes(), np.uint8), artifacts.cv2.IMREAD_COLOR)
    assert crop is not None
    assert crop.size > 0
    assert crop.shape[0] < image.shape[0]
