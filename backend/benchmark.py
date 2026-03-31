"""
Benchmark infrastructure for evaluating the v2 pipeline.
"""
from __future__ import annotations

import base64
import copy
import tempfile
import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import ezdxf
import numpy as np

from .artifacts import build_preview_image, encode_png_data
from .image_utils import decode_image
from .mitunet_inference import (
    MITUNET_BACKEND,
    _prepare_mitunet_wall_mask_for_regions,
    build_mitunet_region_plan,
    generate_mitunet_region_dxf,
)
from .observability import log_event
from .plan_parser import parse_structure_payload
from .provenance import build_code_provenance, utc_now_iso
from .structural_generator import build_render_plan, generate as generate_structural
from .structure_postprocess import build_junction_graph
from .worker_client import infer_structure

_GROUND_TRUTH_CONTRACT = "contract"
_GROUND_TRUTH_SEGMENTATION = "segmentation"
_GROUND_TRUTH_NONE = "none"
_HEATMAP_CHANNEL_TO_JUNCTION = {"0": "L", "1": "T", "2": "X"}
_JUNCTION_MATCH_TOLERANCE = 12.0
_BENCHMARK_MIN_SHORT_SIDE = 512
_GEOMETRY_SCALE_X_KEYS = {"x", "width", "w", "left", "right"}
_GEOMETRY_SCALE_Y_KEYS = {"y", "height", "h", "top", "bottom"}
_GEOMETRY_SCALE_UNIFORM_KEYS = {"thickness", "span", "offset", "length", "radius"}


@dataclass
class BenchmarkCase:
    name: str
    image_path: Path
    expected_path: Path | None = None
    label_path: Path | None = None
    heatmaps_path: Path | None = None

    @property
    def ground_truth_kind(self) -> str:
        if self.expected_path is not None and self.expected_path.exists():
            return _GROUND_TRUTH_CONTRACT
        if self.label_path is not None and self.label_path.exists() and self.heatmaps_path is not None and self.heatmaps_path.exists():
            return _GROUND_TRUTH_SEGMENTATION
        return _GROUND_TRUTH_NONE

    @property
    def has_ground_truth(self) -> bool:
        return self.ground_truth_kind != _GROUND_TRUTH_NONE


@dataclass
class BenchmarkResult:
    name: str
    success: bool
    elapsed_ms: float
    source_image_path: str | None = None
    source_image_b64: str | None = None
    inference_image_b64: str | None = None
    input_normalization: dict[str, Any] = field(default_factory=dict)
    raw_model: dict[str, Any] | None = None
    structure: dict[str, Any] | None = None
    render_plan: dict[str, Any] | None = None
    region_plan: dict[str, Any] | None = None
    quality_metrics: dict[str, Any] = field(default_factory=dict)
    review_flags: list[str] = field(default_factory=list)
    needs_review: bool = False
    comparison: dict[str, Any] = field(default_factory=dict)
    stage_comparison: dict[str, Any] = field(default_factory=dict)
    dxf_bytes: bytes | None = None
    dxf_wall_entities: list[dict[str, Any]] = field(default_factory=list)
    meets_thresholds: bool | None = None
    threshold_failures: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class BenchmarkReport:
    results: list[BenchmarkResult]
    thresholds: dict[str, float]
    metadata: dict[str, Any] = field(default_factory=dict)

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
        normalized_case_count = sum(1 for result in self.results if result.input_normalization.get("applied"))
        return {
            "total": total,
            "passed": len(self.passed),
            "failed": len(self.failed),
            "pass_rate": len(self.passed) / total if total > 0 else 0.0,
            "threshold_passed": len(self.threshold_passed),
            "threshold_failed": len(self.threshold_failed),
            "threshold_pass_rate": len(self.threshold_passed) / total if total > 0 else 0.0,
            "review_rate": sum(1 for result in self.results if result.needs_review) / total if total > 0 else 0.0,
            "avg_elapsed_ms": sum(result.elapsed_ms for result in self.results) / total if total > 0 else 0.0,
            "normalized_case_count": normalized_case_count,
            "native_case_count": total - normalized_case_count,
            "thresholds": self.thresholds,
        }


DEFAULT_THRESHOLDS = {
    "min_wall_count": 4,
    "min_exterior_wall_count": 3,
    "max_review_flags": 5,
    "min_junction_count": 3,
    "min_wall_iou": 0.85,
    "min_exterior_shell_recall": 0.70,
    "min_junction_precision": 0.50,
    "min_junction_recall": 0.50,
}


def load_cases(dataset_dir: str | Path, *, limit: int | None = None) -> list[BenchmarkCase]:
    dataset_path = Path(dataset_dir)
    cases: list[BenchmarkCase] = []
    if not dataset_path.exists():
        return cases

    for case_dir in sorted(dataset_path.iterdir()):
        if not case_dir.is_dir():
            continue

        contract_image = _first_existing(case_dir, ("input.png", "input.jpg", "input.jpeg"))
        contract_expected = case_dir / "expected.json"
        segmentation_image = _first_existing(case_dir, ("original.png", "original.jpg", "original.jpeg"))
        label_path = case_dir / "label.npy"
        heatmaps_path = case_dir / "heatmaps.json"

        if contract_image is not None:
            cases.append(
                BenchmarkCase(
                    name=case_dir.name,
                    image_path=contract_image,
                    expected_path=contract_expected if contract_expected.exists() else None,
                )
            )
        elif segmentation_image is not None and label_path.exists() and heatmaps_path.exists():
            cases.append(
                BenchmarkCase(
                    name=case_dir.name,
                    image_path=segmentation_image,
                    label_path=label_path,
                    heatmaps_path=heatmaps_path,
                )
            )

        if limit is not None and len(cases) >= limit:
            break

    return cases


def run_case(
    case: BenchmarkCase,
    *,
    backend: str | None = None,
    thresholds: dict[str, float] | None = None,
) -> BenchmarkResult:
    try:
        original_image_b64 = _image_data_uri(case.image_path)
        original_image = decode_image(original_image_b64)
        inference_image, input_normalization = _normalize_image_for_benchmark(original_image)
        inference_image_b64 = original_image_b64 if not input_normalization.get("applied") else _png_data_uri(inference_image)
    except Exception as exc:
        return BenchmarkResult(name=case.name, success=False, elapsed_ms=0.0, error=f"Failed to read image: {exc}")

    t0 = time.perf_counter()
    try:
        inferred = infer_structure(inference_image_b64, backend=backend)
        parsed = parse_structure_payload(structure=inferred)
    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000.0
        log_event("benchmark.case.failed", case=case.name, error=str(exc))
        return BenchmarkResult(name=case.name, success=False, elapsed_ms=elapsed, error=f"Pipeline error: {exc}")
    elapsed = (time.perf_counter() - t0) * 1000.0

    raw_model = inferred
    if input_normalization.get("applied"):
        raw_model = _rescale_structure_to_original_space(raw_model, input_normalization)

    structure = parsed["structure"]
    if input_normalization.get("applied"):
        structure = _rescale_structure_to_original_space(structure, input_normalization)

    raw_model_geometry = _structure_for_geometry_benchmark(raw_model)
    structure_geometry = _structure_for_geometry_benchmark(structure)
    region_plan = None

    try:
        render_plan = build_render_plan(structure_geometry)
        if raw_model.get("source") == MITUNET_BACKEND and "_wall_mask" in raw_model:
            region_plan = build_mitunet_region_plan(raw_model)
            dxf_bytes, dxf_wall_entities = _generate_mitunet_region_dxf_wall_artifacts(region_plan)
        else:
            dxf_bytes, dxf_wall_entities = _generate_dxf_wall_artifacts(structure_geometry)
    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000.0
        log_event("benchmark.case.failed", case=case.name, error=f"DXF generation failed: {exc}")
        return BenchmarkResult(name=case.name, success=False, elapsed_ms=elapsed, error=f"DXF generation failed: {exc}")

    quality_metrics = {
        **parsed["quality_metrics"],
        "benchmark_input_profile": input_normalization["profile"],
        "benchmark_normalization_applied": bool(input_normalization.get("applied")),
        "benchmark_original_image_size": input_normalization["original_size"],
        "benchmark_inference_image_size": input_normalization["inference_size"],
        "benchmark_dxf_mode": "mask_regions" if region_plan is not None else "structural",
    }
    if input_normalization.get("applied"):
        quality_metrics["benchmark_input_scale"] = input_normalization["scale"]

    ground_truth = _load_case_ground_truth(case) if case.has_ground_truth else None
    comparison = _compare_stage_structure_to_ground_truth(structure_geometry, case, ground_truth)
    stage_comparison = _build_stage_comparison(
        case=case,
        ground_truth=ground_truth,
        raw_model=raw_model_geometry,
        postprocess=structure_geometry,
        render_plan=render_plan,
        region_plan=region_plan,
        dxf_wall_entities=dxf_wall_entities,
    )

    result = BenchmarkResult(
        name=case.name,
        success=True,
        elapsed_ms=elapsed,
        source_image_path=str(case.image_path),
        source_image_b64=original_image_b64,
        inference_image_b64=inference_image_b64,
        input_normalization=input_normalization,
        raw_model=raw_model,
        structure=structure,
        render_plan=render_plan,
        region_plan=region_plan,
        quality_metrics=quality_metrics,
        review_flags=parsed["review_flags"],
        needs_review=bool(parsed.get("needs_review", False)),
        comparison=comparison,
        stage_comparison=stage_comparison,
        dxf_bytes=dxf_bytes,
        dxf_wall_entities=dxf_wall_entities,
    )

    if thresholds is not None:
        result.meets_thresholds, result.threshold_failures = evaluate_result_against_thresholds(result, thresholds)

    log_event(
        "benchmark.case.completed",
        case=case.name,
        success=result.success,
        meets_thresholds=result.meets_thresholds,
        elapsed_ms=round(result.elapsed_ms, 2),
        ground_truth_kind=case.ground_truth_kind,
    )
    return result


