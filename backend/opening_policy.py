"""
opening_policy.py
Shared policy for disabling automatic door/window detections in image inference.
"""
from __future__ import annotations

from typing import Any

OPENING_DETECTION_REASON = "disabled_by_product_decision"


def disable_opening_detections(
    structure: dict[str, Any],
    *,
    reason: str = OPENING_DETECTION_REASON,
) -> dict[str, Any]:
    """Strip automatic openings from an inferred structure while keeping contract shape."""
    result = dict(structure)
    suppressed = len(result.get("openings") or [])

    result["openings"] = []
    if "_auto_annotations" in result:
        result["_auto_annotations"] = []

    structure_meta = dict(result.get("structure_meta") or {})
    structure_meta["opening_detection_mode"] = "disabled"
    structure_meta["opening_detection_reason"] = reason
    result["structure_meta"] = structure_meta

    inference_debug = dict(result.get("inference_debug") or {})
    inference_debug["opening_detection_disabled"] = True
    inference_debug["opening_detection_reason"] = reason
    inference_debug["suppressed_opening_count"] = suppressed
    if "raw_opening_count" in inference_debug:
        inference_debug["raw_opening_count"] = 0
    if "raw_opening_detections" in inference_debug:
        inference_debug["raw_opening_detections"] = 0
    result["inference_debug"] = inference_debug

    return result
