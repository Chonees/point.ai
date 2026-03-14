"""
worker/server.py
GPU inference worker for Point.ai — POST /infer/structure

Supports two backends via POINTAI_MODEL_BACKEND env var:
  - "heuristic"   (default): OpenCV heuristic, no GPU needed
  - "cubicasa5k"  : CubiCasa5k segmentation model (requires PyTorch + weights)
  - "floortrans"  : FloorTransNet model (requires PyTorch + weights)

Model weights path: POINTAI_MODEL_WEIGHTS env var (path to .pth file)

Contract (POST /infer/structure):
  Request:  { "image": "<base64 data-uri>", "options": {} }
  Response: { model_name, model_version, walls[], openings[], image_size,
              masks_available, debug_overlay_b64, inference_time_ms }
"""
from __future__ import annotations

import base64
import os
import time
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

MODEL_NAME = os.getenv("POINTAI_WORKER_MODEL_NAME", "floorplan-seg-worker")
MODEL_VERSION = os.getenv("POINTAI_WORKER_MODEL_VERSION", "1.0.0")
MODEL_BACKEND = os.getenv("POINTAI_MODEL_BACKEND", "heuristic")
MODEL_WEIGHTS = os.getenv("POINTAI_MODEL_WEIGHTS", "")

app = FastAPI(title="Point.ai GPU Worker", version=MODEL_VERSION)

# Module-level model cache (loaded once on startup)
_model = None


def _load_model():
    global _model
    if _model is not None:
        return _model

    if MODEL_BACKEND == "heuristic":
        _model = "heuristic"
        return _model

    if MODEL_BACKEND == "cubicasa5k":
        _model = _load_cubicasa5k(MODEL_WEIGHTS)
        return _model

    if MODEL_BACKEND == "floortrans":
        _model = _load_floortrans(MODEL_WEIGHTS)
        return _model

    raise RuntimeError(f"Unknown model backend: {MODEL_BACKEND}")


def _load_cubicasa5k(weights_path: str):
    """Load CubiCasa5k segmentation model.

    Expected: standard CubiCasa5k PyTorch checkpoint.
    Returns the model in eval mode.
    """
    try:
        import torch
        from torchvision import models

        # CubiCasa5k uses a FCN/DeepLab-style segmenter with 3 output channels:
        # 0=background, 1=walls, 2=rooms
        # Replace this stub with the actual CubiCasa5k model class when available.
        raise NotImplementedError(
            "CubiCasa5k model class not bundled — add cubicasa5k/ package and update this loader."
        )
    except ImportError:
        raise RuntimeError("PyTorch not installed. Run: pip install torch torchvision")


def _load_floortrans(weights_path: str):
    """Load FloorTransNet segmentation model.

    Expected: standard FloorTransNet PyTorch checkpoint.
    """
    try:
        import torch
        raise NotImplementedError(
            "FloorTransNet model class not bundled — add floortrans/ package and update this loader."
        )
    except ImportError:
        raise RuntimeError("PyTorch not installed. Run: pip install torch torchvision")


@app.on_event("startup")
async def startup():
    ready = os.getenv("POINTAI_WORKER_READY", "true").lower() != "false"
    if ready:
        try:
            _load_model()
        except NotImplementedError:
            pass  # GPU model stubs — worker still serves heuristic fallback
        except Exception as exc:
            print(f"[worker] WARNING: model load failed: {exc}")


@app.get("/health")
async def health() -> dict[str, Any]:
    ready = os.getenv("POINTAI_WORKER_READY", "true").lower() != "false"
    return {
        "status": "ok" if ready else "not_ready",
        "ready": ready,
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "backend": MODEL_BACKEND,
    }


