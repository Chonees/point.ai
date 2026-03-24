"""
finetune_segformer.py — Train SegFormer for floor plan semantic segmentation.

Usage:
    python -u -m training.finetune_segformer \\
        --data-path D:/training_v2/converted/cubicasa \\
        --run-dir D:/training_v2/segformer_runs \\
        --epochs 30 --batch-size 4 --image-size 512
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.amp import GradScaler, autocast
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingWarmRestarts
from torch.utils.data import DataLoader

from training.convert_labels_segformer import MERGED_CLASSES, NUM_CLASSES
from training.segformer_dataset import (
    FloorPlanSegFormerDataset,
    discover_samples,
    split_samples,
)

# ---------------------------------------------------------------------------
# Class weights (inverse frequency, from stats)
# ---------------------------------------------------------------------------
# Inverse frequency weights calculated from segformer_class_stats.json
# Formula: weight = median_freq / class_freq (median frequency balancing)
# This gives natural weights without manual tuning
DEFAULT_CLASS_WEIGHTS = None  # Will be computed from data, or use focal loss


class FocalLoss(nn.Module):
    """Focal Loss — automatically focuses on hard-to-classify pixels."""
    def __init__(self, alpha: torch.Tensor | None = None, gamma: float = 2.0, ignore_index: int = 255):
        super().__init__()
        self.alpha = alpha  # optional per-class weights
        self.gamma = gamma  # focusing parameter: higher = more focus on hard examples
        self.ignore_index = ignore_index

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        ce_loss = nn.functional.cross_entropy(
            logits, targets, weight=self.alpha, ignore_index=self.ignore_index, reduction="none"
        )
        pt = torch.exp(-ce_loss)  # probability of correct class
        focal_loss = ((1 - pt) ** self.gamma) * ce_loss
        return focal_loss.mean()


def _compute_inverse_freq_weights(data_path: str, num_classes: int) -> torch.Tensor:
    """Compute class weights from saved stats using median frequency balancing."""
    import json
    stats_path = Path(data_path) / "segformer_class_stats.json"
    if not stats_path.exists():
        print("[WARNING] No class stats found, using uniform weights", flush=True)
        return torch.ones(num_classes)

    with open(stats_path) as f:
        stats = json.load(f)

    total = stats["total_pixels"]
    freqs = []
    for i in range(num_classes):
        pixels = stats["classes"][str(i)]["pixels"]
        freqs.append(pixels / total if total > 0 else 1.0)

    median_freq = sorted(freqs)[len(freqs) // 2]
    weights = [median_freq / (f + 1e-10) for f in freqs]

    # Cap extreme weights
    max_weight = 10.0
    weights = [min(w, max_weight) for w in weights]

    print(f"[Focal Loss] Inverse freq weights: {[round(w, 2) for w in weights]}", flush=True)
    return torch.tensor(weights, dtype=torch.float32)


def _build_model(num_labels: int, model_name: str, device: torch.device) -> nn.Module:
    from transformers import SegformerForSemanticSegmentation

    id2label = {i: name for i, name in MERGED_CLASSES.items()}
    label2id = {name: i for i, name in MERGED_CLASSES.items()}

    model = SegformerForSemanticSegmentation.from_pretrained(
        model_name,
        num_labels=num_labels,
        id2label=id2label,
        label2id=label2id,
        ignore_mismatched_sizes=True,
    )
    return model.to(device)


def _compute_iou(pred: np.ndarray, target: np.ndarray, num_classes: int) -> dict[str, float]:
    """Compute per-class IoU and mean IoU."""
    ious = {}
    for cls in range(num_classes):
        p = pred == cls
        t = target == cls
        intersection = np.sum(p & t)
        union = np.sum(p | t)
        if union > 0:
            ious[MERGED_CLASSES[cls]] = intersection / union

    mean_iou = np.mean(list(ious.values())) if ious else 0.0
    return {
        "mean_iou": float(mean_iou),
        "wall_iou": ious.get("wall", 0.0),
        "door_iou": ious.get("door", 0.0),
        "window_iou": ious.get("window", 0.0),
    }


def _run_epoch(
    model: nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer | None,
    device: torch.device,
    loss_fn: nn.Module,
    scaler: GradScaler | None,
    phase: str,
    log_every: int = 50,
) -> dict[str, float]:
    is_train = optimizer is not None
    model.train() if is_train else model.eval()

    total_loss = 0.0
    all_preds = []
    all_labels = []
    step = 0

    ctx = torch.enable_grad() if is_train else torch.no_grad()
    with ctx:
        for batch in loader:
            pixel_values = batch["pixel_values"].to(device)
            labels = batch["labels"].to(device)

            if scaler and is_train:
                with autocast("cuda"):
                    outputs = model(pixel_values=pixel_values, labels=labels)
                    # Recompute loss with class weights
                    logits = outputs.logits
                    upsampled = nn.functional.interpolate(
                        logits, size=labels.shape[-2:], mode="bilinear", align_corners=False
                    )
                    loss = loss_fn(upsampled, labels)

                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad()
            else:
                outputs = model(pixel_values=pixel_values, labels=labels)
                logits = outputs.logits
                upsampled = nn.functional.interpolate(
                    logits, size=labels.shape[-2:], mode="bilinear", align_corners=False
                )
                loss = loss_fn(upsampled, labels)

                if is_train:
                    loss.backward()
                    nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    optimizer.step()
                    optimizer.zero_grad()

            total_loss += loss.item() * pixel_values.size(0)
            step += 1

            # Collect predictions for IoU (subsample to save memory)
            if not is_train or step % log_every == 0:
                pred = upsampled.argmax(dim=1).cpu().numpy()
                lbl = labels.cpu().numpy()
                all_preds.append(pred)
                all_labels.append(lbl)

            if step % log_every == 0:
                avg_loss = total_loss / (step * pixel_values.size(0))
                samples = step * pixel_values.size(0)
                print(
                    json.dumps({
                        "phase": phase,
                        "step": step,
                        "samples": samples,
                        "loss": round(avg_loss, 4),
                    }),
                    flush=True,
                )

    n_samples = len(loader.dataset)
    avg_loss = total_loss / n_samples

    # Compute IoU
    if all_preds:
        all_preds = np.concatenate(all_preds, axis=0)
        all_labels = np.concatenate(all_labels, axis=0)
        iou_metrics = _compute_iou(all_preds.flatten(), all_labels.flatten(), NUM_CLASSES)
    else:
        iou_metrics = {"mean_iou": 0.0, "wall_iou": 0.0, "door_iou": 0.0, "window_iou": 0.0}

    return {"loss": avg_loss, **iou_metrics}


def run_finetune(
    data_path: str,
    run_dir: str,
    model_name: str = "nvidia/mit-b2",
    epochs: int = 30,
    batch_size: int = 4,
    image_size: int = 512,
    learning_rate: float = 6e-5,
    device_name: str = "cuda",
    log_every: int = 50,
    patience: int = 7,
) -> dict:
    device = torch.device(device_name if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}", flush=True)

    # Discover and split data
    samples = discover_samples(Path(data_path))
    print(f"Found {len(samples)} samples", flush=True)
    train_samples, val_samples = split_samples(samples)
    print(f"Train: {len(train_samples)}  Val: {len(val_samples)}", flush=True)

    # Datasets
    train_ds = FloorPlanSegFormerDataset(train_samples, image_size=image_size, augment=True)
    val_ds = FloorPlanSegFormerDataset(val_samples, image_size=image_size, augment=False)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=0, drop_last=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=0)

    # Model
    model = _build_model(NUM_CLASSES, model_name, device)
    print(f"Model: {model_name} ({sum(p.numel() for p in model.parameters()):,} params)", flush=True)

    # Optimizer
    optimizer = AdamW(model.parameters(), lr=learning_rate, weight_decay=0.01)
    scheduler = CosineAnnealingWarmRestarts(optimizer, T_0=len(train_loader), T_mult=2)

    # Focal Loss with inverse frequency weights
    alpha_weights = _compute_inverse_freq_weights(data_path, NUM_CLASSES).to(device)
    loss_fn = FocalLoss(alpha=alpha_weights, gamma=2.0)

    # AMP
    use_amp = device.type == "cuda"
    scaler = GradScaler("cuda") if use_amp else None

    # Checkpoints
    ckpt_dir = Path(run_dir) / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    history_path = Path(run_dir) / "history.jsonl"

    best_val_loss = float("inf")
    epochs_no_improve = 0

    for epoch in range(epochs):
        t0 = time.time()

        train_metrics = _run_epoch(
            model, train_loader, optimizer, device, loss_fn, scaler,
            phase=f"train_epoch_{epoch}", log_every=log_every,
        )
        scheduler.step()

        val_metrics = _run_epoch(
            model, val_loader, None, device, loss_fn, None,
            phase=f"val_epoch_{epoch}", log_every=log_every,
        )

        elapsed = time.time() - t0
        summary = {
            "epoch": epoch + 1,
            "epochs_total": epochs,
            "train_loss": round(train_metrics["loss"], 4),
            "val_loss": round(val_metrics["loss"], 4),
            "mean_iou": round(val_metrics["mean_iou"], 4),
            "wall_iou": round(val_metrics["wall_iou"], 4),
            "door_iou": round(val_metrics["door_iou"], 4),
            "window_iou": round(val_metrics["window_iou"], 4),
            "elapsed_s": round(elapsed, 1),
        }
        print(f"Epoch {epoch+1}/{epochs}  " + "  ".join(f"{k}={v}" for k, v in summary.items()), flush=True)

        # Save history
        with open(history_path, "a") as f:
            f.write(json.dumps(summary) + "\n")

        # Checkpoints
        ckpt = {
            "model_state": model.state_dict(),
            "optimizer_state": optimizer.state_dict(),
            "epoch": epoch,
            "val_loss": val_metrics["loss"],
            "config": {
                "model_name": model_name,
                "num_labels": NUM_CLASSES,
                "image_size": image_size,
            },
        }
        torch.save(ckpt, str(ckpt_dir / "latest.pt"))

        if val_metrics["loss"] < best_val_loss:
            best_val_loss = val_metrics["loss"]
            epochs_no_improve = 0
            torch.save(ckpt, str(ckpt_dir / "best_val.pt"))
            # Lightweight inference checkpoint
            torch.save(
                {"model_state": model.state_dict(), "config": ckpt["config"]},
                str(ckpt_dir / "best_inference.pt"),
            )
            print(f"  ✓ New best val_loss={best_val_loss:.4f}", flush=True)
        else:
            epochs_no_improve += 1
            if epochs_no_improve >= patience:
                print(f"  Early stopping at epoch {epoch+1} (no improvement for {patience} epochs)", flush=True)
                break

    final = {
        "run_dir": run_dir,
        "device": str(device),
        "epochs_completed": epoch + 1,
        "best_val_loss": best_val_loss,
        "model_name": model_name,
        "num_samples": len(samples),
        "best_checkpoint": str(ckpt_dir / "best_val.pt"),
        "best_inference_checkpoint": str(ckpt_dir / "best_inference.pt"),
    }
    print(json.dumps(final, indent=2), flush=True)
    return final


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune SegFormer for floor plans")
    parser.add_argument("--data-path", type=str, required=True)
    parser.add_argument("--run-dir", type=str, required=True)
    parser.add_argument("--model-name", type=str, default="nvidia/mit-b2")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--image-size", type=int, default=512)
    parser.add_argument("--learning-rate", type=float, default=6e-5)
    parser.add_argument("--device", type=str, default="cuda")
    parser.add_argument("--log-every-steps", type=int, default=50)
    parser.add_argument("--patience", type=int, default=7)
    args = parser.parse_args()

    run_finetune(
        data_path=args.data_path,
        run_dir=args.run_dir,
        model_name=args.model_name,
        epochs=args.epochs,
        batch_size=args.batch_size,
        image_size=args.image_size,
        learning_rate=args.learning_rate,
        device_name=args.device,
        log_every=args.log_every_steps,
        patience=args.patience,
    )


if __name__ == "__main__":
    raise SystemExit(main())