def run_benchmark(
    dataset_dir: str | Path,
    *,
    output_dir: str | Path | None = None,
    backend: str | None = None,
    thresholds: dict[str, float] | None = None,
    limit: int | None = None,
    is_baseline: bool = False,
) -> BenchmarkReport:
    effective_thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    cases = load_cases(dataset_dir, limit=limit)
    results = [run_case(case, backend=backend, thresholds=effective_thresholds) for case in cases]
    inference_provenance = None
    for result in results:
        region_meta = (result.region_plan or {}).get("meta") or {}
        if region_meta.get("provenance"):
            inference_provenance = region_meta["provenance"]
            break
    report = BenchmarkReport(
        results=results,
        thresholds=effective_thresholds,
        metadata={
            "captured_at_utc": utc_now_iso(),
            "dataset_dir": str(Path(dataset_dir).resolve()),
            "backend": backend,
            "limit": limit,
            "output_dir": str(Path(output_dir).resolve()) if output_dir is not None else None,
            "is_official_baseline": bool(is_baseline),
            "code": build_code_provenance(),
            "inference_provenance": inference_provenance,
        },
    )
    if output_dir:
        _save_report(report, Path(output_dir))
    return report


def evaluate_result_against_thresholds(
    result: BenchmarkResult,
    thresholds: dict[str, float],
) -> tuple[bool, list[str]]:
    effective = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    failures: list[str] = []
    if not result.success:
        failures.append("pipeline_success=false")
        return False, failures

    quality = result.quality_metrics
    if quality.get("quality_gate_passed") is False:
        failures.append("quality_gate_failed")
    if quality.get("wall_count", 0) < effective["min_wall_count"]:
        failures.append(f"wall_count<{effective['min_wall_count']}")
    if quality.get("exterior_wall_count", 0) < effective["min_exterior_wall_count"]:
        failures.append(f"exterior_wall_count<{effective['min_exterior_wall_count']}")
    benchmark_review_flags = _review_flags_for_benchmark(result.review_flags)
    if len(benchmark_review_flags) > effective["max_review_flags"]:
        failures.append(f"review_flags>{effective['max_review_flags']}")
    if quality.get("junction_count", 0) < effective["min_junction_count"]:
        failures.append(f"junction_count<{effective['min_junction_count']}")

    comparison = result.comparison
    if comparison.get("wall_footprint_iou") is not None and comparison["wall_footprint_iou"] < effective["min_wall_iou"]:
        failures.append(f"wall_footprint_iou<{effective['min_wall_iou']}")
    if comparison.get("exterior_shell_recall") is not None and comparison["exterior_shell_recall"] < effective["min_exterior_shell_recall"]:
        failures.append(f"exterior_shell_recall<{effective['min_exterior_shell_recall']}")
    if comparison.get("junction_precision") is not None and comparison["junction_precision"] < effective["min_junction_precision"]:
        failures.append(f"junction_precision<{effective['min_junction_precision']}")
    if comparison.get("junction_recall") is not None and comparison["junction_recall"] < effective["min_junction_recall"]:
        failures.append(f"junction_recall<{effective['min_junction_recall']}")

    return len(failures) == 0, failures


