"""
parse_service — Resolve input (structure / plan / image) into a parsed structure dict.
"""
from ..worker_client import infer_structure
from ..plan_parser import parse_structure_payload
from ..mitunet_inference import MITUNET_BACKEND
from ..ensemble_inference import ENSEMBLE_BACKEND


def parse_v2_input(
    plan: dict | None,
    structure: dict | None,
    image: str | None,
    scale_hint: float | None,
    model_variant: str | None,
) -> tuple[dict, str | None, str | None]:
    """Parse/infer a floor plan structure from one of three input modes.

    Returns (parsed_payload, image_b64_or_none, debug_overlay_b64_or_none).
    """
    if structure is not None:
        parsed = parse_structure_payload(structure=structure, scale_hint=scale_hint)
        return parsed, None, structure.get("inference_debug", {}).get("debug_overlay_b64")

    if plan is not None:
        parsed = parse_structure_payload(plan=plan, scale_hint=scale_hint)
        return parsed, None, None

    if image is not None:
        if model_variant == "r2v":
            inferred = infer_structure(image, backend="r2v_local")
        elif model_variant == "mitunet":
            inferred = infer_structure(image, backend="mitunet_local")
        elif model_variant == "ensemble":
            inferred = infer_structure(image, backend="ensemble_local")
        else:
            options = {"model_variant": model_variant} if model_variant else None
            if options is None:
                inferred = infer_structure(image)
            else:
                inferred = infer_structure(image, options=options)
        parsed = parse_structure_payload(structure=inferred, scale_hint=scale_hint)
        parsed["quality_metrics"]["inference_backend"] = (
            inferred.get("inference_debug", {}).get("backend") or inferred.get("source")
        )
        parsed["quality_metrics"]["model_variant"] = (
            inferred.get("inference_debug", {}).get("model_variant") or model_variant or "baseline"
        )
        parsed["_infer_result"] = inferred
        return parsed, image, inferred.get("inference_debug", {}).get("debug_overlay_b64")

    raise ValueError("One of structure, plan or image must be provided.")


def resolve_dxf_mode(parsed: dict) -> str:
    """Decide whether to use mask_regions or structural DXF generation."""
    infer_result = parsed.get("_infer_result") or {}
    source = infer_result.get("source", "")
    supports_mask_regions = (
        source in (MITUNET_BACKEND, ENSEMBLE_BACKEND)
        and "_wall_mask" in infer_result
    )
    return "mask_regions" if supports_mask_regions else "structural"
