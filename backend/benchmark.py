"""
benchmark.py
Benchmark infrastructure for evaluating the v2 pipeline against Pointe plans.

Usage:
    python -m backend.benchmark --dataset data/benchmark --output data/benchmark_results

Stores per-run artifacts: structure JSON, preview PNG, quality metrics, comparison report.
"""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .artifacts import build_preview_image, encode_png_data
from .observability import log_event
from .plan_parser import parse_structure_payload
from .worker_client import infer_structure


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkCase:
    """A single benchmark test case."""
    name: str
    image_path: Path
    expected_path: Path | None = None

    @property
    def has_ground_truth(self) -> bool:
        return self.expected_path is not None and self.expected_path.exists()


@dataclass
class BenchmarkResult:
    """Result of running one benchmark case."""
    name: str
    success: bool
    elapsed_ms: float
    structure: dict[str, Any] | None = None
    quality_metrics: dict[str, Any] = field(default_factory=dict)
    review_flags: list[str] = field(default_factory=list)
    comparison: dict[str, Any] = field(default_factory=dict)
    meets_thresholds: bool | None = None
    threshold_failures: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class BenchmarkReport:
    """Aggregated report across all cases."""
    results: list[BenchmarkResult]
    thresholds: dict[str, float]

    @property
    def passed(self) -> list[BenchmarkResult]:
        return [result for result in self.results if result.success]

    @property
    def failed(self) -> list[BenchmarkResult]:
        return [result for result in self.results if not result.success]

    @property
    def threshold_passed(self) -> list[BenchmarkResult]:
        return [result for result in self.results if result.meets_thresholds is True]

    @property
    def threshold_failed(self) -> list[BenchmarkResult]:
        return [result for result in self.results if result.meets_thresholds is False]

    def summary(self) -> dict[str, Any]:
        total = len(self.results)
        return {
            "total": total,
            "passed": len(self.passed),
            "failed": len(self.failed),
            "pass_rate": len(self.passed) / total if total > 0 else 0.0,
            "threshold_passed": len(self.threshold_passed),
            "threshold_failed": len(self.threshold_failed),
            "threshold_pass_rate": len(self.threshold_passed) / total if total > 0 else 0.0,
            "avg_elapsed_ms": sum(result.elapsed_ms for result in self.results) / total if total > 0 else 0.0,
            "thresholds": self.thresholds,
        }


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS = {
    "min_wall_count": 4,
    "min_exterior_wall_count": 3,
    "max_review_flags": 5,
    "min_opening_anchor_rate": 0.75,
    "min_junction_count": 3,
    "min_wall_iou": 0.85,
    "min_door_precision": 0.80,
    "min_door_recall": 0.75,
    "min_window_precision": 0.80,
    "min_window_recall": 0.75,
}


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------

def load_cases(dataset_dir: str | Path) -> list[BenchmarkCase]:
    dataset_path = Path(dataset_dir)
    cases = []

    if not dataset_path.exists():
        return cases

    for case_dir in sorted(dataset_path.iterdir()):
        if not case_dir.is_dir():
            continue

        image_path = None
        for ext in (".png", ".jpg", ".jpeg"):
            candidate = case_dir / f"input{ext}"
            if candidate.exists():
                image_path = candidate
                break

        if image_path is None:
            continue

        expected_path = case_dir / "expected.json"
        cases.append(
            BenchmarkCase(
                name=case_dir.name,
                image_path=image_path,
                expected_path=expected_path if expected_path.exists() else None,
            )
        )

    return cases


