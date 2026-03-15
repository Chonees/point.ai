"""
r2v_inference.py
Raster-to-Vector (ICCV 2017) inference backend for Point.ai.

Paper: "Raster-to-Vector: Revisiting Floorplan Transformation"
       Chen Liu, Jiajun Wu, Pushmeet Kohli, Yasutaka Furukawa. ICCV 2017.
Code:  https://github.com/art-programmer/FloorplanTransformation

Expected layout (sibling of CubiCasa5k):
  floorplan-research/FloorplanTransformation/pytorch/           ← R2V pytorch source
  floorplan-research/FloorplanTransformation/pytorch/
    checkpoint/floorplan/checkpoint.pth                         ← pretrained weights

Setup:
  git clone https://github.com/art-programmer/FloorplanTransformation.git \\
    ../../../floorplan-research/FloorplanTransformation
  pip install pulp scikit-image
  # Download checkpoint (Google Drive ID: 1e5c7308fdoCMRv0w-XduWqyjYPV4JWHS)
  # Place at:  floorplan-research/FloorplanTransformation/pytorch/
  #            checkpoint/floorplan/checkpoint.pth
"""
from __future__ import annotations

import importlib
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .image_utils import decode_image

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_R2V_PYTORCH = (
    Path(__file__).resolve().parent.parent.parent
    / "floorplan-research"
    / "FloorplanTransformation"
    / "pytorch"
)

_WEIGHTS_PATH = _R2V_PYTORCH / "checkpoint" / "floorplan" / "checkpoint.pth"

R2V_BACKEND = "r2v_local"
_MODEL_SIZE = 256  # R2V internal inference resolution

# ---------------------------------------------------------------------------
# Module-level caches (lazy-loaded, same pattern as cubicasa_inference.py)
# ---------------------------------------------------------------------------

_model: Any | None = None
_reconstruct_fn: Any | None = None
_torch: Any | None = None
_availability_cache: dict[str, tuple[bool, str | None]] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def r2v_available() -> tuple[bool, str | None]:
    """Return (ready, reason). Mirrors cubicasa_available() interface."""
    key = "r2v"
    if key in _availability_cache:
        return _availability_cache[key]

    if not _R2V_PYTORCH.exists():
        result: tuple[bool, str | None] = (
            False,
            f"R2V pytorch folder not found at {_R2V_PYTORCH}. "
            "Clone: git clone https://github.com/art-programmer/FloorplanTransformation "
            "floorplan-research/FloorplanTransformation",
        )
        _availability_cache[key] = result
        return result

    if not _WEIGHTS_PATH.exists():
        result = (
            False,
            f"R2V weights not found at {_WEIGHTS_PATH}. "
            "Download checkpoint (Google Drive ID: 1e5c7308fdoCMRv0w-XduWqyjYPV4JWHS) "
            "and place at that path.",
        )
        _availability_cache[key] = result
        return result

    try:
        importlib.import_module("torch")
    except Exception as exc:
        result = (False, f"torch unavailable: {exc}")
        _availability_cache[key] = result
        return result

    _register_r2v_path()
    _clear_r2v_conflicts()
    try:
        importlib.import_module("models.model")
        importlib.import_module("IP")
    except Exception as exc:
        result = (
            False,
            f"R2V modules unavailable: {exc}. "
            "Ensure FloorplanTransformation/pytorch is intact.",
        )
        _availability_cache[key] = result
        return result

    try:
        importlib.import_module("pulp")
    except Exception:
        result = (
            False,
            "PuLP not installed (required by R2V IP solver). Run: pip install pulp",
        )
        _availability_cache[key] = result
        return result

    result = (True, None)
    _availability_cache[key] = result
    return result


