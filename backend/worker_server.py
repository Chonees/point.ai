"""
worker_server.py
HTTP worker implementation for the v2 inference contract.

This worker currently serves the local heuristic inference backend through the
same contract expected from a future GPU worker.
"""
from __future__ import annotations

import base64
import os
from typing import Any, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .artifacts import build_preview_image
from .cubicasa_inference import CUBICASA_BACKEND, cubicasa_available, infer_cubicasa
from .image_utils import encode_png_data
from .inference_client import HEURISTIC_BACKEND, infer_heuristic_structure
from .opening_policy import disable_opening_detections
from .observability import log_event

WORKER_MODEL_NAME = os.getenv("POINTAI_WORKER_MODEL_NAME", "heuristic-floorplan-worker")
WORKER_MODEL_VERSION = os.getenv("POINTAI_WORKER_MODEL_VERSION", "0.4.0")

worker_app = FastAPI(title="Point.ai Worker", version=WORKER_MODEL_VERSION)


@worker_app.get("/health")
async def health() -> dict[str, Any]:
    ready = os.getenv("POINTAI_WORKER_READY", "true").lower() != "false"
    backend = _worker_backend()
    if backend == CUBICASA_BACKEND:
        cubicasa_ready, _ = cubicasa_available()
        ready = ready and cubicasa_ready
    payload = {
        "status": "ok" if ready else "not_ready",
        "ready": ready,
        "model_name": WORKER_MODEL_NAME,
        "model_version": WORKER_MODEL_VERSION,
        "backend": backend,
    }
    log_event("worker.health", **payload)
    return payload


@worker_app.post("/infer/structure")
async def infer_structure(request: Request) -> JSONResponse:
    body = await request.json()
    image_b64 = body.get("image")
    options = body.get("options", {})

    if not image_b64:
        return _worker_error_response("INVALID_IMAGE", "Request body must include an image field.", status_code=422)

    ready = os.getenv("POINTAI_WORKER_READY", "true").lower() != "false"
    backend = _worker_backend()
    if backend == CUBICASA_BACKEND:
        model_variant = options.get("model_variant") if options else None
        cubicasa_ready, reason = cubicasa_available(str(model_variant) if model_variant else None)
        if not cubicasa_ready:
            return _worker_error_response("MODEL_NOT_LOADED", reason or "CubiCasa is not available.", status_code=503)

    if not ready:
        return _worker_error_response("MODEL_NOT_LOADED", "Worker model is not ready yet.", status_code=503)

    try:
        runner = _inference_runner(backend, options)
    except ValueError as exc:
        return _worker_error_response("MODEL_NOT_LOADED", str(exc), status_code=503)

    try:
        inferred = runner(image_b64)
    except ValueError as exc:
        log_event("worker.invalid_image", error=str(exc))
        return _worker_error_response("INVALID_IMAGE", str(exc), status_code=422)
    except Exception as exc:  # pragma: no cover - defensive branch
        log_event("worker.inference_failed", error=str(exc))
        return _worker_error_response("INFERENCE_FAILED", str(exc), status_code=500)

    inferred = disable_opening_detections(inferred)

    include_overlay = bool(options.get("include_debug_overlay", True))
    debug_overlay_b64 = None
    if include_overlay:
        debug_overlay_b64 = _build_debug_overlay_b64(inferred, image_b64)

    payload = {
        "model_name": inferred.get("model", WORKER_MODEL_NAME),
        "model_version": WORKER_MODEL_VERSION,
        "walls": inferred.get("walls", []),
        "openings": inferred.get("openings", []),
        "image_size": inferred.get("structure_meta", {}).get("image_size", {}),
        "masks_available": False,
        "debug_overlay_b64": debug_overlay_b64,
        "inference_time_ms": float(options.get("inference_time_ms", 0.0)),
    }
    log_event(
        "worker.infer.success",
        backend=backend,
        wall_count=len(payload["walls"]),
        opening_count=len(payload["openings"]),
        model_name=WORKER_MODEL_NAME,
        model_version=WORKER_MODEL_VERSION,
    )
    return JSONResponse(payload)


def _build_debug_overlay_b64(structure: dict[str, Any], image_b64: str) -> str:
    preview = build_preview_image(structure, image_b64=image_b64)
    return base64.b64encode(encode_png_data(preview)).decode("ascii")


def _worker_backend() -> str:
    configured = os.getenv("POINTAI_WORKER_BACKEND")
    if configured:
        return configured
    ready, _ = cubicasa_available()
    return CUBICASA_BACKEND if ready else HEURISTIC_BACKEND


def _inference_runner(
    backend: str,
    options: dict[str, Any] | None = None,
) -> Callable[[str], dict[str, Any]]:
    if backend == HEURISTIC_BACKEND:
        return infer_heuristic_structure
    if backend == CUBICASA_BACKEND:
        model_variant = None
        if options:
            variant = options.get("model_variant")
            model_variant = str(variant) if variant else None
        return lambda image_b64: infer_cubicasa(image_b64, model_variant=model_variant)
    raise ValueError(f"Unsupported worker backend: {backend}")


def _worker_error_response(code: str, message: str, *, status_code: int) -> JSONResponse:
    log_event("worker.error", code=code, message=message, status_code=status_code)
    return JSONResponse(
        {"error": {"code": code, "message": message}},
        status_code=status_code,
    )
