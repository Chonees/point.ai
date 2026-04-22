"""
worker_contract.py
Defines the contract between Point.ai backend and the GPU inference worker.

Worker endpoint: POST /infer/structure
  Input:  WorkerRequest  (image as base64)
  Output: WorkerResponse (walls, openings, masks metadata, debug overlays)

Error responses use WorkerErrorResponse with typed error codes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .coordinate_space import IMAGE_COORDINATE_SPACE


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------

class WorkerError(Exception):
    """Typed error from the GPU worker."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


ERROR_CODES = {
    "INVALID_IMAGE": "The provided image could not be decoded.",
    "INVALID_RESPONSE": "The worker returned a payload that does not satisfy the contract.",
    "MODEL_NOT_LOADED": "The inference model is not loaded yet.",
    "INFERENCE_FAILED": "Inference failed during forward pass.",
    "POSTPROCESS_FAILED": "Post-processing of model output failed.",
    "WORKER_UNREACHABLE": "Cannot connect to the worker service.",
    "WORKER_TIMEOUT": "Worker did not respond in time.",
    "WORKER_HTTP_ERROR": "Worker returned an unexpected HTTP error.",
}


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

@dataclass
class WorkerRequest:
    """What Point.ai sends to the GPU worker."""
    image_b64: str
    options: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "image": self.image_b64,
            "options": self.options,
        }


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@dataclass
class WorkerHealthResponse:
    status: str
    ready: bool
    model_name: str
    model_version: str
    backend: str


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

@dataclass
class WallDetection:
    """A single wall detected by the model."""
    polyline: list[dict[str, float]]
    thickness: float
    is_exterior: bool = False
    confidence: float = 0.5
    orientation: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WallDetection:
        polyline = data.get("polyline") or []
        if len(polyline) != 2:
            raise ValueError("wall polyline must contain exactly 2 points")
        orientation = data.get("orientation")
        if orientation is not None and orientation not in {"horizontal", "vertical"}:
            raise ValueError(f"invalid wall orientation: {orientation}")
        thickness = float(data.get("thickness", 4.0))
        if thickness <= 0:
            raise ValueError("wall thickness must be positive")
        return cls(
            polyline=[{"x": float(p["x"]), "y": float(p["y"])} for p in polyline],
            thickness=thickness,
            is_exterior=bool(data.get("is_exterior", False)),
            confidence=float(data.get("confidence", 0.5)),
            orientation=orientation,
        )


@dataclass
class OpeningDetection:
    """A single opening (door/window) detected by the model."""
    kind: str  # "door" | "window"
    position: dict[str, float]
    span: float
    orientation: str | None = None
    confidence: float = 0.5
    swing: str | None = None
    door_type: str = "normal"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OpeningDetection:
        kind = data.get("kind")
        if kind not in {"door", "window"}:
            raise ValueError(f"invalid opening kind: {kind}")
        pos = data.get("position", {})
        orientation = data.get("orientation")
        if orientation is not None and orientation not in {"horizontal", "vertical"}:
            raise ValueError(f"invalid opening orientation: {orientation}")
        span = float(data.get("span", 0))
        if span <= 0:
            raise ValueError("opening span must be positive")
        return cls(
            kind=kind,
            position={"x": float(pos.get("x", 0)), "y": float(pos.get("y", 0))},
            span=span,
            orientation=orientation,
            confidence=float(data.get("confidence", 0.5)),
            swing=data.get("swing"),
            door_type=data.get("door_type", "normal"),
        )


@dataclass
class WorkerResponse:
    """What the GPU worker returns to Point.ai."""
    model_name: str
    model_version: str
    walls: list[WallDetection]
    openings: list[OpeningDetection]
    image_size: dict[str, int]
    masks_available: bool = False
    debug_overlay_b64: str | None = None
    inference_time_ms: float = 0.0

    def to_structure_dict(self) -> dict[str, Any]:
        """Convert to the canonical structure dict that plan_parser expects."""
        wall_dicts = []
        for i, wall in enumerate(self.walls, 1):
            wall_dicts.append({
                "id": f"raw-wall-{i:04d}",
                "polyline": wall.polyline,
                "thickness": wall.thickness,
                "is_exterior": wall.is_exterior,
                "confidence": wall.confidence,
                "orientation": wall.orientation,
            })

        opening_dicts = []
        for i, opening in enumerate(self.openings, 1):
            entry: dict[str, Any] = {
                "id": f"raw-opening-{i:04d}",
                "kind": opening.kind,
                "position": opening.position,
                "span": opening.span,
                "orientation": opening.orientation,
                "confidence": opening.confidence,
            }
            if opening.kind == "door":
                entry["swing"] = opening.swing
                entry["door_type"] = opening.door_type
            opening_dicts.append(entry)

        return {
            "model": self.model_name,
            "source": f"remote_worker/{self.model_version}",
            "walls": wall_dicts,
            "openings": opening_dicts,
            "structure_meta": {
                "image_size": self.image_size,
                "scale_status": "unverified",
                "unit": "pixel",
                "coordinate_space": IMAGE_COORDINATE_SPACE,
            },
            "inference_debug": {
                "model_name": self.model_name,
                "model_version": self.model_version,
                "inference_time_ms": self.inference_time_ms,
                "masks_available": self.masks_available,
                "raw_wall_fragments": len(self.walls),
                "raw_opening_detections": len(self.openings),
                "debug_overlay_b64": self.debug_overlay_b64,
            },
        }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_worker_response(raw: dict[str, Any]) -> WorkerResponse:
    """Validate and parse a raw JSON response from the worker."""
    if "error" in raw:
        err = raw["error"]
        raise WorkerError(
            code=err.get("code", "UNKNOWN"),
            message=err.get("message", "Unknown worker error"),
        )

    required = ("model_name", "model_version", "walls", "openings", "image_size")
    missing = [k for k in required if k not in raw]
    if missing:
        raise WorkerError(
            code="INVALID_RESPONSE",
            message=f"Worker response missing required fields: {missing}",
        )

    try:
        walls = [WallDetection.from_dict(w) for w in raw["walls"]]
        openings = [OpeningDetection.from_dict(o) for o in raw["openings"]]
    except (KeyError, TypeError, ValueError) as exc:
        raise WorkerError(
            code="INVALID_RESPONSE",
            message=f"Failed to parse worker detections: {exc}",
        ) from exc

    image_size = raw["image_size"]
    if not isinstance(image_size, dict) or "width" not in image_size or "height" not in image_size:
        raise WorkerError(
            code="INVALID_RESPONSE",
            message="image_size must contain width and height",
        )

    return WorkerResponse(
        model_name=raw["model_name"],
        model_version=raw["model_version"],
        walls=walls,
        openings=openings,
        image_size={
            "width": int(image_size["width"]),
            "height": int(image_size["height"]),
        },
        masks_available=bool(raw.get("masks_available", False)),
        debug_overlay_b64=raw.get("debug_overlay_b64"),
        inference_time_ms=float(raw.get("inference_time_ms", 0)),
    )
