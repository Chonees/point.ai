from __future__ import annotations

import os
from pathlib import Path

import numpy as np

MITUNET_BACKEND = "mitunet_local"
MITUNET_MASK_REGIONS_DXF_MODE = "mask_regions"
MAX_MITUNET_REGION_WALL_THICKNESS = 6.0
MITUNET_MODEL_NAME = "MitUNet MiT-B4 UNet scSE"

_WEIGHTS_PATH = Path(os.getenv(
    "POINTAI_MITUNET_WEIGHTS",
    r"C:\Users\lucas\OneDrive\Escritorio\pesos\mitunet_finetune_a6_mit_b4_tversky_8864_28E.pth",
))
_IMAGE_SIZE = 512
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406])
_IMAGENET_STD = np.array([0.229, 0.224, 0.225])

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "data" / "plans" / "MARCAREGISTRADA.dxf"

_PLAN_X1 = 40
_PLAN_Y1 = 30
_PLAN_X2 = 1530
_PLAN_Y2 = 1080

_model = None
_device = None
_onnx_session = None

_ONNX_PATH = _WEIGHTS_PATH.parent / "mitunet_mit_b4.onnx"


def mitunet_available() -> tuple[bool, str | None]:
    if not _WEIGHTS_PATH.exists() and not _ONNX_PATH.exists():
        return False, f"No weights found: {_WEIGHTS_PATH}"
    try:
        import torch
        import segmentation_models_pytorch as smp
        return True, None
    except ImportError as e:
        # ONNX-only mode: PyTorch not needed if ONNX file exists
        if _ONNX_PATH.exists():
            try:
                import onnxruntime
                return True, None
            except ImportError:
                pass
        return False, str(e)


def _load_onnx_session():
    global _onnx_session
    if _onnx_session is not None:
        return _onnx_session

    import onnxruntime as ort
    opts = ort.SessionOptions()
    opts.inter_op_num_threads = 2
    opts.intra_op_num_threads = 4
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    _onnx_session = ort.InferenceSession(str(_ONNX_PATH), opts, providers=["CPUExecutionProvider"])
    print(f"[MitUNet] ONNX session loaded from {_ONNX_PATH}")
    return _onnx_session


def _load_model():
    global _model, _device
    if _model is not None:
        return _model, _device

    import torch
    import segmentation_models_pytorch as smp

    _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    aux = smp.Segformer(encoder_name="mit_b4", encoder_weights=None)
    model = smp.Unet(
        encoder_name="mit_b4",
        encoder_weights=None,
        in_channels=3,
        classes=1,
        decoder_attention_type="scse",
    )
    model.encoder = aux.encoder

    state_dict = torch.load(str(_WEIGHTS_PATH), map_location=_device, weights_only=False)
    model.load_state_dict(state_dict)
    model.to(_device)
    model.eval()

    _model = model
    print(f"[MitUNet] Model loaded on {_device}")
    return _model, _device


def onnx_available() -> bool:
    """Check if ONNX runtime is available for MitUNet."""
    if not _ONNX_PATH.exists():
        return False
    try:
        import onnxruntime
        return True
    except ImportError:
        return False