@app.post("/infer/structure")
async def infer_structure(request: Request) -> JSONResponse:
    body = await request.json()
    image_b64 = body.get("image")
    options = body.get("options", {})

    if not image_b64:
        return _error("INVALID_IMAGE", "Request body must include an image field.", 422)

    ready = os.getenv("POINTAI_WORKER_READY", "true").lower() != "false"
    if not ready:
        return _error("MODEL_NOT_LOADED", "Worker model is not ready.", 503)

    t0 = time.perf_counter()
    try:
        image = _decode_image(image_b64)
    except Exception as exc:
        return _error("INVALID_IMAGE", f"Could not decode image: {exc}", 422)

    try:
        model = _load_model()
        if model == "heuristic" or MODEL_BACKEND == "heuristic":
            walls, openings = _heuristic_infer(image)
        else:
            walls, openings = _model_infer(model, image)
    except NotImplementedError as exc:
        # GPU model not yet integrated — fall back to heuristic
        print(f"[worker] Falling back to heuristic: {exc}")
        walls, openings = _heuristic_infer(image)
    except Exception as exc:
        return _error("INFERENCE_FAILED", str(exc), 500)

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    height, width = image.shape[:2]

    debug_overlay_b64 = None
    if options.get("include_debug_overlay", True):
        debug_overlay_b64 = _build_overlay_b64(image, walls, openings)

    return JSONResponse({
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "walls": walls,
        "openings": openings,
        "image_size": {"width": width, "height": height},
        "masks_available": False,
        "debug_overlay_b64": debug_overlay_b64,
        "inference_time_ms": round(elapsed_ms, 2),
    })


# ---------------------------------------------------------------------------
# Heuristic inference (fallback, no GPU required)
# ---------------------------------------------------------------------------

def _heuristic_infer(image: np.ndarray) -> tuple[list, list]:
    """Simplified heuristic wall/opening detection.
    For full implementation see backend/inference_client.py.
    """
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if np.sum(binary > 0) / binary.size > 0.5:
        binary = cv2.bitwise_not(binary)

    # Extract H and V walls with morphological kernels
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
    h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
    v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)

    walls = _mask_to_walls(h_lines, "horizontal") + _mask_to_walls(v_lines, "vertical")
    openings = []  # gap/arc detection delegated to backend/inference_client.py
    return walls, openings


def _mask_to_walls(mask: np.ndarray, orientation: str) -> list[dict]:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    walls = []
    for i, cnt in enumerate(contours):
        x, y, w, h = cv2.boundingRect(cnt)
        if orientation == "horizontal" and w < 20:
            continue
        if orientation == "vertical" and h < 20:
            continue
        if orientation == "horizontal":
            yc = float(y + h / 2)
            walls.append({
                "id": f"raw-wall-{orientation[:1]}{i:04d}",
                "orientation": "horizontal",
                "polyline": [{"x": float(x), "y": yc}, {"x": float(x + w), "y": yc}],
                "thickness": float(max(1, h)),
                "is_exterior": False,
                "confidence": 0.7,
            })
        else:
            xc = float(x + w / 2)
            walls.append({
                "id": f"raw-wall-{orientation[:1]}{i:04d}",
                "orientation": "vertical",
                "polyline": [{"x": xc, "y": float(y)}, {"x": xc, "y": float(y + h)}],
                "thickness": float(max(1, w)),
                "is_exterior": False,
                "confidence": 0.7,
            })
    return walls


# ---------------------------------------------------------------------------
# GPU model inference (stub — implement when model weights are available)
# ---------------------------------------------------------------------------

def _model_infer(model, image: np.ndarray) -> tuple[list, list]:
    """Run inference with a loaded PyTorch model.

    Expected model output: segmentation masks with channels:
      - channel 0: background
      - channel 1: walls
      - channel 2: openings / rooms

    Replace the body of this function with the actual model forward pass.
    """
    raise NotImplementedError("GPU model inference not yet implemented.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decode_image(image_b64: str) -> np.ndarray:
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]
    data = base64.b64decode(image_b64)
    arr = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode image data")
    return image


def _build_overlay_b64(image: np.ndarray, walls: list, openings: list) -> str:
    overlay = image.copy()
    for wall in walls:
        pts = wall.get("polyline", [])
        if len(pts) == 2:
            p1 = (int(pts[0]["x"]), int(pts[0]["y"]))
            p2 = (int(pts[1]["x"]), int(pts[1]["y"]))
            cv2.line(overlay, p1, p2, (0, 0, 255), 2)
    for op in openings:
        pos = op.get("position", {})
        cx, cy = int(pos.get("x", 0)), int(pos.get("y", 0))
        color = (0, 255, 0) if op.get("kind") == "door" else (255, 0, 0)
        cv2.circle(overlay, (cx, cy), 6, color, -1)
    _, buf = cv2.imencode(".png", overlay)
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _error(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)