def _save_report(report: BenchmarkReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(_json_ready(report.summary()), indent=2), encoding="utf-8")
    (output_dir / "run_manifest.json").write_text(json.dumps(_json_ready(report.metadata), indent=2), encoding="utf-8")
    if report.metadata.get("is_official_baseline"):
        (output_dir / "baseline_manifest.json").write_text(
            json.dumps(_json_ready(report.metadata), indent=2),
            encoding="utf-8",
        )

    for result in report.results:
        case_dir = output_dir / result.name
        case_dir.mkdir(parents=True, exist_ok=True)
        preview_paths: dict[str, str] = {}
        provenance = ((result.region_plan or {}).get("meta") or {}).get("provenance")
        if result.success and result.structure:
            (case_dir / "postprocess.json").write_text(json.dumps(_json_ready(result.structure), indent=2), encoding="utf-8")
            (case_dir / "structure.json").write_text(json.dumps(_json_ready(result.structure), indent=2), encoding="utf-8")
            if result.raw_model:
                (case_dir / "raw_model.json").write_text(json.dumps(_json_ready(result.raw_model), indent=2), encoding="utf-8")
            if result.render_plan:
                (case_dir / "render_plan.json").write_text(json.dumps(_json_ready(result.render_plan), indent=2), encoding="utf-8")
            if result.region_plan:
                (case_dir / "region_plan.json").write_text(json.dumps(_json_ready(result.region_plan), indent=2), encoding="utf-8")
                region_debug = result.region_plan.get("debug")
                if region_debug:
                    (case_dir / "mitunet_region_debug.json").write_text(
                        json.dumps(_json_ready(region_debug), indent=2),
                        encoding="utf-8",
                    )
            if provenance:
                (case_dir / "provenance.json").write_text(
                    json.dumps(_json_ready(provenance), indent=2),
                    encoding="utf-8",
                )

            pipeline_debug = result.structure.get("pipeline_debug")
            if pipeline_debug:
                (case_dir / "pipeline_debug.json").write_text(json.dumps(_json_ready(pipeline_debug), indent=2), encoding="utf-8")

            try:
                _copy_original_image(result, case_dir)
                _save_inference_input_image(result, case_dir)
                _save_raw_model_mask_image(result, case_dir)
                raw_preview = build_preview_image(
                    _structure_for_geometry_benchmark(result.raw_model or result.structure),
                    image_b64=result.source_image_b64,
                )
                postprocess_preview = build_preview_image(
                    _structure_for_geometry_benchmark(result.structure),
                    image_b64=result.source_image_b64,
                )
                cleaned_mask = None
                if result.region_plan and _has_mitunet_wall_mask(result.raw_model):
                    raw_mask = result.raw_model["_wall_mask"]
                    image_shape = (
                        int(result.raw_model.get("_image_shape", [raw_mask.shape[0], raw_mask.shape[1]])[0]),
                        int(result.raw_model.get("_image_shape", [raw_mask.shape[0], raw_mask.shape[1]])[1]),
                    )
                    cleaned_mask = _prepare_mitunet_wall_mask_for_regions(raw_mask, image_shape=image_shape)
                    _save_cleaned_model_mask_image(cleaned_mask, case_dir)
                    raw_preview = _build_binary_mask_preview(raw_mask, image_b64=result.source_image_b64)
                    postprocess_preview = _build_binary_mask_preview(cleaned_mask, image_b64=result.source_image_b64)
                render_plan_preview = _build_wall_entities_preview(
                    (result.render_plan or {}).get("wall_lines", []),
                    image_b64=result.source_image_b64,
                )
                region_plan_preview = None
                dxf_preview_entities = result.dxf_wall_entities
                if result.region_plan:
                    region_plan_preview_entities = _region_plan_to_image_wall_entities(result.region_plan)
                    dxf_preview_entities = _wall_entities_to_image_space(
                        result.dxf_wall_entities,
                        image_shape=_region_plan_image_shape(result.region_plan),
                        transform=(result.region_plan.get("meta") or {}).get("transform") or {},
                    )
                    if result.input_normalization.get("applied"):
                        region_plan_preview_entities = _rescale_wall_entities_to_original_image(
                            region_plan_preview_entities,
                            result.input_normalization,
                        )
                        dxf_preview_entities = _rescale_wall_entities_to_original_image(
                            dxf_preview_entities,
                            result.input_normalization,
                        )
                    region_plan_preview = _build_wall_entities_preview(
                        region_plan_preview_entities,
                        image_b64=result.source_image_b64,
                    )
                dxf_preview = _build_wall_entities_preview(
                    dxf_preview_entities,
                    image_b64=result.source_image_b64,
                )
                path_panel_label = "REGION PLAN" if region_plan_preview is not None else "RENDER PLAN"
                path_panel_image = region_plan_preview if region_plan_preview is not None else render_plan_preview
                comparison = _build_stage_comparison_image(
                    image_b64=result.source_image_b64,
                    panels=[
                        ("RAW MODEL", raw_preview),
                        ("POSTPROCESS", postprocess_preview),
                        (path_panel_label, path_panel_image),
                        ("DXF", dxf_preview),
                    ],
                )

                (case_dir / "raw_model_preview.png").write_bytes(encode_png_data(raw_preview))
                (case_dir / "postprocess_preview.png").write_bytes(encode_png_data(postprocess_preview))
                (case_dir / "render_plan_preview.png").write_bytes(encode_png_data(render_plan_preview))
                if region_plan_preview is not None:
                    (case_dir / "region_plan_preview.png").write_bytes(encode_png_data(region_plan_preview))
                (case_dir / "dxf_preview.png").write_bytes(encode_png_data(dxf_preview))
                (case_dir / "preview.png").write_bytes(encode_png_data(comparison))
                (case_dir / "comparison.png").write_bytes(encode_png_data(comparison))
                preview_paths = {
                    "raw_model_preview": "raw_model_preview.png",
                    "postprocess_preview": "postprocess_preview.png",
                    "render_plan_preview": "render_plan_preview.png",
                    "dxf_preview": "dxf_preview.png",
                    "comparison": "comparison.png",
                }
                if region_plan_preview is not None:
                    preview_paths["region_plan_preview"] = "region_plan_preview.png"
                if (case_dir / "mitunet_region_debug.json").exists():
                    preview_paths["mitunet_region_debug"] = "mitunet_region_debug.json"
                if (case_dir / "raw_wall_mask.png").exists():
                    preview_paths["raw_wall_mask"] = "raw_wall_mask.png"
                if (case_dir / "cleaned_wall_mask.png").exists():
                    preview_paths["cleaned_wall_mask"] = "cleaned_wall_mask.png"
                if (case_dir / "provenance.json").exists():
                    preview_paths["provenance"] = "provenance.json"

                if result.dxf_bytes:
                    (case_dir / "output.dxf").write_bytes(result.dxf_bytes)
            except Exception:
                pass

        result_data = {
            "name": result.name,
            "success": result.success,
            "needs_review": result.needs_review,
            "meets_thresholds": result.meets_thresholds,
            "threshold_failures": result.threshold_failures,
            "elapsed_ms": result.elapsed_ms,
            "input_normalization": result.input_normalization,
            "quality_metrics": result.quality_metrics,
            "review_flags": result.review_flags,
            "benchmark_review_flags": _review_flags_for_benchmark(result.review_flags),
            "comparison": result.comparison,
            "stage_comparison": result.stage_comparison,
            "provenance": provenance,
            "artifact_files": preview_paths,
            "error": result.error,
        }
        (case_dir / "result.json").write_text(json.dumps(_json_ready(result_data), indent=2), encoding="utf-8")


