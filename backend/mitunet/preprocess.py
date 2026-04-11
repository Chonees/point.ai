from __future__ import annotations

import cv2
import numpy as np

from .model import _IMAGE_SIZE, _IMAGENET_MEAN, _IMAGENET_STD, _load_model, onnx_available, _load_onnx_session


def _preprocess_numpy(image_bgr: np.ndarray) -> np.ndarray:
    """Preprocess image to numpy array (for ONNX)."""
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(image_rgb, (_IMAGE_SIZE, _IMAGE_SIZE))
    tensor = resized.astype(np.float32) / 255.0
    tensor = (tensor - _IMAGENET_MEAN) / _IMAGENET_STD
    return tensor.transpose(2, 0, 1)[np.newaxis, ...].astype(np.float32)


def _preprocess(image_bgr: np.ndarray) -> "torch.Tensor":
    import torch
    return torch.from_numpy(_preprocess_numpy(image_bgr))


def _predict_wall_mask(image_bgr: np.ndarray, threshold: float = 0.5) -> np.ndarray:
    """Run MitUNet and return binary wall mask at original resolution."""
    h_orig, w_orig = image_bgr.shape[:2]

    if onnx_available():
        return _predict_wall_mask_onnx(image_bgr, h_orig, w_orig, threshold)
    return _predict_wall_mask_torch(image_bgr, h_orig, w_orig, threshold)


def _predict_wall_mask_onnx(
    image_bgr: np.ndarray, h_orig: int, w_orig: int, threshold: float,
) -> np.ndarray:
    """ONNX Runtime inference path."""
    session = _load_onnx_session()
    input_array = _preprocess_numpy(image_bgr)
    logits = session.run(None, {"input": input_array})[0]
    # sigmoid
    probs = 1.0 / (1.0 + np.exp(-logits))
    mask = (probs > threshold).astype(np.float32)
    result_uint8 = (mask.squeeze() * 255).astype(np.uint8)
    return cv2.resize(result_uint8, (w_orig, h_orig))


def _predict_wall_mask_torch(
    image_bgr: np.ndarray, h_orig: int, w_orig: int, threshold: float,
) -> np.ndarray:
    """PyTorch inference path (fallback)."""
    import torch

    model, device = _load_model()
    tensor = _preprocess(image_bgr).to(device)

    with torch.no_grad():
        logits = model(tensor)
        probs = torch.sigmoid(logits)
        mask = (probs > threshold).float()

    result = mask.squeeze().cpu().numpy()
    result_uint8 = (result * 255).astype(np.uint8)
    return cv2.resize(result_uint8, (w_orig, h_orig))
