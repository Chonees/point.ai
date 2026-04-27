"""
ensemble_inference.py -- Ensemble: MitUNet walls + CubiCasa doors/windows.

Runs both models on the same image, takes walls from MitUNet (87.84% mIoU)
and openings from CubiCasa (heatmaps + icons), re-anchors CubiCasa openings
to MitUNet wall geometry, and converts them to annotation format for the
mask_regions DXF pipeline.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .mitunet_inference import infer_mitunet, mitunet_available
from .cubicasa_inference import cubicasa_available, infer_cubicasa
from .observability import log_event
from .structure_postprocess import (
    _anchor_openings,
    _deduplicate_openings,
    _limit_exterior_wall_windows,
    _normalize_wall_geometry,
    _resolve_postprocess_config,
)

ENSEMBLE_BACKEND = "ensemble_local"

# Max Manhattan distance (image pixels) between an opening center and the
# nearest MitUNet wall midpoint.  Openings farther than this are dropped as
# likely CubiCasa false positives in areas where MitUNet saw no wall.
_MAX_OPENING_WALL_DISTANCE = 80


def ensemble_available() -> tuple[bool, str | None]:
    """Ensemble requires both MitUNet (walls) and CubiCasa (doors/windows)."""
    mitu_ready, mitu_reason = mitunet_available()
    if not mitu_ready:
        return False, f"MitUNet unavailable: {mitu_reason}"
    cubi_ready, cubi_reason = cubicasa_available()
    if not cubi_ready:
        return False, f"CubiCasa unavailable: {cubi_reason}"
    return True, None


def infer_ensemble(
    image_b64: str,
    *,
    cubicasa_model_variant: str | None = None,
) -> dict[str, Any]:
    """Run ensemble inference: MitUNet for walls, CubiCasa for openings."""
    t0 = time.time()

    # --- Steps 1 & 2: Run both models in parallel ---
    with ThreadPoolExecutor(max_workers=2) as pool:
        mitunet_future = pool.submit(infer_mitunet, image_b64)
        cubicasa_future = pool.submit(
            infer_cubicasa, image_b64, model_variant=cubicasa_model_variant,
        )
        mitunet_result = mitunet_future.result()
        cubi_result = cubicasa_future.result()

    h, w = mitunet_result["_image_shape"]
    mitunet_walls = mitunet_result["walls"]
    normalized_mitunet_walls = [_normalize_wall_geometry(wall) for wall in mitunet_walls]
    cubicasa_openings = cubi_result.get("openings", [])
    cubicasa_debug = {
        "raw_opening_count": len(cubicasa_openings),
        "cubicasa_wall_count": len(cubi_result.get("walls", [])),
    }

    config = _resolve_postprocess_config(mitunet_result.get("structure_meta") or {})

    # --- Step 3: Anchor semantics (side/swing/defaults) onto MitUNet walls ---
    review_flags: list[str] = []
    wall_map = {wall["id"]: wall for wall in normalized_mitunet_walls}
    anchored_openings, opening_metrics = _anchor_openings(
        cubicasa_openings,
        normalized_mitunet_walls,
        wall_map,
        review_flags,
        config=config,
    )

    # --- Step 4: Deduplicate + cap after openings are anchored structurally ---
    deduplicated, duplicate_removed_count = _deduplicate_openings(anchored_openings, normalized_mitunet_walls)
    filtered, excess_window_removed_count = _limit_exterior_wall_windows(deduplicated, normalized_mitunet_walls)

    # --- Step 5: Convert to annotation format for mask_regions DXF ---
    auto_annotations = _openings_to_annotations(filtered, image_height=h)

    elapsed = time.time() - t0
    log_event(
        "ensemble.infer.done",
        wall_count=len(mitunet_walls),
        opening_count=len(cubicasa_openings),
        anchored_count=len(anchored_openings),
        deduplicated_count=len(deduplicated),
        filtered_count=len(filtered),
        annotation_count=len(auto_annotations),
        elapsed=round(elapsed, 2),
    )

    return {
        "walls": mitunet_walls,
        "openings": filtered,
        "rooms": [],
        "source": ENSEMBLE_BACKEND,
        "_wall_mask": mitunet_result["_wall_mask"],
        "_image_shape": mitunet_result["_image_shape"],
        "_auto_annotations": auto_annotations,
        "inference_debug": {
            "backend": ENSEMBLE_BACKEND,
            "debug_overlay_b64": mitunet_result.get("inference_debug", {}).get(
                "debug_overlay_b64"
            ),
            "model_variant": "ensemble",
            "mitunet": mitunet_result.get("inference_debug", {}),
            "cubicasa": cubicasa_debug,
            "ensemble": {
                "wall_count": len(mitunet_walls),
                "cubicasa_raw_opening_count": len(cubicasa_openings),
                "anchored_opening_count": len(anchored_openings),
                "deduplicated_opening_count": len(deduplicated),
                "final_opening_count": len(filtered),
                "duplicate_removed_count": duplicate_removed_count,
                "excess_window_removed_count": excess_window_removed_count,
                "auto_annotation_count": len(auto_annotations),
                **opening_metrics,
                "review_flags": review_flags,
                "elapsed_s": round(elapsed, 2),
            },
        },
    }


def _openings_to_annotations(
    openings: list[dict[str, Any]],
    *,
    image_height: int,
) -> list[dict[str, Any]]:
    """Convert CubiCasa openings (Y-flipped) to annotation format (Y-down).

    Structured openings:
      position.x, position.y  -- Y-flipped (Y goes up)
      span, orientation, kind, side, swing

    Annotations (standard image coords, Y goes down):
      {type, x1, y1, x2, y2, swing?}
    """
    annotations: list[dict[str, Any]] = []

    for opening in openings:
        kind = opening.get("kind", "door")
        if kind not in ("door", "window"):
            continue

        pos = opening.get("position") or {}
        cx_flipped = float(pos.get("x", 0))
        cy_flipped = float(pos.get("y", 0))
        span = float(opening.get("span", 0))
        orientation = opening.get("orientation", "horizontal")

        # Y-flipped -> image coords: image_y = image_height - flipped_y
        cx_img = cx_flipped
        cy_img = image_height - cy_flipped
        half = span / 2.0

        if orientation == "horizontal":
            x1, y1 = cx_img - half, cy_img
            x2, y2 = cx_img + half, cy_img
        else:
            x1, y1 = cx_img, cy_img - half
            x2, y2 = cx_img, cy_img + half

        ann: dict[str, Any] = {
            "type": kind,
            "x1": round(x1, 1),
            "y1": round(y1, 1),
            "x2": round(x2, 1),
            "y2": round(y2, 1),
            "_source": "ensemble_cubicasa",
        }

        if kind == "door":
            swing = opening.get("swing")
            if swing:
                ann["swing"] = swing
        else:
            side = opening.get("side")
            swing = _window_side_to_annotation_swing(side, orientation) or opening.get("swing")
            if swing:
                ann["swing"] = swing

        annotations.append(ann)

    return annotations


def _window_side_to_annotation_swing(
    side: str | None,
    orientation: str,
) -> str | None:
    if not side:
        return None
    if orientation == "horizontal":
        return {
            "bottom": "up",
            "top": "down",
            "up": "up",
            "down": "down",
        }.get(side)
    return {
        "left": "left",
        "right": "right",
    }.get(side)