def compare_structures(predicted: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    pred_walls = predicted.get("walls", [])
    exp_walls = expected.get("walls", [])
    expected_junctions = expected.get("junctions") or []

    pred_ext = sum(1 for wall in pred_walls if wall.get("is_exterior"))
    exp_ext = sum(1 for wall in exp_walls if wall.get("is_exterior"))
    junction_metrics = _junction_match_metrics(predicted.get("junctions", []), expected_junctions) if expected_junctions else None

    return {
        "benchmark_scope": "geometry_only",
        "ground_truth_kind": _GROUND_TRUTH_CONTRACT,
        "wall_count_predicted": len(pred_walls),
        "wall_count_expected": len(exp_walls),
        "wall_count_diff": len(pred_walls) - len(exp_walls),
        "exterior_wall_predicted": pred_ext,
        "exterior_wall_expected": exp_ext,
        "wall_footprint_iou": _wall_footprint_iou(predicted, expected),
        "exterior_shell_recall": _exterior_shell_recall(predicted, expected),
        "junction_precision": junction_metrics["precision"] if junction_metrics else None,
        "junction_recall": junction_metrics["recall"] if junction_metrics else None,
    }


def compare_structure_to_segmentation(predicted: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    pred_walls = predicted.get("walls", [])
    wall_mask = expected["wall_mask"]
    shell_mask = expected["shell_mask"]
    junction_metrics = _junction_match_metrics(predicted.get("junctions", []), expected["junctions"])

    return {
        "benchmark_scope": "geometry_only",
        "ground_truth_kind": _GROUND_TRUTH_SEGMENTATION,
        "wall_count_predicted": len(pred_walls),
        "wall_count_expected": int(expected.get("wall_component_count", 0)),
        "wall_footprint_iou": _wall_footprint_iou_vs_mask(predicted, wall_mask),
        "exterior_shell_recall": _exterior_shell_recall_vs_mask(predicted, shell_mask),
        "junction_precision": junction_metrics["precision"],
        "junction_recall": junction_metrics["recall"],
    }


def _load_case_ground_truth(case: BenchmarkCase) -> dict[str, Any] | None:
    if not case.has_ground_truth:
        return None
    if case.ground_truth_kind == _GROUND_TRUTH_CONTRACT:
        return json.loads(case.expected_path.read_text(encoding="utf-8"))
    return _load_segmentation_ground_truth(case)


def _build_stage_comparison(
    *,
    case: BenchmarkCase,
    ground_truth: dict[str, Any] | None,
    raw_model: dict[str, Any],
    postprocess: dict[str, Any],
    render_plan: dict[str, Any],
    region_plan: dict[str, Any] | None,
    dxf_wall_entities: list[dict[str, Any]],
) -> dict[str, Any]:
    render_structure = _render_plan_to_structure(render_plan, postprocess)
    stage_comparison = {
        "raw_model_vs_ground_truth": _compare_stage_structure_to_ground_truth(raw_model, case, ground_truth),
        "postprocess_vs_ground_truth": _compare_stage_structure_to_ground_truth(postprocess, case, ground_truth),
        "render_plan_vs_ground_truth": _compare_stage_structure_to_ground_truth(render_structure, case, ground_truth),
        "dxf_vs_ground_truth": _compare_dxf_stage_to_ground_truth(
            dxf_wall_entities=dxf_wall_entities,
            case=case,
            ground_truth=ground_truth,
            reference_structure=render_structure,
        ),
        "raw_to_postprocess": compare_structures(raw_model, postprocess),
        "postprocess_to_render_plan": compare_structures(render_structure, postprocess),
        "render_plan_to_dxf": _compare_dxf_to_render_plan(dxf_wall_entities, render_plan),
    }
    if region_plan:
        region_structure = _region_plan_to_structure(region_plan, postprocess)
        region_entities = _region_plan_to_wall_entities(region_plan)
        stage_comparison["region_plan_vs_ground_truth"] = _compare_stage_structure_to_ground_truth(region_structure, case, ground_truth)
        stage_comparison["postprocess_to_region_plan"] = compare_structures(region_structure, postprocess)
        stage_comparison["region_plan_to_dxf"] = _compare_dxf_to_wall_entities(dxf_wall_entities, region_entities)
    return stage_comparison


def _compare_stage_structure_to_ground_truth(
    stage_structure: dict[str, Any],
    case: BenchmarkCase,
    ground_truth: dict[str, Any] | None,
) -> dict[str, Any]:
    if ground_truth is None:
        return {}
    if case.ground_truth_kind == _GROUND_TRUTH_CONTRACT:
        return compare_structures(stage_structure, ground_truth)
    return compare_structure_to_segmentation(stage_structure, ground_truth)


def _render_plan_to_structure(render_plan: dict[str, Any], reference_structure: dict[str, Any]) -> dict[str, Any]:
    walls = []
    for index, wall in enumerate(render_plan.get("wall_geometries", []), start=1):
        if wall["orientation"] == "horizontal":
            polyline = [
                {"x": float(wall["start"]), "y": float(wall["coord"])},
                {"x": float(wall["end"]), "y": float(wall["coord"])},
            ]
        else:
            polyline = [
                {"x": float(wall["coord"]), "y": float(wall["start"])},
                {"x": float(wall["coord"]), "y": float(wall["end"])},
            ]
        walls.append(
            {
                "id": wall.get("id", f"render-wall-{index:04d}"),
                "orientation": wall["orientation"],
                "polyline": polyline,
                "thickness": float(wall.get("draw_thickness", wall.get("thickness", 4.0))),
                "is_exterior": bool(wall.get("is_exterior", False)),
                "confidence": 1.0,
            }
        )

    return {
        "model": "DXF Render Plan",
        "source": "benchmark_render_plan",
        "walls": walls,
        "openings": [],
        "junctions": build_junction_graph(walls),
        "structure_meta": reference_structure.get("structure_meta", {}),
    }


def _region_plan_to_structure(region_plan: dict[str, Any], reference_structure: dict[str, Any]) -> dict[str, Any]:
    walls = []
    for index, region in enumerate(region_plan.get("regions", []), start=1):
        bounds = region.get("bounds") or {}
        x1 = float(bounds.get("x1", 0.0))
        y1 = float(bounds.get("y1", 0.0))
        x2 = float(bounds.get("x2", 0.0))
        y2 = float(bounds.get("y2", 0.0))
        orientation = region.get("orientation", "horizontal")
        if orientation == "horizontal":
            polyline = [
                {"x": x1, "y": (y1 + y2) / 2.0},
                {"x": x2, "y": (y1 + y2) / 2.0},
            ]
            thickness = max(1.0, y2 - y1)
        else:
            polyline = [
                {"x": (x1 + x2) / 2.0, "y": y1},
                {"x": (x1 + x2) / 2.0, "y": y2},
            ]
            thickness = max(1.0, x2 - x1)
        walls.append(
            {
                "id": region.get("id", f"region-wall-{index:04d}"),
                "orientation": orientation,
                "polyline": polyline,
                "thickness": float(thickness),
                "is_exterior": False,
                "confidence": 1.0,
            }
        )

    return {
        "model": "MitUNet Region Plan",
        "source": "benchmark_region_plan",
        "walls": walls,
        "openings": [],
        "junctions": build_junction_graph(walls),
        "structure_meta": reference_structure.get("structure_meta", {}),
    }


def _generate_dxf_wall_artifacts(structure: dict[str, Any]) -> tuple[bytes, list[dict[str, Any]]]:
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as handle:
            temp_path = Path(handle.name)
        generate_structural(structure, str(temp_path))
        dxf_bytes = temp_path.read_bytes()
        dxf_wall_entities = _read_dxf_wall_entities(temp_path)
        return dxf_bytes, dxf_wall_entities
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def _generate_mitunet_region_dxf_wall_artifacts(region_plan: dict[str, Any]) -> tuple[bytes, list[dict[str, Any]]]:
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as handle:
            temp_path = Path(handle.name)
        generate_mitunet_region_dxf(region_plan, str(temp_path))
        dxf_bytes = temp_path.read_bytes()
        dxf_wall_entities = _filter_wall_entities_to_bounds(
            _read_dxf_wall_entities(temp_path),
            _region_plan_bounds(region_plan),
            margin=24.0,
        )
        return dxf_bytes, dxf_wall_entities
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def _read_dxf_wall_entities(path: Path) -> list[dict[str, Any]]:
    doc = ezdxf.readfile(str(path))
    entities: list[dict[str, Any]] = []
    for entity in doc.modelspace().query('LINE[layer=="WALLS"]'):
        start = entity.dxf.start
        end = entity.dxf.end
        entities.append(
            {
                "type": "line",
                "layer": "WALLS",
                "start": {"x": float(start.x), "y": float(start.y)},
                "end": {"x": float(end.x), "y": float(end.y)},
            }
        )
    for entity in doc.modelspace().query('LWPOLYLINE[layer=="WALLS"]'):
        points = [(float(point[0]), float(point[1])) for point in entity.get_points("xy")]
        if len(points) < 2:
            continue
        is_closed = bool(entity.closed)
        limit = len(points) if is_closed else len(points) - 1
        for index in range(limit):
            start = points[index]
            end = points[(index + 1) % len(points)]
            entities.append(
                {
                    "type": "line",
                    "layer": "WALLS",
                    "start": {"x": float(start[0]), "y": float(start[1])},
                    "end": {"x": float(end[0]), "y": float(end[1])},
                }
            )
    return entities


def _compare_dxf_stage_to_ground_truth(
    *,
    dxf_wall_entities: list[dict[str, Any]],
    case: BenchmarkCase,
    ground_truth: dict[str, Any] | None,
    reference_structure: dict[str, Any],
) -> dict[str, Any]:
    if ground_truth is None:
        return {}

    if case.ground_truth_kind == _GROUND_TRUTH_SEGMENTATION:
        wall_mask = ground_truth["wall_mask"]
        return {
            "benchmark_scope": "geometry_only",
            "ground_truth_kind": _GROUND_TRUTH_SEGMENTATION,
            "wall_line_count": len(dxf_wall_entities),
            "wall_footprint_iou": _wall_entities_iou_vs_mask(dxf_wall_entities, wall_mask),
            "component_count": _component_count(_wall_entities_to_mask(dxf_wall_entities, wall_mask.shape)),
        }

    expected = ground_truth
    wall_iou = _wall_entities_iou_vs_structure(dxf_wall_entities, expected)
    return {
        "benchmark_scope": "geometry_only",
        "ground_truth_kind": _GROUND_TRUTH_CONTRACT,
        "wall_line_count": len(dxf_wall_entities),
        "wall_footprint_iou": wall_iou,
        "component_count": None,
    }


def _compare_dxf_to_render_plan(
    dxf_wall_entities: list[dict[str, Any]],
    render_plan: dict[str, Any],
) -> dict[str, Any]:
    render_wall_entities = render_plan.get("wall_lines", [])
    if not render_wall_entities and not dxf_wall_entities:
        return {"wall_line_count_predicted": 0, "wall_line_count_expected": 0, "wall_line_count_diff": 0, "wall_line_iou": 1.0}
    bounds = _wall_entity_bounds(render_wall_entities, dxf_wall_entities)
    pred_mask = _wall_entities_to_mask(dxf_wall_entities, (bounds["height"], bounds["width"]), offset=bounds["offset"])
    exp_mask = _wall_entities_to_mask(render_wall_entities, (bounds["height"], bounds["width"]), offset=bounds["offset"])
    return {
        "wall_line_count_predicted": len(dxf_wall_entities),
        "wall_line_count_expected": len(render_wall_entities),
        "wall_line_count_diff": len(dxf_wall_entities) - len(render_wall_entities),
        "wall_line_iou": _mask_iou(pred_mask > 0, exp_mask > 0),
    }


def _compare_dxf_to_wall_entities(
    dxf_wall_entities: list[dict[str, Any]],
    expected_wall_entities: list[dict[str, Any]],
) -> dict[str, Any]:
    if not expected_wall_entities and not dxf_wall_entities:
        return {"wall_line_count_predicted": 0, "wall_line_count_expected": 0, "wall_line_count_diff": 0, "wall_line_iou": 1.0}
    bounds = _wall_entity_bounds(expected_wall_entities, dxf_wall_entities)
    pred_mask = _wall_entities_to_mask(dxf_wall_entities, (bounds["height"], bounds["width"]), offset=bounds["offset"])
    exp_mask = _wall_entities_to_mask(expected_wall_entities, (bounds["height"], bounds["width"]), offset=bounds["offset"])
    return {
        "wall_line_count_predicted": len(dxf_wall_entities),
        "wall_line_count_expected": len(expected_wall_entities),
        "wall_line_count_diff": len(dxf_wall_entities) - len(expected_wall_entities),
        "wall_line_iou": _mask_iou(pred_mask > 0, exp_mask > 0),
    }


def _wall_footprint_iou(predicted: dict[str, Any], expected: dict[str, Any]) -> float | None:
    pred_mask, exp_mask = _rasterize_wall_masks(predicted, expected)
    return _mask_iou(pred_mask, exp_mask)


def _exterior_shell_recall(predicted: dict[str, Any], expected: dict[str, Any]) -> float | None:
    bounds = _comparison_bounds(predicted, expected)
    width = max(64, int(round(bounds["max_x"] - bounds["min_x"] + 40)))
    height = max(64, int(round(bounds["max_y"] - bounds["min_y"] + 40)))
    offset_x = 20 - bounds["min_x"]
    offset_y = 20 - bounds["min_y"]

    pred_mask = np.zeros((height, width), dtype=np.uint8)
    exp_mask = np.zeros((height, width), dtype=np.uint8)
    _draw_walls_to_mask(
        pred_mask,
        [wall for wall in predicted.get("walls", []) if wall.get("is_exterior")],
        offset_x,
        offset_y,
    )
    _draw_walls_to_mask(
        exp_mask,
        [wall for wall in expected.get("walls", []) if wall.get("is_exterior")],
        offset_x,
        offset_y,
    )
    return _mask_recall(pred_mask > 0, exp_mask > 0)


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


def _wall_footprint_iou_vs_mask(predicted: dict[str, Any], expected_mask: np.ndarray) -> float | None:
    pred_mask = _rasterize_structure_walls_to_shape(predicted, expected_mask.shape)
    kernel = _relaxation_kernel(expected_mask)
    pred_relaxed = cv2.dilate((pred_mask.astype(np.uint8) * 255), kernel, iterations=1) > 0
    exp_relaxed = cv2.dilate((expected_mask.astype(np.uint8) * 255), kernel, iterations=1) > 0
    return _mask_iou(pred_relaxed, exp_relaxed)


def _exterior_shell_recall_vs_mask(predicted: dict[str, Any], shell_mask: np.ndarray) -> float | None:
    pred_mask = _rasterize_structure_walls_to_shape(predicted, shell_mask.shape, exterior_only=True)
    kernel = _relaxation_kernel(shell_mask)
    pred_relaxed = cv2.dilate((pred_mask.astype(np.uint8) * 255), kernel, iterations=1) > 0
    exp_relaxed = cv2.dilate((shell_mask.astype(np.uint8) * 255), kernel, iterations=1) > 0
    return _mask_recall(pred_relaxed, exp_relaxed)


def _rasterize_structure_walls_to_shape(
    structure: dict[str, Any],
    shape: tuple[int, int],
    *,
    exterior_only: bool = False,
) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    walls = structure.get("walls", [])
    if exterior_only:
        walls = [wall for wall in walls if wall.get("is_exterior")]
    _draw_walls_to_mask(mask, walls, 0.0, 0.0)
    return mask > 0


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


def _wall_entities_iou_vs_mask(wall_entities: list[dict[str, Any]], expected_mask: np.ndarray) -> float | None:
    pred_mask = _wall_entities_to_mask(wall_entities, expected_mask.shape)
    kernel = _relaxation_kernel(expected_mask)
    pred_relaxed = cv2.dilate(pred_mask, kernel, iterations=1) > 0
    exp_relaxed = cv2.dilate((expected_mask.astype(np.uint8) * 255), kernel, iterations=1) > 0
    return _mask_iou(pred_relaxed, exp_relaxed)


def _wall_entities_iou_vs_structure(wall_entities: list[dict[str, Any]], expected: dict[str, Any]) -> float | None:
    image_size = expected.get("structure_meta", {}).get("image_size")
    if image_size:
        shape = (int(image_size["height"]), int(image_size["width"]))
        pred_mask = _wall_entities_to_mask(wall_entities, shape)
        exp_mask = _rasterize_structure_walls_to_shape(expected, shape)
        return _mask_iou(pred_mask > 0, exp_mask > 0)

    bounds = _comparison_bounds({"walls": _wall_entities_to_structure_walls(wall_entities)}, expected)
    width = max(64, int(round(bounds["max_x"] - bounds["min_x"] + 40)))
    height = max(64, int(round(bounds["max_y"] - bounds["min_y"] + 40)))
    offset = {"x": 20 - bounds["min_x"], "y": 20 - bounds["min_y"]}
    pred_mask = _wall_entities_to_mask(wall_entities, (height, width), offset=offset)
    exp_mask = np.zeros((height, width), dtype=np.uint8)
    _draw_walls_to_mask(exp_mask, expected.get("walls", []), offset["x"], offset["y"])
    return _mask_iou(pred_mask > 0, exp_mask > 0)


def _wall_entities_to_mask(
    wall_entities: list[dict[str, Any]],
    shape: tuple[int, int],
    *,
    offset: dict[str, float] | None = None,
) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    if not wall_entities:
        return mask
    resolved_offset = offset or {"x": 0.0, "y": 0.0}
    for entity in wall_entities:
        start = entity.get("start") or {}
        end = entity.get("end") or {}
        cv2.line(
            mask,
            (
                int(round(float(start.get("x", 0.0)) + resolved_offset["x"])),
                int(round(float(start.get("y", 0.0)) + resolved_offset["y"])),
            ),
            (
                int(round(float(end.get("x", 0.0)) + resolved_offset["x"])),
                int(round(float(end.get("y", 0.0)) + resolved_offset["y"])),
            ),
            255,
            1,
        )
    return mask


def _wall_entity_bounds(*entity_groups: list[dict[str, Any]]) -> dict[str, Any]:
    points: list[tuple[float, float]] = []
    for group in entity_groups:
        for entity in group:
            start = entity.get("start") or {}
            end = entity.get("end") or {}
            points.append((float(start.get("x", 0.0)), float(start.get("y", 0.0))))
            points.append((float(end.get("x", 0.0)), float(end.get("y", 0.0))))
    if not points:
        return {"width": 512, "height": 512, "offset": {"x": 0.0, "y": 0.0}}

    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    return {
        "width": max(64, int(round(max_x - min_x + 40))),
        "height": max(64, int(round(max_y - min_y + 40))),
        "offset": {"x": 20 - min_x, "y": 20 - min_y},
    }


def _wall_entities_to_structure_walls(wall_entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"dxf-wall-line-{index:04d}",
            "polyline": [entity["start"], entity["end"]],
            "thickness": 1.0,
            "is_exterior": bool(entity.get("is_exterior", False)),
        }
        for index, entity in enumerate(wall_entities, start=1)
    ]


def _opening_match_metrics(
    predicted: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    *,
    kind: str | None = None,
    wall_support_mask: np.ndarray | None = None,
    wall_map: dict[str, dict[str, Any]] | None = None,
) -> dict[str, float | int]:
    predicted_kind = [opening for opening in predicted if kind is None or opening.get("kind") == kind]
    expected_kind = [opening for opening in expected if kind is None or opening.get("kind") == kind]

    used_expected: set[int] = set()
    matches = 0
    anchored_matches = 0
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
            if wall_support_mask is None or _opening_has_wall_support(pred, wall_support_mask, wall_map or {}):
                anchored_matches += 1

    precision = matches / len(predicted_kind) if predicted_kind else (1.0 if not expected_kind else 0.0)
    recall = matches / len(expected_kind) if expected_kind else (1.0 if not predicted_kind else 0.0)
    anchor_precision = anchored_matches / len(predicted_kind) if predicted_kind else (1.0 if not expected_kind else 0.0)
    return {
        "predicted": len(predicted_kind),
        "expected": len(expected_kind),
        "matches": matches,
        "precision": precision,
        "recall": recall,
        "anchor_precision": anchor_precision,
    }


def _junction_match_metrics(
    predicted: list[dict[str, Any]],
    expected: list[dict[str, Any]],
) -> dict[str, float | int]:
    if not predicted and not expected:
        return {"predicted": 0, "expected": 0, "matches": 0, "precision": 1.0, "recall": 1.0}

    used_expected: set[int] = set()
    matches = 0
    for pred in predicted:
        pred_type = pred.get("type")
        pred_point = pred.get("point") or {}
        best_index = None
        best_distance = None
        for index, exp in enumerate(expected):
            if index in used_expected or exp.get("type") != pred_type:
                continue
            exp_point = exp.get("point") or {}
            dx = float(pred_point.get("x", 0.0)) - float(exp_point.get("x", 0.0))
            dy = float(pred_point.get("y", 0.0)) - float(exp_point.get("y", 0.0))
            distance = (dx * dx + dy * dy) ** 0.5
            if distance > _JUNCTION_MATCH_TOLERANCE:
                continue
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_index = index
        if best_index is not None:
            used_expected.add(best_index)
            matches += 1

    precision = matches / len(predicted) if predicted else (1.0 if not expected else 0.0)
    recall = matches / len(expected) if expected else (1.0 if not predicted else 0.0)
    return {
        "predicted": len(predicted),
        "expected": len(expected),
        "matches": matches,
        "precision": precision,
        "recall": recall,
    }


def _load_segmentation_ground_truth(case: BenchmarkCase) -> dict[str, Any]:
    label = np.load(case.label_path)
    if label.ndim != 3 or label.shape[0] < 2:
        raise ValueError(f"Benchmark case {case.name} has invalid label.npy shape: {label.shape}")

    room_mask = label[0]
    icon_mask = label[1]
    wall_mask = room_mask == 2
    heatmaps = json.loads(case.heatmaps_path.read_text(encoding="utf-8"))
    return {
        "image_size": {"width": int(room_mask.shape[1]), "height": int(room_mask.shape[0])},
        "wall_mask": wall_mask,
        "shell_mask": _extract_shell_mask(wall_mask),
        "wall_component_count": _component_count(wall_mask),
        "openings": _openings_from_icon_mask(icon_mask),
        "junctions": _junctions_from_heatmaps(heatmaps, wall_mask.shape),
    }


def _mask_iou(pred_mask: np.ndarray, exp_mask: np.ndarray) -> float | None:
    union = np.logical_or(pred_mask, exp_mask).sum()
    if union == 0:
        return None
    intersection = np.logical_and(pred_mask, exp_mask).sum()
    return float(intersection / union)


def _mask_recall(pred_mask: np.ndarray, exp_mask: np.ndarray) -> float | None:
    expected_pixels = exp_mask.sum()
    if expected_pixels == 0:
        return None
    intersection = np.logical_and(pred_mask, exp_mask).sum()
    return float(intersection / expected_pixels)


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


def _extract_shell_mask(wall_mask: np.ndarray) -> np.ndarray:
    binary = wall_mask.astype(np.uint8) * 255
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    shell = np.zeros_like(binary)
    thickness = _estimate_wall_thickness(binary)
    if contours:
        cv2.drawContours(shell, contours, -1, 255, thickness=thickness)
    return shell > 0


def _estimate_wall_thickness(binary_wall_mask: np.ndarray) -> int:
    dist = cv2.distanceTransform(binary_wall_mask, cv2.DIST_L2, 3)
    values = dist[dist > 0]
    if values.size == 0:
        return 4
    return max(2, int(round(float(np.percentile(values, 50)) * 2.0)))


def _relaxation_kernel(mask: np.ndarray) -> np.ndarray:
    thickness = _estimate_wall_thickness(mask.astype(np.uint8) * 255)
    size = max(3, thickness // 2)
    if size % 2 == 0:
        size += 1
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))