def infer_r2v(image_b64: str) -> dict[str, Any]:
    """Run R2V inference and return a WorkerContract-compatible dict."""
    ready, reason = r2v_available()
    if not ready:
        raise ValueError(reason or "R2V is not available.")

    t0 = time.time()
    torch = _load_torch()
    device = _runtime_device(torch)
    model = _load_model(torch, device)

    image = decode_image(image_b64)
    orig_h, orig_w = image.shape[:2]

    # Convert thick-wall US/Western plan to thin-wall centerlines.
    # R2V was trained on LIFULL (thin walls); this normalizes the style.
    image_for_model = _preprocess_floorplan(image)

    # Resize with aspect ratio preserved + white-pad to 256×256.
    # NOTE: keep BGR — model was trained on cv2.imread (BGR) output.
    resized = _resize_padded(image_for_model, _MODEL_SIZE)
    tensor_np = (resized.astype(np.float32) / 255.0) - 0.5
    tensor_np = np.moveaxis(tensor_np, -1, 0)   # HWC → CHW
    tensor = torch.from_numpy(tensor_np).unsqueeze(0).float().to(device)

    with torch.inference_mode():
        corner_pred, icon_pred, room_pred = model(tensor)

    # Move to CPU numpy; apply softmax to icon/room logits.
    corner_np = corner_pred.squeeze(0).detach().cpu().numpy()  # (H, W, C)
    icon_np = (
        torch.nn.functional.softmax(icon_pred.squeeze(0), dim=-1)
        .detach().cpu().numpy()
    )
    room_np = (
        torch.nn.functional.softmax(room_pred.squeeze(0), dim=-1)
        .detach().cpu().numpy()
    )

    num_wall = _num_wall_corners()

    # Debug: log corner heatmap activation stats to help tune thresholds.
    wall_hm = corner_np[:, :, :num_wall]
    print(
        f"[R2V] wall corner heatmaps: max={wall_hm.max():.4f} "
        f"mean={wall_hm.mean():.5f} "
        f"pixels>0.5={int((wall_hm > 0.5).sum())} "
        f"pixels>0.2={int((wall_hm > 0.2).sum())} "
        f"pixels>0.1={int((wall_hm > 0.1).sum())}"
    )

    reconstruct = _load_reconstruct_fn()
    out_prefix = str(Path(tempfile.gettempdir()) / "r2v_out_")

    r2v_result = reconstruct(
        corner_np[:, :, :num_wall],
        corner_np[:, :, num_wall: num_wall + 4],
        corner_np[:, :, -4:],
        icon_np,
        room_np,
        output_prefix=out_prefix,
        gap=-1,
        distanceThreshold=-1,
        lengthThreshold=-1,
        debug_prefix="r2v",
        enableAugmentation=True,
        heatmapValueThresholdWall=0.5,
        heatmapValueThresholdDoor=0.5,
        heatmapValueThresholdIcon=0.5,
    )

    # Scale from 256×256 padded space back to original image coordinates.
    # _resize_padded scales by max(orig_h, orig_w)/256 uniformly.
    pad_scale = max(orig_h, orig_w) / float(_MODEL_SIZE)

    inference_ms = (time.time() - t0) * 1000
    walls, openings = _r2v_to_contract(r2v_result, orig_w, orig_h, pad_scale)

    return {
        "model": "R2V-ICCV2017",
        "source": "r2v_local:iccv2017",
        "walls": walls,
        "openings": openings,
        "structure_meta": {
            "image_size": {"width": orig_w, "height": orig_h},
            "scale_status": "unverified",
            "unit": "pixel",
        },
        "inference_debug": {
            "backend": R2V_BACKEND,
            "model": "r2v_iccv2017",
            "model_variant": "pretrained",
            "raw_wall_count": len(walls),
            "raw_opening_count": len(openings),
            "inference_time_ms": round(inference_ms, 1),
            "input_image_size": {"width": orig_w, "height": orig_h},
        },
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _preprocess_floorplan(image: np.ndarray) -> np.ndarray:
    """Convert thick-wall floor plan to thin-wall centerlines (LIFULL style).

    R2V was trained on Japanese LIFULL plans: thin black outlines on white bg.
    US/Western plans have thick filled walls + dense furniture/text.
    This preprocessing normalizes the input to match the training distribution.

    Steps:
      1. Grayscale + Otsu threshold → binary wall mask
      2. Morphological erosion → remove thin features (furniture, text, dims)
      3. Skeletonize → 1-pixel centerlines
      4. Output: black centerlines on white background (3-channel BGR)
    """
    from skimage.morphology import skeletonize, disk, binary_erosion

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Otsu: auto-separates walls (dark) from rooms (light)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    walls = binary.astype(bool)

    # Erosion radius: ~1.5% of min dimension removes furniture/text (<5px)
    # but keeps structural walls (typically 8-20px thick in original images)
    min_dim = min(image.shape[:2])
    radius = max(2, int(min_dim * 0.015))

    thick = binary_erosion(walls, disk(radius))

    # If erosion wiped everything out, try radius=1 (already thin-wall plan)
    if thick.sum() < 50:
        thick = binary_erosion(walls, disk(1))

    # If still nothing, image is already thin-line style — return as-is
    if thick.sum() < 20:
        return image

    skeleton = skeletonize(thick)

    # Black centerlines on white background (matches LIFULL training style)
    result = np.full((gray.shape[0], gray.shape[1], 3), 255, dtype=np.uint8)
    result[skeleton] = 0
    return result


def _resize_padded(image: np.ndarray, size: int) -> np.ndarray:
    """Resize image preserving aspect ratio, white-pad to size×size.

    Matches the R2V dataset's test-split augmentation (split != 'train' path):
      - max_size = options.width (= 256)
      - offset_x = offset_y = 0
      - background = white (255)
    """
    h, w = image.shape[:2]
    scale = size / max(h, w)
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
    canvas = np.full((size, size, 3), fill_value=255, dtype=np.uint8)
    canvas[:new_h, :new_w] = resized
    return canvas


# R2V module names that conflict with backend modules (e.g. backend/models.py,
# backend/utils.py).  We must evict any non-R2V versions from sys.modules
# before every import so Python re-resolves from _R2V_PYTORCH.
_R2V_MODULE_NAMES = {"models", "utils", "options", "IP", "datasets"}


def _register_r2v_path() -> None:
    r2v_str = str(_R2V_PYTORCH)
    if r2v_str not in sys.path:
        sys.path.insert(0, r2v_str)


def _clear_r2v_conflicts() -> None:
    """Remove non-R2V cached modules that share names with R2V packages."""
    r2v_str = str(_R2V_PYTORCH)
    for key in list(sys.modules.keys()):
        top = key.split(".")[0]
        if top not in _R2V_MODULE_NAMES:
            continue
        mod = sys.modules.get(key)
        if mod is None:
            continue
        mod_file = getattr(mod, "__file__", "") or ""
        if r2v_str not in mod_file:
            del sys.modules[key]


def _load_torch() -> Any:
    global _torch
    if _torch is None:
        _register_r2v_path()
        _torch = importlib.import_module("torch")
    return _torch


def _runtime_device(torch: Any) -> Any:
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _load_reconstruct_fn() -> Any:
    global _reconstruct_fn
    if _reconstruct_fn is None:
        _register_r2v_path()
        _clear_r2v_conflicts()
        ip = importlib.import_module("IP")
        # IP.py omits `import os` — inject it into the module namespace.
        import os as _os
        if not hasattr(ip, "os"):
            ip.os = _os
        _reconstruct_fn = ip.reconstructFloorplan
    return _reconstruct_fn


def _num_wall_corners() -> int:
    try:
        _register_r2v_path()
        _clear_r2v_conflicts()
        utils = importlib.import_module("utils")
        return int(utils.NUM_WALL_CORNERS)
    except Exception:
        return 13  # paper default


def _icon_name_map() -> dict[int, str]:
    try:
        _register_r2v_path()
        _clear_r2v_conflicts()
        utils = importlib.import_module("utils")
        return {int(k): str(v) for k, v in utils.iconNumberNameMap.items()}
    except Exception:
        return {}


def _load_model(torch: Any, device: Any) -> Any:
    global _model
    if _model is not None:
        return _model

    _register_r2v_path()
    _clear_r2v_conflicts()

    # Obtain default options from the R2V options module.
    try:
        opts_mod = importlib.import_module("options")
        options = opts_mod.parse_args([])
    except (SystemExit, Exception):
        import argparse
        options = argparse.Namespace(
            numFeatures=256,
            numInputChannels=3,
            augmentationProbability=0,
            restore=0,
            task="test",
        )

    _clear_r2v_conflicts()  # re-clear after options import
    model_mod = importlib.import_module("models.model")

    # model.py uses options.height / options.width for the upsample layer.
    if not hasattr(options, "height"):
        options.height = _MODEL_SIZE
    if not hasattr(options, "width"):
        options.width = _MODEL_SIZE

    # model.py does `from models.drn import drn_d_54` so the reference lives
    # in model_mod's namespace. Patch it there to skip the pretrained download
    # — the R2V checkpoint (161 MB) already contains all backbone weights.
    _orig = model_mod.drn_d_54

    def _drn_no_pretrain(*args, **kwargs):
        kwargs["pretrained"] = False
        return _orig(*args, **kwargs)

    model_mod.drn_d_54 = _drn_no_pretrain
    try:
        model = model_mod.Model(options)
    finally:
        model_mod.drn_d_54 = _orig

    ckpt = torch.load(str(_WEIGHTS_PATH), map_location=device, weights_only=False)
    if isinstance(ckpt, dict) and "state_dict" in ckpt:
        model.load_state_dict(ckpt["state_dict"])
    elif isinstance(ckpt, dict) and "model_state" in ckpt:
        model.load_state_dict(ckpt["model_state"])
    else:
        model.load_state_dict(ckpt)

    model = model.to(device)
    model.eval()
    _model = model
    return model


def _r2v_to_contract(
    result: dict[str, Any] | None,
    orig_w: int,
    orig_h: int,
    pad_scale: float = 1.0,
) -> tuple[list[dict], list[dict]]:
    """Map R2V IP solver output to WorkerContract walls/openings format.

    pad_scale = max(orig_h, orig_w) / 256 — uniform scale used by _resize_padded.
    """
    if not result:
        return [], []

    # Aspect-preserving resize uses a single scale for both axes.
    sx = pad_scale
    sy = pad_scale

    walls: list[dict] = []
    openings: list[dict] = []

    # ── Walls ──────────────────────────────────────────────────────────────
    wall_data = result.get("wall")
    if wall_data:
        wallPoints, wallLines, _wallLabels = wall_data
        for i, line in enumerate(wallLines):
            p1 = wallPoints[line[0]]
            p2 = wallPoints[line[1]]
            x1, y1 = float(p1[0]) * sx, float(p1[1]) * sy
            x2, y2 = float(p2[0]) * sx, float(p2[1]) * sy
            # Flip Y: image origin top-left → CAD origin bottom-left.
            y1f = orig_h - y1
            y2f = orig_h - y2
            dx, dy = abs(x2 - x1), abs(y2 - y1)
            orientation = "horizontal" if dx >= dy else "vertical"
            walls.append({
                "id": f"r2v-wall-{i + 1:04d}",
                "polyline": [{"x": x1, "y": y1f}, {"x": x2, "y": y2f}],
                "thickness": 4.0,
                "is_exterior": False,
                "confidence": 0.9,
                "orientation": orientation,
            })

    # ── Doors ──────────────────────────────────────────────────────────────
    door_data = result.get("door")
    if door_data:
        doorPoints, doorLines, _ = door_data
        for i, line in enumerate(doorLines):
            p1 = doorPoints[line[0]]
            p2 = doorPoints[line[1]]
            x1, y1 = float(p1[0]) * sx, float(p1[1]) * sy
            x2, y2 = float(p2[0]) * sx, float(p2[1]) * sy
            cx = (x1 + x2) / 2
            cy = orig_h - (y1 + y2) / 2  # flip Y
            span = max(abs(x2 - x1), abs(y2 - y1))
            dx, dy = abs(x2 - x1), abs(y2 - y1)
            orientation = "horizontal" if dx >= dy else "vertical"
            openings.append({
                "id": f"r2v-door-{i + 1:04d}",
                "kind": "door",
                "position": {"x": cx, "y": cy},
                "span": max(span, 1.0),
                "orientation": orientation,
                "confidence": 0.85,
                "swing": None,
                "door_type": "normal",
            })

    # ── Icons — filter for windows ─────────────────────────────────────────
    icon_data = result.get("icon")
    if icon_data:
        iconPoints, icons, iconTypes = icon_data
        name_map = _icon_name_map()
        for i, (icon_corners, itype) in enumerate(zip(icons, iconTypes)):
            pts = [iconPoints[idx] for idx in icon_corners]
            xs = [float(p[0]) * sx for p in pts]
            ys = [float(p[1]) * sy for p in pts]
            cx = sum(xs) / len(xs)
            cy = orig_h - sum(ys) / len(ys)  # flip Y
            x_span = max(xs) - min(xs)
            y_span = max(ys) - min(ys)
            span = max(x_span, y_span)
            orientation = "horizontal" if x_span >= y_span else "vertical"
            icon_name = name_map.get(int(itype), "").lower()
            if "window" in icon_name:
                openings.append({
                    "id": f"r2v-window-{i + 1:04d}",
                    "kind": "window",
                    "position": {"x": cx, "y": cy},
                    "span": max(span, 1.0),
                    "orientation": orientation,
                    "confidence": 0.85,
                })

    return walls, openings
