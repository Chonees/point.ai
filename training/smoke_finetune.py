from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import torch
import torch.nn.functional as F
import torch.nn as nn
from torch.optim import Adam
from torch.utils.data import DataLoader


def _cubi_root() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / ".."
        / "floorplan-research"
        / "CubiCasa5k"
    ).resolve()


def _build_smoke_augmentations(image_size: int):
    from floortrans.loaders.augmentations import Compose, DictToTensor, ResizePaddedTorch

    return Compose(
        [
            ResizePaddedTorch((0, 0), data_format="dict", size=(image_size, image_size)),
            DictToTensor(),
        ]
    )


def smoke_loss(outputs: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
    heatmap_pred, rooms_pred, icons_pred = torch.split(outputs, [21, 12, 11], dim=1)
    heatmap_target, rooms_target, icons_target = torch.split(labels, [21, 1, 1], dim=1)
    rooms_target = rooms_target.squeeze(1).long()
    icons_target = icons_target.squeeze(1).long()
    heatmap_loss = F.mse_loss(heatmap_pred, heatmap_target)
    room_loss = F.cross_entropy(rooms_pred, rooms_target)
    icon_loss = F.cross_entropy(icons_pred, icons_target)
    return heatmap_loss + room_loss + icon_loss


def run_smoke_finetune(
    *,
    data_path: Path,
    batch_size: int = 1,
    max_steps: int = 1,
    image_size: int = 128,
    learning_rate: float = 1e-4,
    checkpoint_output: Path | None = None,
    model_variant: str = "experimental",
) -> dict[str, object]:
    cubi_root = _cubi_root()
    sys.path.insert(0, str(cubi_root))

    from floortrans.loaders import FloorplanSVG
    from floortrans.models import get_model

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dataset = FloorplanSVG(
        str(data_path) + "\\",
        "train.txt",
        format="lmdb",
        augmentations=_build_smoke_augmentations(image_size),
    )
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=0)

    previous_cwd = Path.cwd()
    os.chdir(cubi_root)
    try:
        model = get_model("hg_furukawa_original", 51)
        model.conv4_ = torch.nn.Conv2d(256, 44, bias=True, kernel_size=1)
        model.upsample = torch.nn.ConvTranspose2d(44, 44, kernel_size=4, stride=4)
        for module in [model.conv4_, model.upsample]:
            nn.init.kaiming_normal_(module.weight, mode="fan_out", nonlinearity="relu")
            nn.init.constant_(module.bias, 0)
        model = model.to(device)
    finally:
        os.chdir(previous_cwd)
    optimizer = Adam(model.parameters(), lr=learning_rate)
    model.train()

    steps_run = 0
    last_loss = None
    while steps_run < max_steps:
        progressed = False
        for batch in loader:
            images = batch["image"].to(device=device, dtype=torch.float32)
            if torch.max(images).item() > 1.5:
                images = 2.0 * (images / 255.0) - 1.0
            labels = batch["label"].to(device)
            optimizer.zero_grad(set_to_none=True)
            outputs = model(images)
            loss = smoke_loss(outputs, labels)
            loss.backward()
            optimizer.step()
            last_loss = float(loss.detach().cpu().item())
            steps_run += 1
            progressed = True
            if steps_run >= max_steps:
                break
        if not progressed:
            break

    if checkpoint_output is not None:
        checkpoint_output.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "model_state": model.state_dict(),
                "variant": model_variant,
                "steps_run": steps_run,
                "last_loss": last_loss,
                "dataset_size": len(dataset),
                "learning_rate": learning_rate,
            },
            checkpoint_output,
        )

    summary = {
        "device": str(device),
        "cuda_available": torch.cuda.is_available(),
        "steps_run": steps_run,
        "last_loss": last_loss,
        "dataset_size": len(dataset),
        "image_size": image_size,
        "batch_size": batch_size,
        "model_variant": model_variant,
        "checkpoint_output": str(checkpoint_output) if checkpoint_output else None,
    }
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a one-step smoke fine-tune over a CubiCasa-compatible LMDB layout.")
    parser.add_argument("--data-path", type=Path, required=True, help="Directory containing train.txt and cubi_lmdb/.")
    parser.add_argument("--batch-size", type=int, default=1, help="Batch size.")
    parser.add_argument("--steps", type=int, default=1, help="Maximum optimizer steps.")
    parser.add_argument("--image-size", type=int, default=128, help="Resize target for the smoke run.")
    parser.add_argument("--learning-rate", type=float, default=1e-4, help="Learning rate.")
    parser.add_argument(
        "--checkpoint-output",
        type=Path,
        default=None,
        help="Optional path to save an inference-compatible checkpoint.",
    )
    parser.add_argument(
        "--model-variant",
        type=str,
        default="experimental",
        help="Variant name stored in the checkpoint metadata.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "training" / "smoke_finetune_summary.json",
        help="Where to write the smoke summary JSON.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    summary = run_smoke_finetune(
        data_path=args.data_path,
        batch_size=args.batch_size,
        max_steps=args.steps,
        image_size=args.image_size,
        learning_rate=args.learning_rate,
        checkpoint_output=args.checkpoint_output,
        model_variant=args.model_variant,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
