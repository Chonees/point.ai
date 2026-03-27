"""Tests for the benchmark infrastructure."""
import copy
import json
from pathlib import Path

import cv2
import numpy as np

from backend.benchmark import (
    BenchmarkResult,
    compare_structures,
    evaluate_result_against_thresholds,
    load_cases,
    run_benchmark,
    run_case,
)
from backend.image_utils import decode_image
from tests.helpers import build_manual_structure, build_mitunet_infer_result


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


def _create_disk_ground_truth_dataset(tmp_path: Path) -> Path:
    case_dir = tmp_path / "0001"
    case_dir.mkdir()
    _write_synthetic_image(case_dir / "original.png")

    room = np.zeros((160, 220), dtype=np.uint8)
    icon = np.zeros((160, 220), dtype=np.uint8)

    cv2.line(room, (20, 20), (200, 20), 2, 8)
    cv2.line(room, (20, 140), (200, 140), 2, 8)
    cv2.line(room, (20, 20), (20, 140), 2, 8)
    cv2.line(room, (200, 20), (200, 140), 2, 8)
    cv2.line(room, (110, 20), (110, 140), 2, 8)

    cv2.rectangle(icon, (106, 60), (114, 88), 2, -1)
    cv2.rectangle(icon, (136, 20), (166, 28), 1, -1)

    np.save(case_dir / "label.npy", np.stack([room, icon], axis=0))
    heatmaps = {
        "0": [[20, 20], [200, 20], [20, 140], [200, 140]],
        "1": [[110, 20], [110, 140]],
        "2": [],
    }
    (case_dir / "heatmaps.json").write_text(json.dumps(heatmaps), encoding="utf-8")
    return tmp_path


def _scale_manual_structure_for_input(
    image_b64: str,
    *,
    source: str = "mock_inference",
    with_openings: bool = True,
) -> dict:
    image = decode_image(image_b64)
    height, width = image.shape[:2]
    structure = copy.deepcopy(build_manual_structure(source=source, with_openings=with_openings))
    base_size = structure["structure_meta"]["image_size"]
    scale_x = width / float(base_size["width"])
    scale_y = height / float(base_size["height"])

    for wall in structure["walls"]:
        for point in wall["polyline"]:
            point["x"] *= scale_x
            point["y"] *= scale_y
        wall["thickness"] *= (scale_x + scale_y) / 2.0

    for opening in structure["openings"]:
        opening["position"]["x"] *= scale_x
        opening["position"]["y"] *= scale_y
        opening["span"] *= (scale_x + scale_y) / 2.0

    structure["structure_meta"]["image_size"] = {"width": width, "height": height}
    return structure


def test_load_cases_finds_images(tmp_path):
    dataset = _create_test_dataset(tmp_path)
    cases = load_cases(dataset)

    assert len(cases) == 1
    assert cases[0].name == "simple_box"
    assert cases[0].has_ground_truth


def test_load_cases_supports_pointai_disk_dataset(tmp_path):
    dataset = _create_disk_ground_truth_dataset(tmp_path)

    cases = load_cases(dataset)

    assert len(cases) == 1
    assert cases[0].name == "0001"
    assert cases[0].ground_truth_kind == "segmentation"


def test_run_case_succeeds_and_populates_metrics(tmp_path, monkeypatch):
    dataset = _create_test_dataset(tmp_path)
    case = load_cases(dataset)[0]
    monkeypatch.setattr(
        "backend.benchmark.infer_structure",
        lambda image_b64, backend=None: _scale_manual_structure_for_input(image_b64, source="mock_inference"),
    )

    result = run_case(case, backend="cubicasa_local")

    assert result.success is True
    assert result.elapsed_ms > 0
    assert result.structure is not None
    assert result.input_normalization["applied"] is True
    assert result.input_normalization["profile"] == "low_res_upscaled"
    assert result.raw_model is not None
    assert result.comparison["benchmark_scope"] == "geometry_only"
    assert result.comparison["wall_footprint_iou"] == 1.0
    assert result.stage_comparison["raw_model_vs_ground_truth"]["wall_footprint_iou"] == 1.0
    assert result.stage_comparison["postprocess_vs_ground_truth"]["wall_footprint_iou"] == 1.0
    assert result.render_plan is not None
    assert len(result.render_plan["wall_lines"]) >= 2
    assert result.dxf_bytes is not None
    assert len(result.dxf_wall_entities) >= 2
    assert "door_precision" not in result.comparison
    assert "window_recall" not in result.comparison
    assert result.quality_metrics["quality_gate_passed"] is True
    assert result.structure["structure_meta"]["image_size"] == {"width": 220, "height": 160}


def test_compare_structures_includes_geometry_metrics_only():
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

    assert result["benchmark_scope"] == "geometry_only"
    assert result["wall_footprint_iou"] == 1.0
    assert "door_precision" not in result
    assert "door_recall" not in result
    assert "window_precision" not in result
    assert "window_recall" not in result


def test_evaluate_result_against_thresholds_accepts_good_case(tmp_path, monkeypatch):
    dataset = _create_test_dataset(tmp_path)
    case = load_cases(dataset)[0]
    monkeypatch.setattr(
        "backend.benchmark.infer_structure",
        lambda image_b64, backend=None: _scale_manual_structure_for_input(image_b64, source="mock_inference"),
    )
    result = run_case(case, backend="cubicasa_local")

    meets, failures = evaluate_result_against_thresholds(result, {
        "min_wall_count": 4,
        "min_exterior_wall_count": 4,
        "max_review_flags": 0,
        "min_junction_count": 4,
        "min_wall_iou": 0.95,
    })

    assert meets is True
    assert failures == []


