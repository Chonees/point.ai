"""Tests for the benchmark infrastructure."""
import json
from pathlib import Path

import cv2
import numpy as np

from backend.benchmark import (
    compare_structures,
    evaluate_result_against_thresholds,
    load_cases,
    run_benchmark,
    run_case,
)
from tests.helpers import build_manual_structure


def _write_synthetic_image(path: Path) -> None:
    image = np.full((160, 220, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (20, 20), (200, 28), (0, 0, 0), -1)
    cv2.rectangle(image, (20, 132), (200, 140), (0, 0, 0), -1)
    cv2.rectangle(image, (20, 20), (28, 140), (0, 0, 0), -1)
    cv2.rectangle(image, (192, 20), (200, 140), (0, 0, 0), -1)
    cv2.rectangle(image, (106, 28), (114, 132), (0, 0, 0), -1)
    cv2.rectangle(image, (106, 60), (114, 88), (0, 200, 0), -1)
    cv2.rectangle(image, (136, 20), (166, 28), (255, 0, 0), -1)
    cv2.imwrite(str(path), image)


def _create_test_dataset(tmp_path: Path) -> Path:
    case_dir = tmp_path / "simple_box"
    case_dir.mkdir()
    _write_synthetic_image(case_dir / "input.png")
    (case_dir / "expected.json").write_text(
        json.dumps(build_manual_structure(source="ground_truth"), indent=2),
        encoding="utf-8",
    )
    return tmp_path


def test_load_cases_finds_images(tmp_path):
    dataset = _create_test_dataset(tmp_path)
    cases = load_cases(dataset)

    assert len(cases) == 1
    assert cases[0].name == "simple_box"
    assert cases[0].has_ground_truth


def test_run_case_succeeds_and_populates_metrics(tmp_path, monkeypatch):
    dataset = _create_test_dataset(tmp_path)
    case = load_cases(dataset)[0]
    monkeypatch.setattr("backend.benchmark.infer_structure", lambda image_b64, backend=None: build_manual_structure(source="mock_inference"))

    result = run_case(case, backend="cubicasa_local")

    assert result.success is True
    assert result.elapsed_ms > 0
    assert result.structure is not None
    assert result.comparison["wall_footprint_iou"] == 1.0
    assert result.comparison["door_precision"] == 1.0
    assert result.comparison["window_recall"] == 1.0
    assert result.quality_metrics["quality_gate_passed"] is True


def test_compare_structures_includes_iou_and_opening_metrics():
    predicted = {
        "structure_meta": {"image_size": {"width": 220, "height": 160}},
        "walls": [
            {
                "id": "w1",
                "is_exterior": True,
                "thickness": 8,
                "polyline": [{"x": 20, "y": 24}, {"x": 200, "y": 24}],
            },
        ],
        "openings": [
            {"id": "o1", "kind": "door", "position": {"x": 110, "y": 74}, "span": 28},
            {"id": "o2", "kind": "window", "position": {"x": 151, "y": 24}, "span": 30},
        ],
    }
    expected = json.loads(json.dumps(predicted))

    result = compare_structures(predicted, expected)

    assert result["wall_footprint_iou"] == 1.0
    assert result["door_precision"] == 1.0
    assert result["door_recall"] == 1.0
    assert result["window_precision"] == 1.0
    assert result["window_recall"] == 1.0


def test_evaluate_result_against_thresholds_accepts_good_case(tmp_path, monkeypatch):
    dataset = _create_test_dataset(tmp_path)
    case = load_cases(dataset)[0]
    monkeypatch.setattr("backend.benchmark.infer_structure", lambda image_b64, backend=None: build_manual_structure(source="mock_inference"))
    result = run_case(case, backend="cubicasa_local")

    meets, failures = evaluate_result_against_thresholds(result, {
        "min_wall_count": 4,
        "min_exterior_wall_count": 4,
        "max_review_flags": 0,
        "min_opening_anchor_rate": 1.0,
        "min_junction_count": 4,
        "min_wall_iou": 0.95,
        "min_door_precision": 1.0,
        "min_door_recall": 1.0,
        "min_window_precision": 1.0,
        "min_window_recall": 1.0,
    })

    assert meets is True
    assert failures == []


def test_run_benchmark_evaluates_thresholds(tmp_path, monkeypatch):
    dataset = _create_test_dataset(tmp_path)
    monkeypatch.setattr("backend.benchmark.infer_structure", lambda image_b64, backend=None: build_manual_structure(source="mock_inference"))

    report = run_benchmark(dataset, backend="cubicasa_local")
    summary = report.summary()

    assert summary["total"] == 1
    assert summary["passed"] == 1
    assert summary["threshold_passed"] == 1
    assert report.results[0].meets_thresholds is True