def _component_count(mask: np.ndarray) -> int:
    count, _ = cv2.connectedComponents(mask.astype(np.uint8), connectivity=8)
    return max(0, count - 1)


def _openings_from_icon_mask(icon_mask: np.ndarray) -> list[dict[str, Any]]:
    openings: list[dict[str, Any]] = []
    for label_value, kind in ((2, "door"), (1, "window")):
        binary = np.where(icon_mask == label_value, np.uint8(255), np.uint8(0))
        kernel_size = 11 if kind == "door" else 15
        min_area = 120 if kind == "door" else 150
        clustered = cv2.morphologyEx(
            binary,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size)),
            iterations=1,
        )
        clustered = cv2.dilate(
            clustered,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size)),
            iterations=1,
        )
        count, _, stats, centroids = cv2.connectedComponentsWithStats(clustered, connectivity=8)
        for index in range(1, count):
            area = int(stats[index, cv2.CC_STAT_AREA])
            if area < min_area:
                continue
            x = int(stats[index, cv2.CC_STAT_LEFT])
            y = int(stats[index, cv2.CC_STAT_TOP])
            w = int(stats[index, cv2.CC_STAT_WIDTH])
            h = int(stats[index, cv2.CC_STAT_HEIGHT])
            cx, cy = centroids[index]
            openings.append(
                {
                    "id": f"gt-{kind}-{index:04d}",
                    "kind": kind,
                    "position": {"x": float(cx), "y": float(cy)},
                    "span": float(max(w, h)),
                    "orientation": "horizontal" if w >= h else "vertical",
                    "bbox": {"x": x, "y": y, "w": w, "h": h},
                }
            )
    return openings


