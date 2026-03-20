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

_WEIGHTS_PATH = Path(r"D:\training_v2\segformer_runs\checkpoints\best_inference.pt")
_IMAGE_SIZE = 512
_NUM_CLASSES = 14

# Class IDs matching training/convert_labels_segformer.py
_WALL = 2
_WINDOW = 12
_DOOR = 13

# Lazy-loaded globals
_model = None
_device = None


def segformer_available() -> tuple[bool, str | None]:
    if not _WEIGHTS_PATH.exists():
        return False, f"Weights not found: {_WEIGHTS_PATH}"
    try:
        import torch
        from transformers import SegformerForSemanticSegmentation
        return True, None
    except ImportError as e:
        return False, str(e)


def _load_model():
    global _model, _device
    if _model is not None:
        return _model, _device

    import torch
    from transformers import SegformerForSemanticSegmentation
    from training.convert_labels_segformer import MERGED_CLASSES

    _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    id2label = {i: name for i, name in MERGED_CLASSES.items()}
    label2id = {name: i for i, name in MERGED_CLASSES.items()}

    _model = SegformerForSemanticSegmentation.from_pretrained(
        "nvidia/mit-b2",
        num_labels=_NUM_CLASSES,
        id2label=id2label,
        label2id=label2id,
        ignore_mismatched_sizes=True,
    )

    checkpoint = torch.load(str(_WEIGHTS_PATH), map_location=_device, weights_only=False)
    _model.load_state_dict(checkpoint["model_state"])
    _model.to(_device)
    _model.eval()
    print(f"[SegFormer] Model loaded on {_device}", flush=True)
    return _model, _device


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


def _predict(tensor: Any) -> np.ndarray:
    """Run model and return class prediction mask at original scale."""
    import torch
    import torch.nn.functional as F

    model, device = _load_model()
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
    """Extract wall line segments from binary wall mask."""
    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    clean = cv2.morphologyEx(wall_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    clean = cv2.morphologyEx(clean, cv2.MORPH_OPEN, kernel, iterations=1)

    # Skeletonize
    from skimage.morphology import skeletonize
    skeleton = skeletonize(clean > 0).astype(np.uint8) * 255

    # Detect line segments
    lines = cv2.HoughLinesP(skeleton, rho=1, theta=np.pi / 180, threshold=15,
                            minLineLength=10, maxLineGap=8)

    walls = []
    if lines is None:
        return walls

    wall_id = 0
    for line in lines:
        x1, y1, x2, y2 = line[0]

        # Scale back to original image coordinates
        sx1, sy1 = x1 * scale_x, y1 * scale_y
        sx2, sy2 = x2 * scale_x, y2 * scale_y

        # Determine orientation
        dx = abs(sx2 - sx1)
        dy = abs(sy2 - sy1)

        if dx < 3 and dy < 3:
            continue  # Too small

        # Snap to H/V if close (within 15 degrees)
        angle = np.degrees(np.arctan2(dy, dx))
        if angle < 15:
            orientation = "horizontal"
            avg_y = (sy1 + sy2) / 2
            sy1 = sy2 = avg_y
        elif angle > 75:
            orientation = "vertical"
            avg_x = (sx1 + sx2) / 2
            sx1 = sx2 = avg_x
        else:
            orientation = "horizontal" if dx > dy else "vertical"

        # Flip Y for CAD coordinates (origin bottom-left)
        cad_y1 = orig_h - sy1
        cad_y2 = orig_h - sy2

        length = np.sqrt((sx2 - sx1) ** 2 + (cad_y2 - cad_y1) ** 2)
        if length < 5:
            continue

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

    return walls


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
    pred_mask = _predict(tensor)
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
