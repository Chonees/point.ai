"""
image_utils.py
Shared helpers for data-URI image payloads.
"""
from __future__ import annotations

import base64

import cv2
import numpy as np


def preprocess_for_cubicasa(image: np.ndarray) -> np.ndarray:
    """Strip furniture, text and dimension lines from a floor plan image.

    Walls are thick filled elements; text, furniture and annotation lines are
    thin.  A morphological erode→dilate cycle (opening) removes any element
    thinner than the erosion radius while restoring wall thickness.  The result
    is a clean black-on-white image with only structural walls visible.

    The erosion radius is chosen adaptively: ~0.4 % of the shorter image
    dimension, which is large enough to kill 1-3 px annotation lines but small
    enough to preserve 6+ px walls across typical plan resolutions.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Normalize brightness convention: CubiCasa expects light background + dark walls.
    # If the image is predominantly dark (dark-background scan or inverted plan), flip it
    # before any thresholding so the Otsu step always sees light-bg + dark-wall input.
    if gray.mean() < 128:
        gray = cv2.bitwise_not(gray)

    # Otsu threshold → walls = white on black
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)

    # Adaptive kernel: ~0.4% of the shorter side, minimum 2 px
    short_side = min(image.shape[:2])
    radius = max(2, int(round(short_side * 0.004)))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (radius, radius))

    # Erode kills thin elements, dilate restores wall thickness
    eroded = cv2.erode(binary, kernel, iterations=1)
    restored = cv2.dilate(eroded, kernel, iterations=2)

    # Return white-background BGR (model expects 3 channels)
    return cv2.cvtColor(255 - restored, cv2.COLOR_GRAY2BGR)


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
