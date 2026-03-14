"""
cubicasa_inference.py
CubiCasa5k model inference for the v2 pipeline.

This module is import-safe in environments that do not have the model runtime
dependencies installed. Torch/floortrans are imported lazily inside the
inference path so the API and test suite can still start.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .image_utils import decode_image

ROOT_DIR = Path(__file__).resolve().parent.parent

# Add CubiCasa5k repo to path for model + post-processing imports.
_CUBICASA_ROOT = Path(__file__).resolve().parent.parent.parent / "floorplan-research" / "CubiCasa5k"
if str(_CUBICASA_ROOT) not in sys.path:
    sys.path.insert(0, str(_CUBICASA_ROOT))

CUBICASA_BACKEND = "cubicasa_local"
_WEIGHTS_PATH = _CUBICASA_ROOT / "model_best_val_loss_var.pkl"
_EXPERIMENTAL_WEIGHTS_PATH = ROOT_DIR / "data" / "training" / "checkpoints" / "cubicasa_experimental.pt"
_N_CLASSES = 44
_SPLIT = [21, 12, 11]  # heatmaps, rooms, icons
_PAD_MULTIPLE = 16     # conv layers need input divisible by 16
_MAX_MODEL_SIDE = int(os.getenv("POINTAI_CUBICASA_MAX_SIDE", "768"))
_OPENING_ICON_CLASSES = {1: "window", 2: "door"}
_DEFAULT_VARIANT = "baseline"
_MODEL_VARIANTS = {
    "baseline": {
        "label": "Baseline",
        "weights_path": _WEIGHTS_PATH,
        "model_name": "CubiCasa5k Baseline",
    },
    "experimental": {
        "label": "Experimental",
        "weights_path": _EXPERIMENTAL_WEIGHTS_PATH,
        "model_name": "CubiCasa5k Experimental",
    },
}

_models: dict[tuple[str, str], Any] = {}
_torch: Any | None = None
_hg_furukawa_original: Any | None = None
_get_polygons: Any | None = None


def cubicasa_available(model_variant: str | None = None) -> tuple[bool, str | None]:
    """Return whether CubiCasa can run in the current environment."""
    variant = resolve_model_variant(model_variant)
    weights_path = _variant_config(variant)["weights_path"]
    if not weights_path.exists():
        return False, f"CubiCasa weights not found at {weights_path}"

    try:
        importlib.import_module("torch")
    except Exception as exc:  # pragma: no cover - depends on local env
        return False, f"torch unavailable: {exc}"

    try:
        importlib.import_module("floortrans.models.hg_furukawa_original")
        importlib.import_module("floortrans.post_prosessing")
    except Exception as exc:  # pragma: no cover - depends on local env
        return False, f"floortrans unavailable: {exc}"

    return True, None


def available_model_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    for name, config in _MODEL_VARIANTS.items():
        weights_path: Path = config["weights_path"]
        variants.append(
            {
                "name": name,
                "label": config["label"],
                "available": weights_path.exists(),
                "weights_path": str(weights_path),
            }
        )
    return variants


def resolve_model_variant(model_variant: str | None) -> str:
    if not model_variant:
        return _DEFAULT_VARIANT
    normalized = str(model_variant).strip().lower()
    if normalized not in _MODEL_VARIANTS:
        raise ValueError(
            f"Unsupported CubiCasa model variant: {model_variant}. "
            f"Supported variants: {sorted(_MODEL_VARIANTS)}"
        )
    return normalized


def infer_cubicasa(image_b64: str, *, model_variant: str | None = None) -> dict[str, Any]:
    """Run CubiCasa5k inference on a base64-encoded floor plan image."""
    variant = resolve_model_variant(model_variant)
    ready, reason = cubicasa_available(variant)
    if not ready:
        raise ValueError(reason or "CubiCasa runtime is not available.")

    torch, _, get_polygons = _load_runtime_dependencies()
    device = _runtime_device()
    model = _load_model(variant, device)
    image = decode_image(image_b64)
    orig_h, orig_w = image.shape[:2]
    model_image, scale_x, scale_y = _resize_for_inference(image)
    model_h, model_w = model_image.shape[:2]

    # Preprocess: convert BGR to RGB, normalize to [-1, 1], pad to multiple of 16.
    rgb = cv2.cvtColor(model_image, cv2.COLOR_BGR2RGB)
    fplan = np.moveaxis(rgb, -1, 0).astype(np.float32)
    fplan = 2.0 * (fplan / 255.0) - 1.0

    h, w = fplan.shape[1], fplan.shape[2]
    pad_h = (_PAD_MULTIPLE - h % _PAD_MULTIPLE) % _PAD_MULTIPLE
    pad_w = (_PAD_MULTIPLE - w % _PAD_MULTIPLE) % _PAD_MULTIPLE
    if pad_h or pad_w:
        fplan = np.pad(fplan, ((0, 0), (0, pad_h), (0, pad_w)), mode="constant", constant_values=-1)

    tensor = torch.from_numpy(fplan).unsqueeze(0).to(device)

    # Single forward pass only. Rotational TTA needs channel remapping first.
    with torch.inference_mode():
        predictions = model(tensor).squeeze(0)

    heatmaps, rooms, icons = _split_predictions(predictions)
    polygons, types, _, room_types = get_polygons(
        (heatmaps, rooms, icons),
        threshold=0.2,
        all_opening_types=list(_OPENING_ICON_CLASSES),
    )

    polygons = _rescale_polygons(polygons, scale_x=scale_x, scale_y=scale_y)
    walls, openings = _polygons_to_structure(polygons, types, orig_h)
    model_name = _variant_config(variant)["model_name"]

    return {
        "model": model_name,
        "source": f"cubicasa5k:{variant}",
        "walls": walls,
        "openings": openings,
        "structure_meta": {
            "image_size": {"width": orig_w, "height": orig_h},
            "scale_status": "unverified",
            "unit": "pixel",
        },
        "inference_debug": {
            "backend": CUBICASA_BACKEND,
            "raw_wall_count": sum(1 for item in types if item.get("type") == "wall"),
            "raw_opening_count": sum(1 for item in types if _is_opening_type(item)),
            "raw_icon_count": sum(1 for item in types if item.get("type") == "icon"),
            "room_count": len(room_types),
            "model": "cubicasa5k",
            "model_variant": variant,
            "runtime_device": str(device),
            "input_image_size": {"width": orig_w, "height": orig_h},
            "model_image_size": {"width": model_w, "height": model_h},
            "resize_scale_x": scale_x,
            "resize_scale_y": scale_y,
        },
    }


def _load_runtime_dependencies() -> tuple[Any, Any, Any]:
    global _torch, _hg_furukawa_original, _get_polygons
    if _torch is None:
        _torch = importlib.import_module("torch")
    if _hg_furukawa_original is None:
        module = importlib.import_module("floortrans.models.hg_furukawa_original")
        _hg_furukawa_original = module.hg_furukawa_original
    if _get_polygons is None:
        module = importlib.import_module("floortrans.post_prosessing")
        _get_polygons = module.get_polygons
    return _torch, _hg_furukawa_original, _get_polygons


def _variant_config(model_variant: str) -> dict[str, Any]:
    return _MODEL_VARIANTS[model_variant]


def _load_model(model_variant: str, device: Any) -> Any:
    cache_key = (model_variant, str(device))
    if cache_key in _models:
        return _models[cache_key]

    config = _variant_config(model_variant)
    weights_path: Path = config["weights_path"]
    torch, hg_furukawa_original, _ = _load_runtime_dependencies()
    model = hg_furukawa_original(n_classes=_N_CLASSES)
    checkpoint = torch.load(str(weights_path), map_location=device, weights_only=False)
    model.load_state_dict(_extract_state_dict(checkpoint))
    model = model.to(device)
    model.eval()
    _models[cache_key] = model
    return model


def _runtime_device() -> Any:
    torch, _, _ = _load_runtime_dependencies()
    if torch.cuda.is_available():
        torch.backends.cudnn.benchmark = True
        return torch.device("cuda")
    return torch.device("cpu")


def _resize_for_inference(image: np.ndarray) -> tuple[np.ndarray, float, float]:
    height, width = image.shape[:2]
    longest_side = max(height, width)
    if longest_side <= _MAX_MODEL_SIDE:
        return image, 1.0, 1.0

    scale = _MAX_MODEL_SIDE / float(longest_side)
    resized_width = max(1, round(width * scale))
    resized_height = max(1, round(height * scale))
    resized = cv2.resize(image, (resized_width, resized_height), interpolation=cv2.INTER_AREA)
    scale_x = width / float(resized_width)
    scale_y = height / float(resized_height)
    return resized, scale_x, scale_y


def _rescale_polygons(polygons: np.ndarray, *, scale_x: float, scale_y: float) -> np.ndarray:
    if scale_x == 1.0 and scale_y == 1.0:
        return polygons
    scaled = polygons.astype(np.float32).copy()
    scaled[:, :, 0] *= scale_x
    scaled[:, :, 1] *= scale_y
    return scaled


def _extract_state_dict(checkpoint: Any) -> dict[str, Any]:
    if isinstance(checkpoint, dict):
        if "model_state" in checkpoint:
            return checkpoint["model_state"]
        if "state_dict" in checkpoint:
            return checkpoint["state_dict"]
    if hasattr(checkpoint, "keys"):
        return checkpoint
    raise ValueError("Unsupported CubiCasa checkpoint format.")


def _predict_with_tta(model: Any, tensor: Any) -> Any:
    """Run inference with 4 90-degree rotations and average the results."""
    torch, _, _ = _load_runtime_dependencies()
    predictions = []
    for rot in range(4):
        rotated = torch.rot90(tensor, rot, [2, 3])
        out = model(rotated)
        out = torch.rot90(out, -rot, [2, 3])
        predictions.append(out)
    return torch.stack(predictions).mean(dim=0).squeeze(0)


def _split_predictions(predictions: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Split the 44-channel prediction into heatmaps(21), rooms(12), icons(11)."""
    pred = predictions.detach().cpu().numpy()

    heatmaps = pred[:_SPLIT[0]]
    rooms_logits = pred[_SPLIT[0]:_SPLIT[0] + _SPLIT[1]]
    icons_logits = pred[_SPLIT[0] + _SPLIT[1]:]

    rooms = _softmax_np(rooms_logits)
    icons = _softmax_np(icons_logits)
    return heatmaps, rooms, icons


