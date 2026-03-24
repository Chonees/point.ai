"""
worker_client.py
Remote GPU worker client for the v2 inference pipeline.

Supports two backends via POINTAI_INFERENCE_BACKEND env var:
  - "heuristic_local" (default): uses the local heuristic from inference_client.py
  - "remote": calls a GPU worker service at POINTAI_WORKER_URL

The remote worker must implement the contract defined in worker_contract.py.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from .cubicasa_inference import CUBICASA_BACKEND, cubicasa_available, infer_cubicasa
from .inference_client import HEURISTIC_BACKEND, infer_heuristic_structure
from .r2v_inference import R2V_BACKEND, infer_r2v, r2v_available
from .segformer_inference import SEGFORMER_BACKEND, infer_segformer, segformer_available
from .mitunet_inference import MITUNET_BACKEND, infer_mitunet, mitunet_available
from .observability import log_event
from .worker_contract import (
    WorkerError,
    WorkerHealthResponse,
    WorkerRequest,
    WorkerResponse,
    validate_worker_response,
)

REMOTE_BACKEND = "remote"

DEFAULT_WORKER_URL = "http://localhost:8100"
WORKER_TIMEOUT_S = 30.0

# When CubiCasa returns fewer walls than this, fall back to the heuristic.
# CubiCasa heatmaps on unusual image types (dark-background, synthetic) can
# underfire; the heuristic morphological approach is more robust as a safety net.
_CUBICASA_MIN_WALLS = int(os.getenv("POINTAI_CUBI_MIN_WALLS", "8"))


def infer_structure(
    image_b64: str,
    *,
    backend: str | None = None,
    options: dict[str, Any] | None = None,
    worker_url: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """Route inference to the configured backend."""
    backend = backend or _default_backend()
    log_event("worker_client.infer.request", backend=backend)

    if backend == HEURISTIC_BACKEND:
        result = infer_heuristic_structure(image_b64)
        result.setdefault("inference_debug", {})
        result["inference_debug"]["backend"] = backend
        log_event("worker_client.infer.success", backend=backend, wall_count=len(result.get("walls", [])))
        return result

    if backend == CUBICASA_BACKEND:
        model_variant = _model_variant_from_options(options)
        ready, reason = cubicasa_available(model_variant)
        if not ready:
            raise WorkerError("MODEL_NOT_LOADED", reason or "CubiCasa is not available.")
        result = infer_cubicasa(image_b64, model_variant=model_variant)
        result.setdefault("inference_debug", {})
        result["inference_debug"]["backend"] = backend

        # Automatic heuristic fallback: if CubiCasa detected very few walls it
        # likely failed on an unusual image type (dark-bg, synthetic, low-contrast).
        wall_count = len(result.get("walls", []))
        if wall_count < _CUBICASA_MIN_WALLS:
            log_event(
                "worker_client.cubicasa.fallback",
                cubicasa_wall_count=wall_count,
                min_required=_CUBICASA_MIN_WALLS,
            )
            heuristic = infer_heuristic_structure(image_b64)
            heuristic.setdefault("inference_debug", {})
            heuristic["inference_debug"]["backend"] = HEURISTIC_BACKEND
            heuristic["inference_debug"]["fallback_from"] = CUBICASA_BACKEND
            heuristic["inference_debug"]["cubicasa_wall_count"] = wall_count
            log_event(
                "worker_client.infer.success",
                backend=HEURISTIC_BACKEND,
                fallback=True,
                wall_count=len(heuristic.get("walls", [])),
            )
            return heuristic

        log_event("worker_client.infer.success", backend=backend, wall_count=wall_count)
        return result

    if backend == REMOTE_BACKEND:
        result = _infer_remote(image_b64, options=options, worker_url=worker_url, transport=transport)
        result.setdefault("inference_debug", {})
        result["inference_debug"]["backend"] = backend
        log_event("worker_client.infer.success", backend=backend, wall_count=len(result.get("walls", [])))
        return result

    if backend == R2V_BACKEND:
        ready, reason = r2v_available()
        if not ready:
            raise WorkerError("MODEL_NOT_LOADED", reason or "R2V is not available.")
        result = infer_r2v(image_b64)
        result.setdefault("inference_debug", {})
        result["inference_debug"]["backend"] = backend
        log_event("worker_client.infer.success", backend=backend, wall_count=len(result.get("walls", [])))
        return result

    if backend == SEGFORMER_BACKEND:
        ready, reason = segformer_available()
        if not ready:
            raise WorkerError("MODEL_NOT_LOADED", reason or "SegFormer is not available.")
        sf_opts = options or {}
        result = infer_segformer(image_b64, **sf_opts)
        result.setdefault("inference_debug", {})
        result["inference_debug"]["backend"] = backend
        log_event("worker_client.infer.success", backend=backend, wall_count=len(result.get("walls", [])))
        return result

    if backend == MITUNET_BACKEND:
        ready, reason = mitunet_available()
        if not ready:
            raise WorkerError("MODEL_NOT_LOADED", reason or "MitUNet is not available.")
        result = infer_mitunet(image_b64)
        result.setdefault("inference_debug", {})
        result["inference_debug"]["backend"] = backend
        log_event("worker_client.infer.success", backend=backend, wall_count=len(result.get("walls", [])))
        return result

    raise ValueError(f"Unsupported inference backend: {backend}")


def get_worker_health(
    *,
    worker_url: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> WorkerHealthResponse:
    worker_url = worker_url or os.getenv("POINTAI_WORKER_URL", DEFAULT_WORKER_URL)
    endpoint = f"{worker_url}/health"

    try:
        with httpx.Client(timeout=WORKER_TIMEOUT_S, transport=transport) as client:
            response = client.get(endpoint)
    except httpx.ConnectError as exc:
        raise WorkerError(
            code="WORKER_UNREACHABLE",
            message=f"Cannot connect to GPU worker at {worker_url}: {exc}",
        ) from exc
    except httpx.TimeoutException as exc:
        raise WorkerError(
            code="WORKER_TIMEOUT",
            message=f"GPU worker timed out after {WORKER_TIMEOUT_S}s",
        ) from exc

    if response.status_code != 200:
        _raise_from_http(response)

    raw = response.json()
    required = ("status", "ready", "model_name", "model_version", "backend")
    missing = [field for field in required if field not in raw]
    if missing:
        raise WorkerError("INVALID_RESPONSE", f"Worker health payload missing fields: {missing}")
    return WorkerHealthResponse(
        status=str(raw["status"]),
        ready=bool(raw["ready"]),
        model_name=str(raw["model_name"]),
        model_version=str(raw["model_version"]),
        backend=str(raw["backend"]),
        )


_backend_cache: str | None = None


def _default_backend() -> str:
    global _backend_cache
    if _backend_cache is not None:
        return _backend_cache
    configured = os.getenv("POINTAI_INFERENCE_BACKEND")
    if configured:
        _backend_cache = configured
        return _backend_cache
    ready, _ = cubicasa_available()
    _backend_cache = CUBICASA_BACKEND if ready else HEURISTIC_BACKEND
    return _backend_cache


def _model_variant_from_options(options: dict[str, Any] | None) -> str | None:
    if not options:
        return None
    variant = options.get("model_variant")
    if variant is None:
        return None
    return str(variant)


def _infer_remote(
    image_b64: str,
    *,
    options: dict[str, Any] | None = None,
    worker_url: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """Call the remote GPU worker and validate the response."""
    worker_url = worker_url or os.getenv("POINTAI_WORKER_URL", DEFAULT_WORKER_URL)
    endpoint = f"{worker_url}/infer/structure"

    request = WorkerRequest(image_b64=image_b64, options=options or {})

    try:
        with httpx.Client(timeout=WORKER_TIMEOUT_S, transport=transport) as client:
            response = client.post(endpoint, json=request.to_dict())
    except httpx.ConnectError as exc:
        raise WorkerError(
            code="WORKER_UNREACHABLE",
            message=f"Cannot connect to GPU worker at {worker_url}: {exc}",
        ) from exc
    except httpx.TimeoutException as exc:
        raise WorkerError(
            code="WORKER_TIMEOUT",
            message=f"GPU worker timed out after {WORKER_TIMEOUT_S}s",
        ) from exc

    if response.status_code != 200:
        _raise_from_http(response)

    raw = response.json()
    validated = validate_worker_response(raw)
    return validated.to_structure_dict()


def _raise_from_http(response: httpx.Response) -> None:
    """Parse worker error response or raise generic HTTP error."""
    try:
        body = response.json()
        raise WorkerError(
            code=body.get("error", {}).get("code", "WORKER_HTTP_ERROR"),
            message=body.get("error", {}).get("message", response.text),
        )
    except (ValueError, KeyError):
        raise WorkerError(
            code="WORKER_HTTP_ERROR",
            message=f"Worker returned HTTP {response.status_code}: {response.text[:500]}",
        )
