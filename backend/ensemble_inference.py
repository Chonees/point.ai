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
    reanchored = _reanchor_openings(cubicasa_openings, mitunet_walls, image_height=h)

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
) -> list[dict[str, Any]]:
    """Re-anchor each CubiCasa opening to the nearest MitUNet wall.

    Both coordinate systems are Y-flipped image pixels (Y goes up).
    MitUNet wall polylines: ``[[x, y], [x, y]]`` (list-of-lists).
    CubiCasa opening positions: ``{"x": cx, "y": cy}`` (dict).
    """
    if not mitunet_walls or not cubicasa_openings:
        return []

    reanchored: list[dict[str, Any]] = []

    for opening in cubicasa_openings:
        pos = opening.get("position") or {}
        cx = float(pos.get("x", 0))
        cy = float(pos.get("y", 0))

        best_wall = None
        best_dist = float("inf")

        for wall in mitunet_walls:
            poly = wall.get("polyline", [])
            if len(poly) < 2:
                continue
            p0, p1 = poly[0], poly[1]
            # MitUNet uses [[x,y],[x,y]]
            wx0, wy0 = float(p0[0]), float(p0[1])
            wx1, wy1 = float(p1[0]), float(p1[1])

            wall_cx = (wx0 + wx1) / 2
            wall_cy = (wy0 + wy1) / 2
            dist = abs(cx - wall_cx) + abs(cy - wall_cy)

            if dist < best_dist:
                best_dist = dist
                best_wall = wall

        if best_wall is not None and best_dist <= _MAX_OPENING_WALL_DISTANCE:
            anchored = dict(opening)
            anchored["wall_id"] = best_wall["id"]
            anchored["_anchor_distance"] = round(best_dist, 1)
            reanchored.append(anchored)

    return reanchored


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
            "type": kind,
            "x1": round(x1, 1),
            "y1": round(y1, 1),
            "x2": round(x2, 1),
            "y2": round(y2, 1),
            "_source": "ensemble_cubicasa",
        }
        # No swing from CubiCasa — unreliable. User sets it manually.

        annotations.append(ann)

    return annotations