def run_case(
    case: BenchmarkCase,
    *,
    backend: str | None = None,
    thresholds: dict[str, float] | None = None,
) -> BenchmarkResult:
    try:
        image_b64 = "data:image/png;base64," + base64.b64encode(case.image_path.read_bytes()).decode("ascii")
    except Exception as exc:
        return BenchmarkResult(
            name=case.name,
            success=False,
            elapsed_ms=0.0,
            error=f"Failed to read image: {exc}",
        )

    t0 = time.perf_counter()
    try:
        inferred = infer_structure(image_b64, backend=backend)
        parsed = parse_structure_payload(structure=inferred)
    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000.0
        log_event("benchmark.case.failed", case=case.name, error=str(exc))
        return BenchmarkResult(
            name=case.name,
            success=False,
            elapsed_ms=elapsed,
            error=f"Pipeline error: {exc}",
        )
    elapsed = (time.perf_counter() - t0) * 1000.0

    structure = parsed["structure"]
    comparison = {}
    if case.has_ground_truth:
        expected = json.loads(case.expected_path.read_text(encoding="utf-8"))
        comparison = compare_structures(structure, expected)

    result = BenchmarkResult(
        name=case.name,
        success=True,
        elapsed_ms=elapsed,
        structure=structure,
        quality_metrics=parsed["quality_metrics"],
        review_flags=parsed["review_flags"],
        comparison=comparison,
    )

    if thresholds is not None:
        result.meets_thresholds, result.threshold_failures = evaluate_result_against_thresholds(result, thresholds)

    log_event(
        "benchmark.case.completed",
        case=case.name,
        success=result.success,
        meets_thresholds=result.meets_thresholds,
        elapsed_ms=round(result.elapsed_ms, 2),
    )
    return result


def run_benchmark(
    dataset_dir: str | Path,
    *,
    output_dir: str | Path | None = None,
    backend: str | None = None,
    thresholds: dict[str, float] | None = None,
) -> BenchmarkReport:
    effective_thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    cases = load_cases(dataset_dir)
    results = [run_case(case, backend=backend, thresholds=effective_thresholds) for case in cases]

    report = BenchmarkReport(results=results, thresholds=effective_thresholds)
    if output_dir:
        _save_report(report, Path(output_dir))
    return report


