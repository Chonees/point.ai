"""
generate_dxf_service — Orchestrate DXF generation from a parsed structure.
"""
from ..mitunet_inference import (
    build_mitunet_region_plan,
    generate_mitunet_region_dxf,
)
from ..structural_generator import generate as generate_structural
from ..dxf_preview import build_dxf_preview
from ..observability import log_event


def generate_dxf(
    *,
    parsed: dict,
    out_path: str,
    dxf_mode: str,
    image_b64: str | None,
) -> dict:
    """Run full DXF generation pipeline.

    Returns dict with keys: dxf_preview.
    """
    parsed["structure"].setdefault("structure_meta", {})
    parsed["quality_metrics"]["dxf_mode"] = dxf_mode
    parsed["structure"]["structure_meta"]["dxf_mode"] = dxf_mode

    if dxf_mode == "mask_regions":
        infer_result = parsed.get("_infer_result") or {}
        if "_reviewed_annotations" in parsed:
            auto_annotations = parsed.get("_reviewed_annotations") or []
            infer_result["_auto_annotations"] = auto_annotations
        else:
            auto_annotations = infer_result.get("_auto_annotations", [])
        region_plan = build_mitunet_region_plan(infer_result, annotations=auto_annotations)

        parsed["quality_metrics"]["dxf_region_count"] = region_plan["meta"]["region_count"]
        parsed["structure"]["structure_meta"]["dxf_region_plan"] = region_plan
        parsed["structure"]["structure_meta"]["mitunet_region_debug"] = region_plan.get("debug", {})
        parsed["structure"]["structure_meta"]["provenance"] = region_plan["meta"].get("provenance", {})
        generate_mitunet_region_dxf(region_plan, out_path, annotations=auto_annotations)
    else:
        generate_structural(parsed["structure"], out_path)

    # Strip non-serializable numpy arrays
    _rp = parsed["structure"].get("structure_meta", {}).get("dxf_region_plan")
    if _rp and "meta" in _rp:
        _rp["meta"].pop("_wall_mask", None)

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
        "dxf_preview": dxf_preview_img,
    }
