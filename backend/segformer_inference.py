"""
segformer_inference.py — SegFormer model inference for floor plan segmentation.

Replaces CubiCasa's get_polygons() with direct mask-to-structure extraction
using OpenCV morphology, skeletonization, and HoughLines.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

SEGFORMER_BACKEND = "segformer_local"

_WEIGHTS_V1 = Path(r"D:\training_v2\segformer_runs\checkpoints\best_inference.pt")
_WEIGHTS_V4 = Path(r"D:\training_v2\segformer_runs_v4\checkpoints\best_inference.pt")
_IMAGE_SIZE = 512
_NUM_CLASSES = 14

# Class IDs matching training/convert_labels_segformer.py
_WALL = 2
_WINDOW = 12
_DOOR = 13

# Lazy-loaded globals per variant
_models: dict[str, Any] = {}
_device = None


def segformer_available() -> tuple[bool, str | None]:
    if not _WEIGHTS_V1.exists() and not _WEIGHTS_V4.exists():
        return False, f"No weights found: {_WEIGHTS_V1} or {_WEIGHTS_V4}"
    try:
        import torch
        from transformers import SegformerForSemanticSegmentation
        return True, None
    except ImportError as e:
        return False, str(e)


def _load_model(variant: str = "v4"):
    global _device
    if variant in _models:
        return _models[variant], _device

    import torch
    from transformers import SegformerForSemanticSegmentation
    from training.convert_labels_segformer import MERGED_CLASSES

    _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    weights_path = _WEIGHTS_V1 if variant == "v1" else _WEIGHTS_V4

    id2label = {i: name for i, name in MERGED_CLASSES.items()}
    label2id = {name: i for i, name in MERGED_CLASSES.items()}

    model = SegformerForSemanticSegmentation.from_pretrained(
        "nvidia/mit-b2",
        num_labels=_NUM_CLASSES,
        id2label=id2label,
        label2id=label2id,
        ignore_mismatched_sizes=True,
    )

    checkpoint = torch.load(str(weights_path), map_location=_device, weights_only=False)
    model.load_state_dict(checkpoint["model_state"])
    model.to(_device)
    model.eval()
    _models[variant] = model
    print(f"[SegFormer] Model {variant} loaded on {_device}", flush=True)
    return model, _device


# ---------------------------------------------------------------------------
# ImageNet normalization
# ---------------------------------------------------------------------------
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _preprocess(image_bgr: np.ndarray) -> tuple[Any, int, int, float, float]:
    """Resize, normalize, and convert to tensor."""
    import torch

    orig_h, orig_w = image_bgr.shape[:2]
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(rgb, (_IMAGE_SIZE, _IMAGE_SIZE), interpolation=cv2.INTER_AREA)

    # Normalize
    img = resized.astype(np.float32) / 255.0
    img = (img - _MEAN) / _STD

    # To tensor (1, 3, H, W)
    tensor = torch.from_numpy(img.transpose(2, 0, 1)).unsqueeze(0)
    scale_x = orig_w / _IMAGE_SIZE
    scale_y = orig_h / _IMAGE_SIZE
    return tensor, orig_h, orig_w, scale_x, scale_y


def _predict(tensor: Any, variant: str = "v4") -> np.ndarray:
    """Run model and return class prediction mask at original scale."""
    import torch
    import torch.nn.functional as F

    model, device = _load_model(variant)
    tensor = tensor.to(device)

    with torch.no_grad():
        outputs = model(pixel_values=tensor)
        logits = outputs.logits  # (1, num_classes, H/4, W/4)

        # Upsample to input size
        upsampled = F.interpolate(
            logits, size=(_IMAGE_SIZE, _IMAGE_SIZE), mode="bilinear", align_corners=False
        )
        pred = upsampled.argmax(dim=1).squeeze(0).cpu().numpy()  # (H, W)

    return pred.astype(np.uint8)


# ---------------------------------------------------------------------------
# Mask → Structure extraction (replaces get_polygons)
# ---------------------------------------------------------------------------

def _extract_wall_segments(wall_mask: np.ndarray, orig_h: int, orig_w: int, scale_x: float, scale_y: float) -> list[dict]:
    """Extract wall line segments from binary wall mask — H, V, and diagonal."""
    from skimage.morphology import skeletonize

    # Morphological cleanup: close small gaps, remove noise
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    clean = cv2.morphologyEx(wall_mask, cv2.MORPH_CLOSE, kernel, iterations=3)
    clean = cv2.morphologyEx(clean, cv2.MORPH_OPEN, kernel, iterations=1)

    # Dilate slightly to connect near-miss walls
    clean = cv2.dilate(clean, kernel, iterations=1)

    # Skeletonize to centerlines
    skeleton = skeletonize(clean > 0).astype(np.uint8) * 255

    # Detect line segments — lower threshold + longer gap tolerance = more walls
    lines = cv2.HoughLinesP(skeleton, rho=1, theta=np.pi / 180,
                            threshold=8,       # lower = detect more lines
                            minLineLength=6,   # lower = detect shorter walls
                            maxLineGap=12)     # higher = bridge more gaps

    walls = []
    if lines is None:
        return walls

    wall_id = 0
    for line in lines:
        x1, y1, x2, y2 = line[0]

        # Scale back to original image coordinates
        sx1, sy1 = x1 * scale_x, y1 * scale_y
        sx2, sy2 = x2 * scale_x, y2 * scale_y

        dx = abs(sx2 - sx1)
        dy = abs(sy2 - sy1)
        length = np.sqrt((sx2 - sx1) ** 2 + (sy2 - sy1) ** 2)

        if length < 4:
            continue  # Too small

        # Determine orientation — snap near-H/V but KEEP diagonals
        angle = np.degrees(np.arctan2(dy, dx))
        if angle < 8:
            orientation = "horizontal"
            avg_y = (sy1 + sy2) / 2
            sy1 = sy2 = avg_y
        elif angle > 82:
            orientation = "vertical"
            avg_x = (sx1 + sx2) / 2
            sx1 = sx2 = avg_x
        else:
            # Diagonal — keep as-is
            orientation = "diagonal"

        # Flip Y for CAD coordinates (origin bottom-left)
        cad_y1 = orig_h - sy1
        cad_y2 = orig_h - sy2

        wall_id += 1
        walls.append({
            "id": f"sf-wall-{wall_id:04d}",
            "orientation": orientation,
            "polyline": [
                {"x": round(float(sx1), 1), "y": round(float(cad_y1), 1)},
                {"x": round(float(sx2), 1), "y": round(float(cad_y2), 1)},
            ],
            "thickness": 4.0,
            "is_exterior": False,
            "confidence": 0.8,
        })

    # Merge nearby parallel segments to reduce clutter
    walls = _merge_nearby_walls(walls)

    return walls


def _merge_nearby_walls(walls: list[dict], dist_threshold: float = 8.0) -> list[dict]:
    """Merge wall segments that are very close and roughly parallel."""
    if len(walls) <= 1:
        return walls

    merged = []
    used = set()

    for i, w1 in enumerate(walls):
        if i in used:
            continue
        p1a = w1["polyline"][0]
        p1b = w1["polyline"][1]
        cx1 = (p1a["x"] + p1b["x"]) / 2
        cy1 = (p1a["y"] + p1b["y"]) / 2

        best_merge = None
        best_dist = dist_threshold

        for j, w2 in enumerate(walls):
            if j <= i or j in used:
                continue
            if w1["orientation"] != w2["orientation"]:
                continue

            p2a = w2["polyline"][0]
            p2b = w2["polyline"][1]
            cx2 = (p2a["x"] + p2b["x"]) / 2
            cy2 = (p2a["y"] + p2b["y"]) / 2

            dist = np.sqrt((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2)
            if dist < best_dist:
                best_dist = dist
                best_merge = j

        if best_merge is not None:
            # Merge: take the longer segment
            w2 = walls[best_merge]
            len1 = np.sqrt((p1b["x"] - p1a["x"]) ** 2 + (p1b["y"] - p1a["y"]) ** 2)
            p2a = w2["polyline"][0]
            p2b = w2["polyline"][1]
            len2 = np.sqrt((p2b["x"] - p2a["x"]) ** 2 + (p2b["y"] - p2a["y"]) ** 2)
            merged.append(w1 if len1 >= len2 else w2)
            used.add(i)
            used.add(best_merge)
        else:
            merged.append(w1)
            used.add(i)

    return merged


def _extract_openings(mask: np.ndarray, kind: str, orig_h: int, orig_w: int,
                      scale_x: float, scale_y: float, walls: list[dict]) -> list[dict]:
    """Extract door/window openings from binary mask."""
    # Find connected components
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)

    openings = []
    opening_id = 0

    for i in range(1, num_labels):  # Skip background (0)
        area = stats[i, cv2.CC_STAT_AREA]
        if area < 20:  # Too small = noise
            continue

        cx, cy = centroids[i]
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]

        # Scale to original coordinates
        scx = cx * scale_x
        scy_img = cy * scale_y
        scy_cad = orig_h - scy_img  # Flip Y
        span = max(w * scale_x, h * scale_y)
        orientation = "horizontal" if w > h else "vertical"

        # Find nearest wall
        best_wall_id = None
        best_dist = float("inf")
        for wall in walls:
            p1 = wall["polyline"][0]
            p2 = wall["polyline"][1]
            wmx = (p1["x"] + p2["x"]) / 2
            wmy = (p1["y"] + p2["y"]) / 2
            dist = np.sqrt((scx - wmx) ** 2 + (scy_cad - wmy) ** 2)
            if dist < best_dist:
                best_dist = dist
                best_wall_id = wall["id"]

        opening_id += 1
        openings.append({
            "id": f"sf-{kind}-{opening_id:04d}",
            "kind": kind,
            "wall_id": best_wall_id,
            "position": {"x": round(float(scx), 1), "y": round(float(scy_cad), 1)},
            "span": round(float(span), 1),
            "orientation": orientation,
            "confidence": 0.7,
            "swing": "left" if kind == "door" else None,
            "door_type": "normal" if kind == "door" else None,
        })

    return openings


def _mask_to_structure(pred_mask: np.ndarray, orig_h: int, orig_w: int,
                       scale_x: float, scale_y: float) -> tuple[list, list]:
    """Convert SegFormer prediction mask to walls + openings."""
    wall_mask = (pred_mask == _WALL).astype(np.uint8)
    door_mask = (pred_mask == _DOOR).astype(np.uint8)
    window_mask = (pred_mask == _WINDOW).astype(np.uint8)

    walls = _extract_wall_segments(wall_mask, orig_h, orig_w, scale_x, scale_y)
    doors = _extract_openings(door_mask, "door", orig_h, orig_w, scale_x, scale_y, walls)
    windows = _extract_openings(window_mask, "window", orig_h, orig_w, scale_x, scale_y, walls)

    return walls, doors + windows


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def infer_segformer(image_b64_or_array, **kwargs) -> dict[str, Any]:
    """Run SegFormer inference on a floor plan image."""
    from .image_utils import decode_image

    variant = kwargs.get("segformer_variant", "v4")
    t0 = time.time()

    # Decode image
    if isinstance(image_b64_or_array, np.ndarray):
        image_bgr = image_b64_or_array
    else:
        image_bgr = decode_image(image_b64_or_array)

    orig_h, orig_w = image_bgr.shape[:2]

    # Preprocess
    tensor, _, _, scale_x, scale_y = _preprocess(image_bgr)

    # Predict
    t_model = time.time()
    pred_mask = _predict(tensor, variant=variant)
    model_time = time.time() - t_model

    # Extract structure
    t_post = time.time()
    walls, openings = _mask_to_structure(pred_mask, orig_h, orig_w, scale_x, scale_y)
    post_time = time.time() - t_post

    total_time = time.time() - t0

    print(f"[SegFormer] model={model_time:.2f}s post={post_time:.2f}s total={total_time:.2f}s "
          f"walls={len(walls)} openings={len(openings)}", flush=True)

    return {
        "model": "SegFormer-B2",
        "source": "segformer_local:mit-b2",
        "walls": walls,
        "openings": openings,
        "structure_meta": {
            "image_size": {"width": orig_w, "height": orig_h},
            "scale_status": "unverified",
            "unit": "pixel",
        },
        "inference_debug": {
            "backend": SEGFORMER_BACKEND,
            "model_variant": "segformer",
            "raw_wall_count": len(walls),
            "raw_opening_count": len(openings),
            "inference_time_ms": round(total_time * 1000),
        },
    }
