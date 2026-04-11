"""
generate_dxf_service — Orchestrate DXF generation from a parsed structure.
"""
from ..mitunet_inference import (
    build_mitunet_region_plan,
    generate_mitunet_region_dxf,
    regions_to_wall_annotations,
)
from ..structural_generator import generate as generate_structural
from ..dxf_preview import build_dxf_preview
from ..observability import log_event


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

    parsed["structure"].setdefault("structure_meta", {})
    parsed["quality_metrics"]["dxf_mode"] = dxf_mode
    parsed["structure"]["structure_meta"]["dxf_mode"] = dxf_mode

    if dxf_mode == "mask_regions":
        infer_result = parsed.get("_infer_result") or {}
        auto_anns = infer_result.get("_auto_annotations", [])
        merged_anns = annotations if user_has_annotations else auto_anns

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
    else:
        generate_structural(parsed["structure"], out_path)

    # Strip non-serializable numpy arrays
    _rp = parsed["structure"].get("structure_meta", {}).get("dxf_region_plan")
    if _rp and "meta" in _rp:
        _rp["meta"].pop("_wall_mask", None)

    # Build auto_annotations response
    infer_result_for_anns = parsed.get("_infer_result") or {}
    auto_anns_response = infer_result_for_anns.get("_auto_annotations", [])
    region_plan_data = parsed["structure"].get("structure_meta", {}).get("dxf_region_plan")
    if region_plan_data:
        wall_anns = regions_to_wall_annotations(region_plan_data)
        if user_has_annotations:
            # User already has walls — don't duplicate, just return thickness map
            auto_anns_response = wall_anns + auto_anns_response
        else:
            auto_anns_response = wall_anns + auto_anns_response

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
    }