def test_evaluate_result_against_thresholds_ignores_opening_review_flags():
    result = BenchmarkResult(
        name="geometry-only",
        success=True,
        elapsed_ms=10.0,
        quality_metrics={
            "quality_gate_passed": True,
            "wall_count": 8,
            "exterior_wall_count": 4,
            "junction_count": 5,
        },
        review_flags=[
            "Filtered opening raw-opening-0001: opening span does not fit wall wall-0001.",
            "Removed 14 furniture-like opening(s).",
        ],
        comparison={
            "benchmark_scope": "geometry_only",
            "wall_footprint_iou": 0.95,
            "exterior_shell_recall": 0.9,
            "junction_precision": 0.9,
            "junction_recall": 0.9,
        },
    )

    meets, failures = evaluate_result_against_thresholds(result, {"max_review_flags": 0})

    assert meets is True
    assert failures == []


def test_run_benchmark_evaluates_thresholds(tmp_path, monkeypatch):
    dataset = _create_test_dataset(tmp_path)
    monkeypatch.setattr(
        "backend.benchmark.infer_structure",
        lambda image_b64, backend=None: _scale_manual_structure_for_input(image_b64, source="mock_inference"),
    )

    report = run_benchmark(dataset, backend="cubicasa_local")
    summary = report.summary()

    assert summary["total"] == 1
    assert summary["passed"] == 1
    assert summary["threshold_passed"] == 1
    assert report.results[0].meets_thresholds is True


def test_run_benchmark_writes_comparison_artifacts(tmp_path, monkeypatch):
    dataset_root = tmp_path / "dataset"
    dataset_root.mkdir()
    dataset = _create_test_dataset(dataset_root)
    output_dir = tmp_path / "out"
    monkeypatch.setattr(
        "backend.benchmark.infer_structure",
        lambda image_b64, backend=None: _scale_manual_structure_for_input(image_b64, source="mock_inference"),
    )

    run_benchmark(dataset, backend="cubicasa_local", output_dir=output_dir)

    case_dir = output_dir / "simple_box"
    assert (case_dir / "original.png").exists()
    assert (case_dir / "inference_input.png").exists()
    assert (case_dir / "raw_model.json").exists()
    assert (case_dir / "postprocess.json").exists()
    assert (case_dir / "render_plan.json").exists()
    assert (case_dir / "output.dxf").exists()
    assert (case_dir / "raw_model_preview.png").exists()
    assert (case_dir / "postprocess_preview.png").exists()
    assert (case_dir / "render_plan_preview.png").exists()
    assert (case_dir / "dxf_preview.png").exists()
    assert (case_dir / "preview.png").exists()
    assert (case_dir / "comparison.png").exists()

    original = cv2.imread(str(case_dir / "original.png"))
    inference_input = cv2.imread(str(case_dir / "inference_input.png"))
    raw_model_preview = cv2.imread(str(case_dir / "raw_model_preview.png"))
    dxf_preview = cv2.imread(str(case_dir / "dxf_preview.png"))
    preview = cv2.imread(str(case_dir / "preview.png"))
    result_json = json.loads((case_dir / "result.json").read_text(encoding="utf-8"))

    assert original is not None
    assert inference_input is not None
    assert raw_model_preview is not None
    assert dxf_preview is not None
    assert preview is not None
    assert inference_input.shape[0] > original.shape[0]
    assert preview.shape[1] > raw_model_preview.shape[1]
    assert preview.shape[0] >= raw_model_preview.shape[0]
    assert "stage_comparison" in result_json
    assert "dxf_vs_ground_truth" in result_json["stage_comparison"]
    assert result_json["artifact_files"]["dxf_preview"] == "dxf_preview.png"


def test_run_case_supports_segmentation_ground_truth_dataset(tmp_path, monkeypatch):
    dataset = _create_disk_ground_truth_dataset(tmp_path)
    case = load_cases(dataset)[0]
    monkeypatch.setattr(
        "backend.benchmark.infer_structure",
        lambda image_b64, backend=None: _scale_manual_structure_for_input(image_b64, source="mock_inference"),
    )

    result = run_case(case, backend="heuristic_local")

    assert result.success is True
    assert result.input_normalization["applied"] is True
    assert result.comparison["benchmark_scope"] == "geometry_only"
    assert result.comparison["ground_truth_kind"] == "segmentation"
    assert result.comparison["wall_footprint_iou"] > 0.75
    assert result.comparison["exterior_shell_recall"] > 0.5
    assert "dxf_vs_ground_truth" in result.stage_comparison
    assert "door_precision" not in result.comparison
    assert "window_precision" not in result.comparison


def test_run_case_tracks_region_plan_for_mitunet(tmp_path, monkeypatch):
    dataset = _create_test_dataset(tmp_path)
    case = load_cases(dataset)[0]
    monkeypatch.setattr(
        "backend.benchmark.infer_structure",
        lambda image_b64, backend=None: build_mitunet_infer_result(),
    )

    result = run_case(case, backend="mitunet_local")

    assert result.success is True
    assert result.region_plan is not None
    assert result.quality_metrics["benchmark_dxf_mode"] == "mask_regions"
    assert result.region_plan["meta"]["region_count"] > 0
    assert result.region_plan["meta"]["max_wall_thickness"] == 6.0
    assert all(region["draw_thickness"] <= 6.0 for region in result.region_plan["regions"])
    assert "region_plan_to_dxf" in result.stage_comparison
    assert len(result.dxf_wall_entities) > 0
