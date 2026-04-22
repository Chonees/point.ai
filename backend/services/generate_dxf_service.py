"""
generate_dxf_service — Orchestrate DXF generation from a parsed structure.
"""
import uuid

from ..mitunet_inference import (
    align_opening_annotations_to_walls,
    build_mitunet_region_plan,
    generate_mitunet_region_dxf,
    regions_to_wall_annotations,
)
from ..structural_generator import generate as generate_structural
from ..dxf_preview import build_dxf_preview
from ..observability import log_event


def _ensure_ids(annotations: list[dict]) -> list[dict]:
    """Generate UUIDs for any annotation that arrived without an id.

    We mutate in-place so downstream wall/opening references stay consistent
    throughout the pipeline.
    """
    for ann in annotations or []:
        if not ann.get("id"):
            ann["id"] = str(uuid.uuid4())
    return annotations


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

    Returns dict with keys: auto_annotations, dxf_preview.
    """
    user_has_annotations = annotations is not None
    parsed["structure"].setdefault("structure_meta", {})
    parsed["quality_metrics"]["dxf_mode"] = dxf_mode
    parsed["structure"]["structure_meta"]["dxf_mode"] = dxf_mode

    if dxf_mode == "mask_regions":
        infer_result = parsed.get("_infer_result") or {}
        auto_anns = infer_result.get("_auto_annotations", [])
        merged_anns = annotations if user_has_annotations else auto_anns

        # Ensure every annotation carries an id so wall/opening references stay stable.
        merged_anns = _ensure_ids(list(merged_anns) if merged_anns else [])

        region_plan = build_mitunet_region_plan(infer_result, annotations=merged_anns)
        wall_anns = regions_to_wall_annotations(region_plan)
        aligned_anns = (
            align_opening_annotations_to_walls(
                wall_anns,
                merged_anns,
                image_shape=(
                    int(region_plan["meta"]["image_shape"]["height"]),
                    int(region_plan["meta"]["image_shape"]["width"]),
                ),
            )
            if not user_has_annotations
            else list(merged_anns)
        )
        dxf_annotations = list(merged_anns) if user_has_annotations else list(wall_anns)

        parsed["quality_metrics"]["dxf_region_count"] = region_plan["meta"]["region_count"]
        parsed["structure"]["structure_meta"]["dxf_region_plan"] = region_plan
        parsed["structure"]["structure_meta"]["mitunet_region_debug"] = region_plan.get("debug", {})
        parsed["structure"]["structure_meta"]["provenance"] = region_plan["meta"].get("provenance", {})

        if user_has_annotations:
            generate_mitunet_region_dxf(
                region_plan, out_path,
                annotations=dxf_annotations, skip_regions=True,
                total_area_sqft=total_area,
            )
        else:
            generate_mitunet_region_dxf(
                region_plan, out_path,
                annotations=dxf_annotations,
                skip_regions=True,
                total_area_sqft=total_area,
            )

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
        auto_anns_response = list(wall_anns)


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
        "auto_annotations": auto_anns_response or None,
        "dxf_preview": dxf_preview_img,
        "computed_rooms": None,
        "region_overlay": None,
        "scale_ipp": None,
    }
