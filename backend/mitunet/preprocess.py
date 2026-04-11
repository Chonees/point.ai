from __future__ import annotations

import cv2
import numpy as np

from .model import _IMAGE_SIZE, _IMAGENET_MEAN, _IMAGENET_STD, _load_model


def _preprocess(image_bgr: np.ndarray) -> "torch.Tensor":
    import torch

    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(image_rgb, (_IMAGE_SIZE, _IMAGE_SIZE))
    tensor = resized.astype(np.float32) / 255.0
    tensor = (tensor - _IMAGENET_MEAN) / _IMAGENET_STD
    tensor = torch.from_numpy(tensor.transpose(2, 0, 1)).float().unsqueeze(0)
    return tensor


def _predict_wall_mask(image_bgr: np.ndarray, threshold: float = 0.5) -> np.ndarray:
    """Run MitUNet and return binary wall mask at original resolution."""
    import torch

    model, device = _load_model()
    h_orig, w_orig = image_bgr.shape[:2]

    tensor = _preprocess(image_bgr).to(device)

    with torch.no_grad():
        logits = model(tensor)
        probs = torch.sigmoid(logits)
        mask = (probs > threshold).float()

    result = mask.squeeze().cpu().numpy()
    result_uint8 = (result * 255).astype(np.uint8)
    return cv2.resize(result_uint8, (w_orig, h_orig))
