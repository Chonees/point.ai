"""
export_onnx.py — Export MitUNet and CubiCasa models to ONNX format.

Usage:
    python scripts/export_onnx.py --mitunet
    python scripts/export_onnx.py --cubicasa
    python scripts/export_onnx.py --all
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import torch
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def export_mitunet(output_path: Path | None = None) -> Path:
    """Export MitUNet to ONNX."""
    from backend.mitunet.model import _load_model, _WEIGHTS_PATH, _IMAGE_SIZE

    weights_dir = _WEIGHTS_PATH.parent
    out = output_path or weights_dir / "mitunet_mit_b4.onnx"

    model, device = _load_model()
    model.eval()

    dummy = torch.randn(1, 3, _IMAGE_SIZE, _IMAGE_SIZE).to(device)

    print(f"[export] Exporting MitUNet to {out} ...")
    torch.onnx.export(
        model,
        dummy,
        str(out),
        input_names=["input"],
        output_names=["output"],
        opset_version=17,
        dynamic_axes=None,  # fixed 512x512
    )
    print(f"[export] MitUNet ONNX saved: {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return out


def export_cubicasa(output_path: Path | None = None, variant: str = "baseline") -> Path:
    """Export CubiCasa to ONNX with dynamic H/W axes."""
    cubicasa_root = Path(os.getenv(
        "POINTAI_CUBICASA_ROOT",
        str(ROOT / "floorplan-research" / "CubiCasa5k"),
    ))
    if str(cubicasa_root) not in sys.path:
        sys.path.insert(0, str(cubicasa_root))

    from backend.cubicasa_inference import _load_model, _load_runtime_dependencies, _runtime_device, _variant_config

    config = _variant_config(variant)
    weights_dir = config["weights_path"].parent
    out = output_path or weights_dir / f"cubicasa_{variant}.onnx"

    device = _runtime_device(variant)
    model = _load_model(variant, device)
    model.eval()

    # Export with fixed 1024x1024 (max inference size), no dynamic axes
    # The hourglass architecture doesn't support dynamic export cleanly
    dummy = torch.randn(1, 3, 1024, 1024).to(device)

    print(f"[export] Exporting CubiCasa ({variant}) to {out} ...")
    torch.onnx.export(
        model,
        dummy,
        str(out),
        input_names=["input"],
        output_names=["output"],
        opset_version=18,
    )
    print(f"[export] CubiCasa ONNX saved: {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export models to ONNX")
    parser.add_argument("--mitunet", action="store_true")
    parser.add_argument("--cubicasa", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--variant", default="baseline")
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    out = Path(args.output) if args.output else None

    if args.all or args.mitunet:
        export_mitunet(out)
    if args.all or args.cubicasa:
        export_cubicasa(out, variant=args.variant)
    if not (args.all or args.mitunet or args.cubicasa):
        parser.print_help()
