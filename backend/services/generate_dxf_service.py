"""
generate_dxf_service — Orchestrate DXF generation from a parsed structure.
"""
import uuid

from ..mitunet_inference import (
    build_mitunet_region_plan,
    generate_mitunet_region_dxf,
    regions_to_wall_annotations,
)
from ..structural_generator import generate as generate_structural
from ..dxf_preview import build_dxf_preview
from ..observability import log_event
from ..components.dimensions import compute_dimension_annotations
from ..measurement.calibration import calibrate_scale


def _ensure_ids(annotations: list[dict]) -> list[dict]:
    """Generate UUIDs for any annotation that arrived without an id.

    We mutate in-place so downstream references (wall_ids inside dimensions)
    stay consistent throughout the pipeline.
    """
    for ann in annotations or []:
        if not ann.get("id"):
            ann["id"] = str(uuid.uuid4())
    return annotations


def _enrich_with_dimensions(
    annotations: list[dict],
    infer_result: dict,
    total_area_sqft: float | None,
) -> tuple[list[dict], float | None]:
    """Compute dimension annotations (exterior + window chains) if missing.

    Respects user-supplied dimensions: if the request already carries any
    annotation with ``type='dimension'``, we do NOT recompute — the user
    is the final authority on dimensions once they've been loaded into the
    2D editor. Returns (annotations_with_dimensions, scale_ipp_or_None).
    """
    if annotations is None:
        return annotations, None

    has_user_dims = any(a.get("type") == "dimension" for a in annotations)
    wall_mask = infer_result.get("_wall_mask") if infer_result else None
    image_shape = infer_result.get("_image_shape") if infer_result else None
    if wall_mask is None or image_shape is None:
        return annotations, None

    has_label = any(a.get("type") == "label" for a in annotations)
    if not has_label:
        return annotations, None

    measurement_context = calibrate_scale(
        annotations,
        wall_mask,
        image_shape,
        total_area_sqft=float(total_area_sqft) if total_area_sqft else None,
    )
    if measurement_context is None:
        return annotations, None

    scale_ipp = float(measurement_context["scale_ipp"])
    if has_user_dims:
        return annotations, scale_ipp

    dims = compute_dimension_annotations(annotations, scale_ipp, image_shape)
    if dims:
        annotations = list(annotations) + dims
    return annotations, scale_ipp


def generate_dxf(
    *,
    parsed: dict,
    out_path: str,
    dxf_mode: str,
    annotations: list | None,
    total_area: float | None,
    image_b64: str | None,
) -> dict:
    """Run full DXF generation pipeline.

    Returns dict with keys: computed_rooms, region_overlay, auto_annotations, dxf_preview.
    """
    user_has_annotations = annotations is not None
    computed_rooms = None
    region_overlay = None
    scale_ipp = None

    parsed["structure"].setdefault("structure_meta", {})
    parsed["quality_metrics"]["dxf_mode"] = dxf_mode
    parsed["structure"]["structure_meta"]["dxf_mode"] = dxf_mode

    if dxf_mode == "mask_regions":
        infer_result = parsed.get("_infer_result") or {}
        auto_anns = infer_result.get("_auto_annotations", [])
        merged_anns = annotations if user_has_annotations else auto_anns

        # Ensure every annotation carries an id so dimensions can anchor
        # to walls via wall_ids and survive reorders/deletes.
        merged_anns = _ensure_ids(list(merged_anns) if merged_anns else [])

        # Compute dimensions upstream so the DXF writer is a pure exporter
        # and the response carries them for the frontend editor to render.
        merged_anns, scale_ipp = _enrich_with_dimensions(
            merged_anns, infer_result, total_area,
        )

        region_plan = build_mitunet_region_plan(infer_result, annotations=merged_anns)

        parsed["quality_metrics"]["dxf_region_count"] = region_plan["meta"]["region_count"]
        parsed["structure"]["structure_meta"]["dxf_region_plan"] = region_plan
        parsed["structure"]["structure_meta"]["mitunet_region_debug"] = region_plan.get("debug", {})
        parsed["structure"]["structure_meta"]["provenance"] = region_plan["meta"].get("provenance", {})

        if user_has_annotations:
            _, dims_result = generate_mitunet_region_dxf(
                region_plan, out_path,
                annotations=merged_anns, skip_regions=True,
                total_area_sqft=total_area,
            )
        else:
            _, dims_result = generate_mitunet_region_dxf(
                region_plan, out_path,
                annotations=merged_anns,
                total_area_sqft=total_area,
            )
        if dims_result:
            computed_rooms = dims_result.get("computed_rooms")
            region_overlay = dims_result.get("region_overlay")
            if dims_result.get("scale_ipp") is not None:
                scale_ipp = float(dims_result["scale_ipp"])
    else:
        generate_structural(parsed["structure"], out_path)

    # Strip non-serializable numpy arrays
    _rp = parsed["structure"].get("structure_meta", {}).get("dxf_region_plan")
    if _rp and "meta" in _rp:
        _rp["meta"].pop("_wall_mask", None)

    # Build auto_annotations response — include the dimensions we computed
    # so the frontend editor can render and edit them as regular annotations.
    infer_result_for_anns = parsed.get("_infer_result") or {}
    auto_anns_response = list(infer_result_for_anns.get("_auto_annotations", []) or [])
    region_plan_data = parsed["structure"].get("structure_meta", {}).get("dxf_region_plan")
    if region_plan_data and not user_has_annotations:
        wall_anns = regions_to_wall_annotations(region_plan_data)
        auto_anns_response = wall_anns + auto_anns_response

    if dxf_mode == "mask_regions" and 'merged_anns' in locals():
        dim_anns = [a for a in merged_anns if a.get("type") == "dimension"]
        if dim_anns:
            auto_anns_response = auto_anns_response + dim_anns

    # Build DXF preview
    dxf_preview_img = None
    try:
        region_plan_for_preview = parsed["structure"].get("structure_meta", {}).get("dxf_region_plan")
        dxf_preview_img = build_dxf_preview(
            out_path, image_b64=image_b64, region_plan=region_plan_for_preview,
        )
    except Exception as exc:
        log_event("api.generate_dxf.dxf_preview_error", error=str(exc))

    return {
        "computed_rooms": computed_rooms,
        "region_overlay": region_overlay,
        "auto_annotations": auto_anns_response or None,
        "dxf_preview": dxf_preview_img,
        "scale_ipp": scale_ipp,
    }
