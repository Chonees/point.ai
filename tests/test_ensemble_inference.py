from __future__ import annotations

from copy import deepcopy

from backend.ensemble_inference import infer_ensemble
from tests.helpers import build_mitunet_infer_result


def _patch_models(monkeypatch, *, cubicasa_openings: list[dict]) -> None:
    mitunet_result = deepcopy(build_mitunet_infer_result())
    for wall in mitunet_result["walls"]:
        wall["polyline"] = [
            [float(point["x"]), float(point["y"])]
            for point in wall["polyline"]
        ]
    openings = deepcopy(cubicasa_openings)

    monkeypatch.setattr(
        "backend.ensemble_inference.infer_mitunet",
        lambda image_b64: deepcopy(mitunet_result),
    )
    monkeypatch.setattr(
        "backend.ensemble_inference.infer_cubicasa",
        lambda image_b64, model_variant=None: {
            "openings": deepcopy(openings),
            "walls": [],
            "inference_debug": {"backend": "cubicasa_local"},
        },
    )


def test_infer_ensemble_keeps_overlapping_doors_in_annotation_first_mode(monkeypatch):
    _patch_models(
        monkeypatch,
        cubicasa_openings=[
            {
                "id": "door-1",
                "kind": "door",
                "position": {"x": 110.0, "y": 74.0},
                "span": 28.0,
                "orientation": "vertical",
                "confidence": 0.9,
                "door_type": "normal",
                "swing": "left",
            },
            {
                "id": "door-2",
                "kind": "door",
                "position": {"x": 110.0, "y": 75.0},
                "span": 26.0,
                "orientation": "vertical",
                "confidence": 0.85,
                "door_type": "normal",
                "swing": "left",
            },
        ],
    )

    result = infer_ensemble("data:image/png;base64,AAAA")

    doors = [ann for ann in result["_auto_annotations"] if ann["type"] == "door"]
    assert len(doors) == 2
    assert all(door["swing"] == "left" for door in doors)


def test_infer_ensemble_keeps_dense_exterior_windows_in_annotation_first_mode(monkeypatch):
    _patch_models(
        monkeypatch,
        cubicasa_openings=[
            {
                "id": f"window-{index}",
                "kind": "window",
                "position": {"x": float(x), "y": 20.0},
                "span": 18.0,
                "orientation": "horizontal",
                "confidence": 0.9,
            }
            for index, x in enumerate([40, 70, 100, 130, 160], start=1)
        ],
    )

    result = infer_ensemble("data:image/png;base64,AAAA")

    windows = [ann for ann in result["_auto_annotations"] if ann["type"] == "window"]
    assert len(windows) == 5
    assert all(window["swing"] == "down" for window in windows)


def test_infer_ensemble_keeps_dense_interior_windows(monkeypatch):
    _patch_models(
        monkeypatch,
        cubicasa_openings=[
            {
                "id": f"window-{index}",
                "kind": "window",
                "position": {"x": 110.0, "y": float(y)},
                "span": 6.0,
                "orientation": "vertical",
                "confidence": 0.9,
            }
            for index, y in enumerate([60, 70, 80, 90, 100], start=1)
        ],
    )

    result = infer_ensemble("data:image/png;base64,AAAA")

    windows = [ann for ann in result["_auto_annotations"] if ann["type"] == "window"]
    assert len(windows) == 5
    assert all(window["swing"] == "right" for window in windows)


def test_infer_ensemble_reanchors_opening_by_nearest_wall_midpoint(monkeypatch):
    mitunet_result = deepcopy(build_mitunet_infer_result())
    mitunet_result["walls"] = [
        {
            "id": "wall-top-long",
            "orientation": "horizontal",
            "polyline": [[20.0, 20.0], [300.0, 20.0]],
            "thickness": 8.0,
            "is_exterior": True,
            "confidence": 0.95,
        },
        {
            "id": "wall-near-vertical",
            "orientation": "vertical",
            "polyline": [[250.0, 20.0], [250.0, 120.0]],
            "thickness": 8.0,
            "is_exterior": False,
            "confidence": 0.95,
        },
    ]

    monkeypatch.setattr(
        "backend.ensemble_inference.infer_mitunet",
        lambda image_b64: deepcopy(mitunet_result),
    )
    monkeypatch.setattr(
        "backend.ensemble_inference.infer_cubicasa",
        lambda image_b64, model_variant=None: {
            "openings": [
                {
                    "id": "window-1",
                    "kind": "window",
                    "position": {"x": 250.0, "y": 20.0},
                    "span": 24.0,
                    "orientation": "horizontal",
                    "confidence": 0.9,
                }
            ],
            "walls": [],
            "inference_debug": {"backend": "cubicasa_local"},
        },
    )

    result = infer_ensemble("data:image/png;base64,AAAA")

    assert result["openings"] == []
    assert len(result["_auto_annotations"]) == 1
    assert result["inference_debug"]["ensemble"]["reanchored_opening_count"] == 1


def test_infer_ensemble_falls_back_when_cubicasa_orientation_is_wrong(monkeypatch):
    mitunet_result = deepcopy(build_mitunet_infer_result())
    for wall in mitunet_result["walls"]:
        wall["polyline"] = [
            [float(point["x"]), float(point["y"])]
            for point in wall["polyline"]
        ]

    monkeypatch.setattr(
        "backend.ensemble_inference.infer_mitunet",
        lambda image_b64: deepcopy(mitunet_result),
    )
    monkeypatch.setattr(
        "backend.ensemble_inference.infer_cubicasa",
        lambda image_b64, model_variant=None: {
            "openings": [
                {
                    "id": "window-wrong-orientation",
                    "kind": "window",
                    "position": {"x": 151.0, "y": 20.0},
                    "span": 30.0,
                    "orientation": "vertical",
                    "confidence": 0.9,
                }
            ],
            "walls": [],
            "inference_debug": {"backend": "cubicasa_local"},
        },
    )

    result = infer_ensemble("data:image/png;base64,AAAA")

    assert result["openings"] == []
    assert [ann["type"] for ann in result["_auto_annotations"]] == ["window"]


def test_infer_ensemble_restores_annotation_first_openings_with_semantics(monkeypatch):
    _patch_models(
        monkeypatch,
        cubicasa_openings=[
            {
                "id": "door-no-swing",
                "kind": "door",
                "position": {"x": 110.0, "y": 74.0},
                "span": 28.0,
                "orientation": "vertical",
                "confidence": 0.9,
                "door_type": "normal",
                "swing": None,
            },
            {
                "id": "window-no-side",
                "kind": "window",
                "position": {"x": 151.0, "y": 20.0},
                "span": 30.0,
                "orientation": "horizontal",
                "confidence": 0.92,
            },
        ],
    )

    result = infer_ensemble("data:image/png;base64,AAAA")

    assert result["openings"] == []
    assert [ann["type"] for ann in result["_auto_annotations"]] == ["door", "window"]
    assert result["_auto_annotations"][0]["swing"] in {"left", "right"}
    assert result["_auto_annotations"][1]["swing"] in {"up", "down"}
