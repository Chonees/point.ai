"""
image_utils.py
Shared helpers for data-URI image payloads.
"""
from __future__ import annotations

import base64

import cv2
import numpy as np


def parse_image_data(raw: str) -> tuple[str, str]:
    media_type = "image/png"
    image_data = raw
    if "," in raw:
        header, image_data = raw.split(",", 1)
        if "jpeg" in header:
            media_type = "image/jpeg"
        elif "webp" in header:
            media_type = "image/webp"
    return media_type, image_data


def decode_image(image_b64: str) -> np.ndarray:
    _, image_data = parse_image_data(image_b64)
    binary = base64.b64decode(image_data)
    arr = np.frombuffer(binary, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Unable to decode image payload.")
    return image


def encode_png_data(image: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("Unable to encode image as PNG.")
    return buffer.tobytes()