def _junctions_from_heatmaps(heatmaps: dict[str, Any], image_shape: tuple[int, int]) -> list[dict[str, Any]]:
    height, width = int(image_shape[0]), int(image_shape[1])
    junctions: list[dict[str, Any]] = []
    for channel, junction_type in _HEATMAP_CHANNEL_TO_JUNCTION.items():
        coords = heatmaps.get(channel, [])
        if not coords:
            continue
        mask = np.zeros((height, width), dtype=np.uint8)
        for raw in coords:
            if not isinstance(raw, (list, tuple)) or len(raw) < 2:
                continue
            x = int(raw[0])
            y = int(raw[1])
            if 0 <= x < width and 0 <= y < height:
                mask[y, x] = 255
        if not np.any(mask):
            continue
        clustered = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=1)
        count, _, stats, centroids = cv2.connectedComponentsWithStats(clustered, connectivity=8)
        for index in range(1, count):
            if int(stats[index, cv2.CC_STAT_AREA]) < 3:
                continue
            cx, cy = centroids[index]
            junctions.append({"point": {"x": float(cx), "y": float(cy)}, "type": junction_type})
    return junctions


def _opening_has_wall_support(
    opening: dict[str, Any],
    wall_support_mask: np.ndarray,
    wall_map: dict[str, dict[str, Any]],
) -> bool:
    wall_id = opening.get("wall_id")
    if not wall_id or wall_id not in wall_map:
        return False

    wall = wall_map[wall_id]
    points = wall.get("polyline") or []
    if len(points) != 2:
        return False

    local_mask = np.zeros_like(wall_support_mask, dtype=np.uint8)
    start = points[0]
    end = points[1]
    thickness = max(1, int(round(float(wall.get("thickness", 4.0)))))
    cv2.line(
        local_mask,
        (int(round(float(start["x"]))), int(round(float(start["y"])))),
        (int(round(float(end["x"]))), int(round(float(end["y"])))),
        255,
        thickness,
    )

    pos = opening.get("position") or {}
    cx = int(round(float(pos.get("x", 0.0))))
    cy = int(round(float(pos.get("y", 0.0))))
    radius = max(8, int(round(float(opening.get("span", 0.0)))))
    y1 = max(0, cy - radius)
    y2 = min(wall_support_mask.shape[0], cy + radius + 1)
    x1 = max(0, cx - radius)
    x2 = min(wall_support_mask.shape[1], cx + radius + 1)
    if y1 >= y2 or x1 >= x2:
        return False

    support = np.logical_and(local_mask[y1:y2, x1:x2] > 0, wall_support_mask[y1:y2, x1:x2]).sum()
    return bool(support >= max(3, thickness))


