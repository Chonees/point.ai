"""
ensemble_inference.py -- Ensemble: MitUNet walls + CubiCasa doors/windows.

Runs both models on the same image, takes walls from MitUNet (87.84% mIoU)
and openings from CubiCasa (heatmaps + icons), re-anchors CubiCasa openings
to MitUNet wall geometry, and converts them to annotation format for the
mask_regions DXF pipeline.
"""
from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .coordinate_space import DXF_COORDINATE_SPACE
from .mitunet_inference import infer_mitunet, mitunet_available
from .cubicasa_inference import cubicasa_available, infer_cubicasa
from .observability import log_event
from .structure_postprocess import anchor_openings_to_walls

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
    cubicasa_openings = cubi_result.get("openings", [])
    cubicasa_debug = {
        "raw_opening_count": len(cubicasa_openings),
        "cubicasa_wall_count": len(cubi_result.get("walls", [])),
    }

    # --- Step 3: Re-anchor CubiCasa openings to MitUNet walls ---
    reanchored, reanchor_metrics = _reanchor_openings(
        cubicasa_openings,
        mitunet_walls,
        image_height=h,
        image_width=w,
    )
    cubicasa_debug["reanchor_filtered_opening_count"] = reanchor_metrics["filtered_opening_count"]
    cubicasa_debug["reanchor_review_flags"] = reanchor_metrics["review_flags"]

    # --- Step 4: Convert to annotation format ---
    auto_annotations = _openings_to_annotations(reanchored, image_height=h)

    elapsed = time.time() - t0
    log_event(
        "ensemble.infer.done",
        wall_count=len(mitunet_walls),
        opening_count=len(cubicasa_openings),
        reanchored_count=len(reanchored),
        annotation_count=len(auto_annotations),
        elapsed=round(elapsed, 2),
    )

    return {
        "walls": mitunet_walls,
        "openings": [],
        "rooms": [],
        "source": ENSEMBLE_BACKEND,
        "structure_meta": {
            "image_size": {"width": w, "height": h},
            "scale_status": "unverified",
            "unit": "pixel",
            "coordinate_space": DXF_COORDINATE_SPACE,
        },
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
                "reanchored_opening_count": len(reanchored),
                "auto_annotation_count": len(auto_annotations),
                "elapsed_s": round(elapsed, 2),
            },
        },
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _reanchor_openings(
    cubicasa_openings: list[dict[str, Any]],
    mitunet_walls: list[dict[str, Any]],
    *,
    image_height: int,
    image_width: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Re-anchor each CubiCasa opening to the nearest MitUNet wall.

    Both coordinate systems are Y-flipped image pixels (Y goes up).
    MitUNet wall polylines: ``[[x, y], [x, y]]`` (list-of-lists).
    CubiCasa opening positions: ``{"x": cx, "y": cy}`` (dict).
    """
    if not mitunet_walls or not cubicasa_openings:
        return [], {
            "filtered_opening_count": 0,
            "inferred_opening_side_count": 0,
            "review_flags": [],
        }

    anchored, metrics = anchor_openings_to_walls(
        cubicasa_openings,
        mitunet_walls,
        structure_meta={
            "image_size": {"width": image_width, "height": image_height},
            "unit": "pixel",
            "scale_status": "unverified",
        },
    )

    max_axis_distance = max(float(_MAX_OPENING_WALL_DISTANCE), 1.0)
    wall_map = {wall["id"]: wall for wall in mitunet_walls}
    filtered: list[dict[str, Any]] = []
    extra_filtered = 0
    for opening in anchored:
        wall = wall_map.get(opening.get("wall_id"))
        if wall is None:
            extra_filtered += 1
            continue

        position = opening.get("position") or {}
        wall_start = wall["polyline"][0]
        wall_axis_x = float(wall_start["x"]) if isinstance(wall_start, dict) else float(wall_start[0])
        wall_axis_y = float(wall_start["y"]) if isinstance(wall_start, dict) else float(wall_start[1])
        if opening["orientation"] == "horizontal":
            axis_distance = abs(float(position.get("y", 0.0)) - wall_axis_y)
        else:
            axis_distance = abs(float(position.get("x", 0.0)) - wall_axis_x)

        if axis_distance > max_axis_distance:
            extra_filtered += 1
            continue
        filtered.append(opening)

    if extra_filtered:
        metrics = {
            **metrics,
            "filtered_opening_count": int(metrics.get("filtered_opening_count", 0)) + extra_filtered,
            "review_flags": list(metrics.get("review_flags", []))
            + [f"Filtered {extra_filtered} opening(s): axis distance exceeded {_MAX_OPENING_WALL_DISTANCE}px."],
        }

    return filtered, metrics


def _openings_to_annotations(
    openings: list[dict[str, Any]],
    *,
    image_height: int,
) -> list[dict[str, Any]]:
    """Convert CubiCasa openings (Y-flipped) to annotation format (Y-down).

    CubiCasa openings:
      position.x, position.y  -- Y-flipped (Y goes up)
      span, orientation, kind, swing

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
            "id": str(uuid.uuid4()),
            "type": kind,
            "x1": round(x1, 1),
            "y1": round(y1, 1),
            "x2": round(x2, 1),
            "y2": round(y2, 1),
            "_source": "ensemble_cubicasa",
        }
        if opening.get("wall_id"):
            ann["wall_id"] = opening["wall_id"]
        if opening.get("side"):
            ann["side"] = opening["side"]
        if kind == "door":
            if opening.get("swing"):
                ann["swing"] = opening["swing"]
            if opening.get("door_type"):
                ann["door_type"] = opening["door_type"]

        annotations.append(ann)

    return annotations