def _softmax_np(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max(axis=0, keepdims=True))
    return e / e.sum(axis=0, keepdims=True)


def _polygons_to_structure(
    polygons: np.ndarray,
    types: list[dict[str, Any]],
    image_height: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert CubiCasa polygons to the v2 walls/openings contract."""
    walls: list[dict[str, Any]] = []
    openings: list[dict[str, Any]] = []
    wall_counter = 0
    opening_counter = 0

    for polygon, ptype in zip(polygons, types):
        flipped = polygon.astype(float)
        flipped[:, 1] = image_height - flipped[:, 1]

        kind = ptype.get("type", "")
        cls = int(ptype.get("class", 0))

        if kind == "wall":
            wall_counter += 1
            wall = _polygon_to_wall(flipped, wall_counter)
            if wall is not None:
                walls.append(wall)
            continue

        if not _is_opening_type(ptype):
            continue

        opening_counter += 1
        opening = _polygon_to_opening(flipped, cls, opening_counter, walls)
        if opening is not None:
            openings.append(opening)

    return walls, openings


def _is_opening_type(ptype: dict[str, Any]) -> bool:
    kind = ptype.get("type")
    cls = int(ptype.get("class", 0))
    return kind == "opening" or (kind == "icon" and cls in _OPENING_ICON_CLASSES)


def _polygon_to_wall(polygon: np.ndarray, counter: int) -> dict[str, Any] | None:
    xs = polygon[:, 0]
    ys = polygon[:, 1]
    x_span = xs.max() - xs.min()
    y_span = ys.max() - ys.min()

    if x_span < 2 and y_span < 2:
        return None

    if x_span >= y_span:
        orientation = "horizontal"
        coord = float((ys.min() + ys.max()) / 2)
        start = float(xs.min())
        end = float(xs.max())
        thickness = float(y_span)
        polyline = [{"x": start, "y": coord}, {"x": end, "y": coord}]
    else:
        orientation = "vertical"
        coord = float((xs.min() + xs.max()) / 2)
        start = float(ys.min())
        end = float(ys.max())
        thickness = float(x_span)
        polyline = [{"x": coord, "y": start}, {"x": coord, "y": end}]

    return {
        "id": f"cubi-wall-{counter:04d}",
        "orientation": orientation,
        "polyline": polyline,
        "thickness": max(thickness, 1.0),
        "is_exterior": False,
        "confidence": 0.85,
    }


def _polygon_to_opening(
    polygon: np.ndarray,
    cls: int,
    counter: int,
    walls: list[dict[str, Any]],
) -> dict[str, Any] | None:
    xs = polygon[:, 0]
    ys = polygon[:, 1]
    cx = float((xs.min() + xs.max()) / 2)
    cy = float((ys.min() + ys.max()) / 2)
    x_span = float(xs.max() - xs.min())
    y_span = float(ys.max() - ys.min())

    if x_span < 2 and y_span < 2:
        return None

    kind = _OPENING_ICON_CLASSES.get(cls, "door")
    span = max(x_span, y_span)
    orientation = "horizontal" if x_span >= y_span else "vertical"

    best_wall_id = None
    best_dist = float("inf")
    for wall in walls:
        p0 = wall["polyline"][0]
        p1 = wall["polyline"][1]
        wall_cx = (p0["x"] + p1["x"]) / 2
        wall_cy = (p0["y"] + p1["y"]) / 2
        dist = abs(cx - wall_cx) + abs(cy - wall_cy)
        if dist < best_dist:
            best_dist = dist
            best_wall_id = wall["id"]

    opening = {
        "id": f"cubi-opening-{counter:04d}",
        "kind": kind,
        "wall_id": best_wall_id,
        "position": {"x": cx, "y": cy},
        "span": span,
        "orientation": orientation,
        "confidence": 0.8,
    }

    if kind == "door":
        opening["door_type"] = "normal"
        opening["swing"] = None

    return opening