def evaluate_result_against_thresholds(
    result: BenchmarkResult,
    thresholds: dict[str, float],
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not result.success:
        failures.append("pipeline_success=false")
        return False, failures

    quality = result.quality_metrics
    if quality.get("quality_gate_passed") is False:
        failures.append("quality_gate_failed")
    if quality.get("wall_count", 0) < thresholds["min_wall_count"]:
        failures.append(f"wall_count<{thresholds['min_wall_count']}")
    if quality.get("exterior_wall_count", 0) < thresholds["min_exterior_wall_count"]:
        failures.append(f"exterior_wall_count<{thresholds['min_exterior_wall_count']}")
    if len(result.review_flags) > thresholds["max_review_flags"]:
        failures.append(f"review_flags>{thresholds['max_review_flags']}")
    if quality.get("junction_count", 0) < thresholds["min_junction_count"]:
        failures.append(f"junction_count<{thresholds['min_junction_count']}")

    raw_openings = quality.get("raw_opening_count", quality.get("opening_count", 0))
    anchored_openings = quality.get("anchored_opening_count", quality.get("opening_count", 0))
    anchor_rate = anchored_openings / raw_openings if raw_openings else 1.0
    if anchor_rate < thresholds["min_opening_anchor_rate"]:
        failures.append(f"opening_anchor_rate<{thresholds['min_opening_anchor_rate']}")

    comparison = result.comparison
    if "wall_footprint_iou" in comparison and comparison["wall_footprint_iou"] is not None:
        if comparison["wall_footprint_iou"] < thresholds["min_wall_iou"]:
            failures.append(f"wall_footprint_iou<{thresholds['min_wall_iou']}")

    if comparison.get("door_count_expected", 0) > 0:
        if comparison.get("door_precision", 0.0) < thresholds["min_door_precision"]:
            failures.append(f"door_precision<{thresholds['min_door_precision']}")
        if comparison.get("door_recall", 0.0) < thresholds["min_door_recall"]:
            failures.append(f"door_recall<{thresholds['min_door_recall']}")

    if comparison.get("window_count_expected", 0) > 0:
        if comparison.get("window_precision", 0.0) < thresholds["min_window_precision"]:
            failures.append(f"window_precision<{thresholds['min_window_precision']}")
        if comparison.get("window_recall", 0.0) < thresholds["min_window_recall"]:
            failures.append(f"window_recall<{thresholds['min_window_recall']}")

    return len(failures) == 0, failures


def _save_report(report: BenchmarkReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(report.summary(), indent=2), encoding="utf-8")

    for result in report.results:
        case_dir = output_dir / result.name
        case_dir.mkdir(parents=True, exist_ok=True)

        result_data = {
            "name": result.name,
            "success": result.success,
            "meets_thresholds": result.meets_thresholds,
            "threshold_failures": result.threshold_failures,
            "elapsed_ms": result.elapsed_ms,
            "quality_metrics": result.quality_metrics,
            "review_flags": result.review_flags,
            "comparison": result.comparison,
            "error": result.error,
        }
        (case_dir / "result.json").write_text(json.dumps(result_data, indent=2), encoding="utf-8")

        if result.structure:
            (case_dir / "structure.json").write_text(json.dumps(result.structure, indent=2), encoding="utf-8")
            try:
                preview = build_preview_image(result.structure)
                (case_dir / "preview.png").write_bytes(encode_png_data(preview))
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Structure comparison
# ---------------------------------------------------------------------------

def compare_structures(predicted: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    pred_walls = predicted.get("walls", [])
    exp_walls = expected.get("walls", [])
    pred_openings = predicted.get("openings", [])
    exp_openings = expected.get("openings", [])

    pred_ext = sum(1 for wall in pred_walls if wall.get("is_exterior"))
    exp_ext = sum(1 for wall in exp_walls if wall.get("is_exterior"))

    door_metrics = _opening_match_metrics(pred_openings, exp_openings, kind="door")
    window_metrics = _opening_match_metrics(pred_openings, exp_openings, kind="window")

    return {
        "wall_count_predicted": len(pred_walls),
        "wall_count_expected": len(exp_walls),
        "wall_count_diff": len(pred_walls) - len(exp_walls),
        "exterior_wall_predicted": pred_ext,
        "exterior_wall_expected": exp_ext,
        "door_count_predicted": door_metrics["predicted"],
        "door_count_expected": door_metrics["expected"],
        "window_count_predicted": window_metrics["predicted"],
        "window_count_expected": window_metrics["expected"],
        "opening_count_diff": len(pred_openings) - len(exp_openings),
        "wall_footprint_iou": _wall_footprint_iou(predicted, expected),
        "door_precision": door_metrics["precision"],
        "door_recall": door_metrics["recall"],
        "window_precision": window_metrics["precision"],
        "window_recall": window_metrics["recall"],
    }


def _wall_footprint_iou(predicted: dict[str, Any], expected: dict[str, Any]) -> float | None:
    pred_mask, exp_mask = _rasterize_wall_masks(predicted, expected)
    union = np.logical_or(pred_mask, exp_mask).sum()
    if union == 0:
        return None
    intersection = np.logical_and(pred_mask, exp_mask).sum()
    return float(intersection / union)


def _rasterize_wall_masks(predicted: dict[str, Any], expected: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    bounds = _comparison_bounds(predicted, expected)
    width = max(64, int(round(bounds["max_x"] - bounds["min_x"] + 40)))
    height = max(64, int(round(bounds["max_y"] - bounds["min_y"] + 40)))
    offset_x = 20 - bounds["min_x"]
    offset_y = 20 - bounds["min_y"]

    pred_mask = np.zeros((height, width), dtype=np.uint8)
    exp_mask = np.zeros((height, width), dtype=np.uint8)
    _draw_walls_to_mask(pred_mask, predicted.get("walls", []), offset_x, offset_y)
    _draw_walls_to_mask(exp_mask, expected.get("walls", []), offset_x, offset_y)
    return pred_mask > 0, exp_mask > 0


def _draw_walls_to_mask(mask: np.ndarray, walls: list[dict[str, Any]], offset_x: float, offset_y: float) -> None:
    for wall in walls:
        points = wall.get("polyline") or []
        if len(points) != 2:
            continue
        start = points[0]
        end = points[1]
        thickness = max(1, int(round(float(wall.get("thickness", 4.0)))))
        cv2.line(
            mask,
            (int(round(float(start["x"]) + offset_x)), int(round(float(start["y"]) + offset_y))),
            (int(round(float(end["x"]) + offset_x)), int(round(float(end["y"]) + offset_y))),
            255,
            thickness,
        )


def _comparison_bounds(predicted: dict[str, Any], expected: dict[str, Any]) -> dict[str, float]:
    image_size = predicted.get("structure_meta", {}).get("image_size") or expected.get("structure_meta", {}).get("image_size")
    if image_size:
        return {"min_x": 0.0, "min_y": 0.0, "max_x": float(image_size["width"]), "max_y": float(image_size["height"])}

    points = []
    for structure in (predicted, expected):
        for wall in structure.get("walls", []):
            points.extend(wall.get("polyline", []))

    if not points:
        return {"min_x": 0.0, "min_y": 0.0, "max_x": 512.0, "max_y": 512.0}

    return {
        "min_x": min(float(point["x"]) for point in points),
        "min_y": min(float(point["y"]) for point in points),
        "max_x": max(float(point["x"]) for point in points),
        "max_y": max(float(point["y"]) for point in points),
    }


def _opening_match_metrics(
    predicted: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    *,
    kind: str,
) -> dict[str, float | int]:
    predicted_kind = [opening for opening in predicted if opening.get("kind") == kind]
    expected_kind = [opening for opening in expected if opening.get("kind") == kind]

    used_expected: set[int] = set()
    matches = 0
    for pred in predicted_kind:
        best_index = None
        best_score = None
        for index, exp in enumerate(expected_kind):
            if index in used_expected:
                continue
            score = _opening_match_score(pred, exp)
            if score is None:
                continue
            if best_score is None or score < best_score:
                best_index = index
                best_score = score
        if best_index is not None:
            used_expected.add(best_index)
            matches += 1

    precision = matches / len(predicted_kind) if predicted_kind else (1.0 if not expected_kind else 0.0)
    recall = matches / len(expected_kind) if expected_kind else (1.0 if not predicted_kind else 0.0)

    return {
        "predicted": len(predicted_kind),
        "expected": len(expected_kind),
        "matches": matches,
        "precision": precision,
        "recall": recall,
    }


def _opening_match_score(predicted: dict[str, Any], expected: dict[str, Any]) -> float | None:
    pred_pos = predicted.get("position")
    exp_pos = expected.get("position")
    if not pred_pos or not exp_pos:
        return None

    dx = float(pred_pos["x"]) - float(exp_pos["x"])
    dy = float(pred_pos["y"]) - float(exp_pos["y"])
    distance = (dx * dx + dy * dy) ** 0.5

    pred_span = float(predicted.get("span", 0))
    exp_span = float(expected.get("span", 0))
    if pred_span <= 0 or exp_span <= 0:
        return None

    span_error = abs(pred_span - exp_span) / max(pred_span, exp_span)
    max_distance = max(12.0, max(pred_span, exp_span) * 0.75)
    if distance > max_distance or span_error > 0.5:
        return None
    return distance + (span_error * 10.0)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Point.ai Benchmark Runner")
    parser.add_argument("--dataset", required=True, help="Path to benchmark dataset directory")
    parser.add_argument("--output", default=None, help="Path to save benchmark results")
    parser.add_argument("--backend", default=None, help="Inference backend override")
    args = parser.parse_args()

    report = run_benchmark(args.dataset, output_dir=args.output, backend=args.backend)
    summary = report.summary()

    print(f"\nBenchmark complete: {summary['total']} cases")
    print(f"  Passed: {summary['passed']}")
    print(f"  Failed: {summary['failed']}")
    print(f"  Threshold passed: {summary['threshold_passed']}")
    print(f"  Threshold failed: {summary['threshold_failed']}")
    print(f"  Avg time: {summary['avg_elapsed_ms']:.0f}ms")

    if report.failed:
        print("\nFailed cases:")
        for result in report.failed:
            print(f"  - {result.name}: {result.error}")


if __name__ == "__main__":
    main()