def _first_existing(directory: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        candidate = directory / name
        if candidate.exists():
            return candidate
    return None


def _image_data_uri(path: Path) -> str:
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def _png_data_uri(image: np.ndarray) -> str:
    payload = base64.b64encode(encode_png_data(image)).decode("ascii")
    return f"data:image/png;base64,{payload}"


def _normalize_image_for_benchmark(image: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    height, width = image.shape[:2]
    short_side = min(width, height)
    normalization = {
        "applied": False,
        "profile": "native_resolution",
        "strategy": "none",
        "original_size": {"width": int(width), "height": int(height)},
        "inference_size": {"width": int(width), "height": int(height)},
        "scale": 1.0,
        "scale_x": 1.0,
        "scale_y": 1.0,
        "target_min_short_side": _BENCHMARK_MIN_SHORT_SIDE,
    }
    if short_side >= _BENCHMARK_MIN_SHORT_SIDE:
        return image, normalization

    scale = float(_BENCHMARK_MIN_SHORT_SIDE / short_side)
    resized = cv2.resize(
        image,
        (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
        interpolation=cv2.INTER_CUBIC,
    )
    normalization.update(
        {
            "applied": True,
            "profile": "low_res_upscaled",
            "strategy": "upscale_min_short_side",
            "inference_size": {"width": int(resized.shape[1]), "height": int(resized.shape[0])},
            "scale": scale,
            "scale_x": float(resized.shape[1] / width),
            "scale_y": float(resized.shape[0] / height),
            "interpolation": "INTER_CUBIC",
        }
    )
    return resized, normalization


def _rescale_structure_to_original_space(
    structure: dict[str, Any],
    input_normalization: dict[str, Any],
) -> dict[str, Any]:
    rescaled = copy.deepcopy(structure)
    scale_x = 1.0 / float(input_normalization["scale_x"])
    scale_y = 1.0 / float(input_normalization["scale_y"])
    _rescale_geometry_value(rescaled, scale_x, scale_y, visited=set())

    structure_meta = rescaled.setdefault("structure_meta", {})
    structure_meta["image_size"] = dict(input_normalization["original_size"])
    structure_meta["benchmark_input_normalization"] = dict(input_normalization)
    return rescaled


def _rescale_geometry_value(value: Any, scale_x: float, scale_y: float, *, visited: set[int]) -> Any:
    if isinstance(value, list):
        value_id = id(value)
        if value_id in visited:
            return value
        visited.add(value_id)
        for item in value:
            _rescale_geometry_value(item, scale_x, scale_y, visited=visited)
        return value
    if isinstance(value, dict):
        value_id = id(value)
        if value_id in visited:
            return value
        visited.add(value_id)
        for key, nested in value.items():
            if isinstance(nested, (int, float)) and not isinstance(nested, bool):
                if key in _GEOMETRY_SCALE_X_KEYS:
                    value[key] = float(nested) * scale_x
                    continue
                if key in _GEOMETRY_SCALE_Y_KEYS:
                    value[key] = float(nested) * scale_y
                    continue
                if key in _GEOMETRY_SCALE_UNIFORM_KEYS:
                    value[key] = float(nested) * ((scale_x + scale_y) / 2.0)
                    continue
            _rescale_geometry_value(nested, scale_x, scale_y, visited=visited)
        return value
    return value


def _review_flags_for_benchmark(review_flags: list[str]) -> list[str]:
    return [flag for flag in review_flags if not _is_opening_related_review_flag(flag)]


def _is_opening_related_review_flag(flag: str) -> bool:
    normalized = flag.lower()
    return "opening" in normalized or "door" in normalized or "window" in normalized


def _structure_for_geometry_benchmark(structure: dict[str, Any]) -> dict[str, Any]:
    geometry = copy.deepcopy(structure)
    normalized_walls: list[dict[str, Any]] = []
    for wall in geometry.get("walls", []) or []:
        polyline = wall.get("polyline") or []
        if len(polyline) != 2:
            continue
        normalized_points: list[dict[str, float]] = []
        for point in polyline:
            if isinstance(point, dict):
                normalized_points.append({
                    "x": float(point.get("x", 0.0)),
                    "y": float(point.get("y", 0.0)),
                })
            elif isinstance(point, (list, tuple)) and len(point) >= 2:
                normalized_points.append({
                    "x": float(point[0]),
                    "y": float(point[1]),
                })
        if len(normalized_points) != 2:
            continue
        wall["polyline"] = normalized_points
        normalized_walls.append(wall)

    geometry["walls"] = normalized_walls
    geometry["openings"] = []
    return geometry


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, np.ndarray):
        nonzero_count = int(np.count_nonzero(value))
        return {
            "_type": "ndarray_summary",
            "shape": [int(dim) for dim in value.shape],
            "dtype": str(value.dtype),
            "nonzero_count": nonzero_count,
            "min": float(value.min()) if value.size else 0.0,
            "max": float(value.max()) if value.size else 0.0,
        }
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


def _copy_original_image(result: BenchmarkResult, case_dir: Path) -> None:
    if not result.source_image_path:
        return
    source_path = Path(result.source_image_path)
    if not source_path.exists():
        return

    suffix = source_path.suffix.lower() or ".png"
    target_path = case_dir / f"original{suffix}"
    shutil.copy2(source_path, target_path)


def _save_raw_model_mask_image(result: BenchmarkResult, case_dir: Path) -> None:
    if not result.raw_model:
        return
    wall_mask = result.raw_model.get("_wall_mask")
    if not isinstance(wall_mask, np.ndarray):
        return
    cv2.imwrite(str(case_dir / "raw_wall_mask.png"), wall_mask)


def _save_cleaned_model_mask_image(cleaned_mask: np.ndarray | None, case_dir: Path) -> None:
    if not isinstance(cleaned_mask, np.ndarray):
        return
    cv2.imwrite(str(case_dir / "cleaned_wall_mask.png"), cleaned_mask)


def _has_mitunet_wall_mask(raw_model: dict[str, Any] | None) -> bool:
    return bool(
        raw_model
        and raw_model.get("source") == MITUNET_BACKEND
        and isinstance(raw_model.get("_wall_mask"), np.ndarray)
    )


def _resized_mask_for_canvas(mask: np.ndarray, image_b64: str | None) -> np.ndarray:
    if image_b64 is None:
        return mask
    canvas = decode_image(image_b64)
    if mask.shape[:2] == canvas.shape[:2]:
        return mask
    return cv2.resize(mask, (canvas.shape[1], canvas.shape[0]), interpolation=cv2.INTER_NEAREST)


def _build_binary_mask_preview(
    mask: np.ndarray,
    *,
    image_b64: str | None = None,
    color: tuple[int, int, int] = (25, 25, 220),
    alpha: float = 0.78,
) -> np.ndarray:
    if image_b64:
        canvas = decode_image(image_b64).copy()
    else:
        resized = mask
        canvas = np.full((resized.shape[0], resized.shape[1], 3), 255, dtype=np.uint8)

    mask_for_canvas = _resized_mask_for_canvas(mask, image_b64)
    binary = mask_for_canvas > 0
    overlay = canvas.copy()
    overlay[binary] = color
    blended = cv2.addWeighted(overlay, alpha, canvas, 1.0 - alpha, 0.0)
    blended[~binary] = canvas[~binary]
    return blended


def _save_inference_input_image(result: BenchmarkResult, case_dir: Path) -> None:
    if not result.inference_image_b64 or not result.input_normalization.get("applied"):
        return
    inference_image = decode_image(result.inference_image_b64)
    (case_dir / "inference_input.png").write_bytes(encode_png_data(inference_image))


def _region_plan_to_wall_entities(region_plan: dict[str, Any]) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for region in region_plan.get("regions", []):
        bounds = region.get("bounds") or {}
        x1 = float(bounds.get("x1", 0.0))
        y1 = float(bounds.get("y1", 0.0))
        x2 = float(bounds.get("x2", 0.0))
        y2 = float(bounds.get("y2", 0.0))
        points = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        for index in range(len(points)):
            start = points[index]
            end = points[(index + 1) % len(points)]
            entities.append(
                {
                    "type": "line",
                    "layer": "WALLS",
                    "start": {"x": float(start[0]), "y": float(start[1])},
                    "end": {"x": float(end[0]), "y": float(end[1])},
                }
            )
    return entities


def _region_plan_image_shape(region_plan: dict[str, Any]) -> tuple[int, int]:
    meta = region_plan.get("meta") or {}
    image_shape = meta.get("image_shape") or {}
    return (
        int(image_shape.get("height", 0)),
        int(image_shape.get("width", 0)),
    )


def _mitunet_dxf_to_image_point(
    dx: float,
    dy: float,
    *,
    image_shape: tuple[int, int],
    transform: dict[str, Any],
) -> dict[str, float]:
    height, _ = image_shape
    scale = float(transform.get("scale", 1.0) or 1.0)
    offset_x = float(transform.get("offset_x", 0.0) or 0.0)
    offset_y = float(transform.get("offset_y", 0.0) or 0.0)
    ix = (float(dx) - offset_x) / scale
    iy = float(height) - ((float(dy) - offset_y) / scale)
    return {"x": ix, "y": iy}


def _wall_entities_to_image_space(
    wall_entities: list[dict[str, Any]],
    *,
    image_shape: tuple[int, int],
    transform: dict[str, Any],
) -> list[dict[str, Any]]:
    height, width = image_shape
    if height <= 0 or width <= 0:
        return wall_entities

    projected: list[dict[str, Any]] = []
    for entity in wall_entities:
        start = entity.get("start") or {}
        end = entity.get("end") or {}
        projected.append(
            {
                **entity,
                "start": _mitunet_dxf_to_image_point(
                    float(start.get("x", 0.0)),
                    float(start.get("y", 0.0)),
                    image_shape=image_shape,
                    transform=transform,
                ),
                "end": _mitunet_dxf_to_image_point(
                    float(end.get("x", 0.0)),
                    float(end.get("y", 0.0)),
                    image_shape=image_shape,
                    transform=transform,
                ),
            }
        )
    return projected


def _rescale_wall_entities_to_original_image(
    wall_entities: list[dict[str, Any]],
    input_normalization: dict[str, Any],
) -> list[dict[str, Any]]:
    if not input_normalization.get("applied"):
        return wall_entities

    scale_x = 1.0 / float(input_normalization.get("scale_x", 1.0) or 1.0)
    scale_y = 1.0 / float(input_normalization.get("scale_y", 1.0) or 1.0)

    rescaled: list[dict[str, Any]] = []
    for entity in wall_entities:
        start = entity.get("start") or {}
        end = entity.get("end") or {}
        rescaled.append(
            {
                **entity,
                "start": {
                    "x": float(start.get("x", 0.0)) * scale_x,
                    "y": float(start.get("y", 0.0)) * scale_y,
                },
                "end": {
                    "x": float(end.get("x", 0.0)) * scale_x,
                    "y": float(end.get("y", 0.0)) * scale_y,
                },
            }
        )
    return rescaled


def _region_plan_to_image_wall_entities(region_plan: dict[str, Any]) -> list[dict[str, Any]]:
    meta = region_plan.get("meta") or {}
    return _wall_entities_to_image_space(
        _region_plan_to_wall_entities(region_plan),
        image_shape=_region_plan_image_shape(region_plan),
        transform=meta.get("transform") or {},
    )


def _region_plan_bounds(region_plan: dict[str, Any]) -> dict[str, float]:
    points: list[tuple[float, float]] = []
    for region in region_plan.get("regions", []):
        bounds = region.get("bounds") or {}
        x1 = float(bounds.get("x1", 0.0))
        y1 = float(bounds.get("y1", 0.0))
        x2 = float(bounds.get("x2", 0.0))
        y2 = float(bounds.get("y2", 0.0))
        points.extend([(x1, y1), (x2, y2)])

    if not points:
        return {"min_x": 0.0, "min_y": 0.0, "max_x": 0.0, "max_y": 0.0}

    return {
        "min_x": min(point[0] for point in points),
        "min_y": min(point[1] for point in points),
        "max_x": max(point[0] for point in points),
        "max_y": max(point[1] for point in points),
    }


def _filter_wall_entities_to_bounds(
    wall_entities: list[dict[str, Any]],
    bounds: dict[str, float],
    *,
    margin: float = 0.0,
) -> list[dict[str, Any]]:
    min_x = bounds["min_x"] - margin
    min_y = bounds["min_y"] - margin
    max_x = bounds["max_x"] + margin
    max_y = bounds["max_y"] + margin

    filtered: list[dict[str, Any]] = []
    for entity in wall_entities:
        start = entity.get("start") or {}
        end = entity.get("end") or {}
        sx = float(start.get("x", 0.0))
        sy = float(start.get("y", 0.0))
        ex = float(end.get("x", 0.0))
        ey = float(end.get("y", 0.0))
        if min_x <= sx <= max_x and min_y <= sy <= max_y and min_x <= ex <= max_x and min_y <= ey <= max_y:
            filtered.append(entity)
    return filtered


def _build_wall_entities_preview(
    wall_entities: list[dict[str, Any]],
    *,
    image_b64: str | None = None,
    color: tuple[int, int, int] = (25, 25, 220),
) -> np.ndarray:
    if image_b64:
        canvas = decode_image(image_b64).copy()
        offset = {"x": 0.0, "y": 0.0}
    else:
        bounds = _wall_entity_bounds(wall_entities)
        canvas = np.full((bounds["height"], bounds["width"], 3), 255, dtype=np.uint8)
        offset = bounds["offset"]

    for entity in wall_entities:
        start = entity.get("start") or {}
        end = entity.get("end") or {}
        cv2.line(
            canvas,
            (
                int(round(float(start.get("x", 0.0)) + offset["x"])),
                int(round(float(start.get("y", 0.0)) + offset["y"])),
            ),
            (
                int(round(float(end.get("x", 0.0)) + offset["x"])),
                int(round(float(end.get("y", 0.0)) + offset["y"])),
            ),
            color,
            2,
            cv2.LINE_AA,
        )
    return canvas


def _build_stage_comparison_image(
    *,
    image_b64: str | None,
    panels: list[tuple[str, np.ndarray]],
) -> np.ndarray:
    rendered_panels: list[np.ndarray] = []
    if image_b64:
        rendered_panels.append(_with_panel_label(_ensure_color(decode_image(image_b64)), "PLANO ORIGINAL"))

    for label, image in panels:
        rendered_panels.append(_with_panel_label(_ensure_color(image), label))

    target_height = max(panel.shape[0] for panel in rendered_panels)
    padded = [_pad_to_height(panel, target_height) for panel in rendered_panels]
    separator = np.full((target_height, 20, 3), 232, dtype=np.uint8)

    stitched = padded[0]
    for panel in padded[1:]:
        stitched = np.hstack([stitched, separator, panel])
    return stitched


def _with_panel_label(image: np.ndarray, label: str) -> np.ndarray:
    banner_height = 44
    banner = np.full((banner_height, image.shape[1], 3), 250, dtype=np.uint8)
    cv2.putText(
        banner,
        label,
        (12, 29),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (40, 40, 40),
        2,
        cv2.LINE_AA,
    )
    cv2.line(
        banner,
        (0, banner_height - 2),
        (banner.shape[1], banner_height - 2),
        (210, 210, 210),
        1,
        cv2.LINE_AA,
    )
    return np.vstack([banner, image])


def _pad_to_height(image: np.ndarray, target_height: int) -> np.ndarray:
    if image.shape[0] == target_height:
        return image
    pad_total = max(0, target_height - image.shape[0])
    pad_top = pad_total // 2
    pad_bottom = pad_total - pad_top
    return cv2.copyMakeBorder(
        image,
        pad_top,
        pad_bottom,
        0,
        0,
        cv2.BORDER_CONSTANT,
        value=(255, 255, 255),
    )


def _ensure_color(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    return image


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Point.ai Benchmark Runner")
    parser.add_argument("--dataset", required=True, help="Path to benchmark dataset directory")
    parser.add_argument("--output", default=None, help="Path to save benchmark results")
    parser.add_argument("--backend", default=None, help="Inference backend override")
    parser.add_argument("--limit", type=int, default=None, help="Optional max case count")
    parser.add_argument("--baseline", action="store_true", help="Mark this run as the official baseline")
    args = parser.parse_args()

    report = run_benchmark(
        args.dataset,
        output_dir=args.output,
        backend=args.backend,
        limit=args.limit,
        is_baseline=args.baseline,
    )
    summary = report.summary()

    print(f"\nBenchmark complete: {summary['total']} cases")
    print(f"  Passed: {summary['passed']}")
    print(f"  Failed: {summary['failed']}")
    print(f"  Threshold passed: {summary['threshold_passed']}")
    print(f"  Threshold failed: {summary['threshold_failed']}")
    print(f"  Review rate: {summary['review_rate']:.2%}")
    print(f"  Avg time: {summary['avg_elapsed_ms']:.0f}ms")

    if report.failed:
        print("\nFailed cases:")
        for result in report.failed:
            print(f"  - {result.name}: {result.error}")


if __name__ == "__main__":
    main()
