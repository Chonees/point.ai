from __future__ import annotations

import argparse
import json
import os
import random
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from torch.optim import AdamW
from torch.optim.lr_scheduler import ReduceLROnPlateau
from torch.utils.data import DataLoader


N_CLASSES = 44
SPLIT = [21, 12, 11]
DEFAULT_D_MONOLITH = Path(r"D:\PointAIData\datasets\combined_curated_full\cubi_layout_monolith")
DEFAULT_LOCAL_MONOLITH = Path("data") / "training" / "combined_curated_full" / "cubi_layout"
DEFAULT_BASELINE_WEIGHTS = (
    Path(__file__).resolve().parents[1]
    / ".."
    / "floorplan-research"
    / "CubiCasa5k"
    / "model_best_val_loss_var.pkl"
).resolve()


@dataclass(slots=True)
class EpochMetrics:
    loss: float
    heatmap_loss: float
    room_loss: float
    icon_loss: float
    room_acc: float
    icon_acc: float
    steps: int
    samples: int
    skipped_steps: int = 0


def _cubi_root() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / ".."
        / "floorplan-research"
        / "CubiCasa5k"
    ).resolve()


def _resolve_default_data_path() -> Path:
    for candidate in (DEFAULT_LOCAL_MONOLITH, DEFAULT_D_MONOLITH):
        if candidate.exists():
            return candidate
    return DEFAULT_LOCAL_MONOLITH


def _normalize_num_workers(requested: int) -> int:
    requested = max(int(requested), 0)
    # FloorplanSVG keeps an open lmdb.Environment. On Windows the DataLoader
    # worker start method requires picklable dataset state, so multiprocessing
    # workers are not safe here. Force single-process loading instead.
    if os.name == "nt" and requested > 0:
        return 0
    return requested


def _runtime_imports() -> tuple[Any, Any, Any, Any, Any, Any]:
    cubi_root = _cubi_root()
    if str(cubi_root) not in sys.path:
        sys.path.insert(0, str(cubi_root))

    from floortrans.loaders import FloorplanSVG
    from floortrans.loaders.augmentations import (
        ColorJitterTorch,
        Compose,
        DictToTensor,
        RandomRotations,
        ResizePaddedTorch,
    )
    from floortrans.models.hg_furukawa_original import hg_furukawa_original

    return FloorplanSVG, Compose, DictToTensor, RandomRotations, ResizePaddedTorch, (ColorJitterTorch, hg_furukawa_original)


def _extract_state_dict(checkpoint: Any) -> dict[str, Any]:
    if isinstance(checkpoint, dict):
        if "model_state" in checkpoint:
            return checkpoint["model_state"]
        if "state_dict" in checkpoint:
            return checkpoint["state_dict"]
    if hasattr(checkpoint, "keys"):
        return checkpoint
    raise ValueError("Unsupported checkpoint format.")


def _build_train_augmentations(image_size: int, *, enable_color_jitter: bool) -> Any:
    _, Compose, DictToTensor, RandomRotations, ResizePaddedTorch, extra = _runtime_imports()
    ColorJitterTorch, _ = extra
    augmentations: list[Any] = [
        ResizePaddedTorch((0, 0), data_format="dict", size=(image_size, image_size)),
        RandomRotations(format="cubi"),
        DictToTensor(),
    ]
    if enable_color_jitter:
        augmentations.append(ColorJitterTorch())
    return Compose(augmentations)


def _build_eval_augmentations(image_size: int) -> Any:
    _, Compose, DictToTensor, _, ResizePaddedTorch, _ = _runtime_imports()
    return Compose(
        [
            ResizePaddedTorch((0, 0), data_format="dict", size=(image_size, image_size)),
            DictToTensor(),
        ]
    )


def cubicasa_multitask_loss(outputs: torch.Tensor, labels: torch.Tensor) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
    heatmap_pred, rooms_pred, icons_pred = torch.split(outputs, SPLIT, dim=1)
    heatmap_target, rooms_target, icons_target = torch.split(labels, [21, 1, 1], dim=1)
    rooms_target = rooms_target.squeeze(1).long()
    icons_target = icons_target.squeeze(1).long()
    heatmap_loss = F.mse_loss(heatmap_pred, heatmap_target)
    room_loss = F.cross_entropy(rooms_pred, rooms_target)
    icon_loss = F.cross_entropy(icons_pred, icons_target)
    total = heatmap_loss + room_loss + icon_loss
    return total, {
        "heatmap_loss": heatmap_loss,
        "room_loss": room_loss,
        "icon_loss": icon_loss,
    }


def _compute_batch_metrics(outputs: torch.Tensor, labels: torch.Tensor) -> tuple[float, float]:
    _, rooms_pred, icons_pred = torch.split(outputs, SPLIT, dim=1)
    _, rooms_target, icons_target = torch.split(labels, [21, 1, 1], dim=1)
    rooms_target = rooms_target.squeeze(1).long()
    icons_target = icons_target.squeeze(1).long()

    room_acc = (rooms_pred.argmax(dim=1) == rooms_target).float().mean().item()
    icon_acc = (icons_pred.argmax(dim=1) == icons_target).float().mean().item()
    return room_acc, icon_acc


def _build_model(device: torch.device, *, init_weights: Path | None) -> torch.nn.Module:
    *_, extra = _runtime_imports()
    _, hg_furukawa_original = extra
    model = hg_furukawa_original(n_classes=N_CLASSES)
    if init_weights is not None:
        checkpoint = torch.load(str(init_weights), map_location=device, weights_only=False)
        model.load_state_dict(_extract_state_dict(checkpoint))
    model = model.to(device)
    return model


def _device_from_name(name: str | None) -> torch.device:
    if name and name != "auto":
        return torch.device(name)
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _autocast_context(device: torch.device, enabled: bool):
    if enabled and device.type == "cuda":
        return torch.amp.autocast(device_type="cuda", dtype=torch.float16)
    return torch.autocast(device_type=device.type, enabled=False)


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _save_training_checkpoint(
    path: Path,
    *,
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
    scheduler: ReduceLROnPlateau,
    scaler: torch.cuda.amp.GradScaler,
    epoch: int,
    global_step: int,
    best_val_loss: float,
    config: dict[str, Any],
    last_train_metrics: EpochMetrics,
    last_val_metrics: EpochMetrics,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state": model.state_dict(),
            "optimizer_state": optimizer.state_dict(),
            "scheduler_state": scheduler.state_dict(),
            "scaler_state": scaler.state_dict(),
            "epoch": epoch,
            "global_step": global_step,
            "best_val_loss": best_val_loss,
            "config": config,
            "last_train_metrics": asdict(last_train_metrics),
            "last_val_metrics": asdict(last_val_metrics),
        },
        path,
    )


def _export_inference_checkpoint(
    path: Path,
    *,
    model: torch.nn.Module,
    model_variant: str,
    epoch: int,
    global_step: int,
    val_metrics: EpochMetrics,
    train_metrics: EpochMetrics,
    source_checkpoint: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state": model.state_dict(),
            "variant": model_variant,
            "epoch": epoch,
            "global_step": global_step,
            "val_loss": val_metrics.loss,
            "train_loss": train_metrics.loss,
            "source_checkpoint": source_checkpoint,
            "exported_at": datetime.now(UTC).isoformat(),
        },
        path,
    )


def _make_dataloader(
    *,
    data_path: Path,
    split_file: str,
    image_size: int,
    batch_size: int,
    num_workers: int,
    shuffle: bool,
    enable_color_jitter: bool,
    pin_memory: bool,
) -> DataLoader:
    FloorplanSVG, *_ = _runtime_imports()
    effective_num_workers = _normalize_num_workers(num_workers)
    augmentations = (
        _build_train_augmentations(image_size, enable_color_jitter=enable_color_jitter)
        if shuffle
        else _build_eval_augmentations(image_size)
    )
    dataset = FloorplanSVG(
        str(data_path) + "\\",
        split_file,
        format="lmdb",
        augmentations=augmentations,
        original_size=False,
    )
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=effective_num_workers,
        pin_memory=pin_memory,
        persistent_workers=effective_num_workers > 0,
    )


def _verify_dataset_access(*, data_path: Path, split_file: str, max_items: int = 8) -> None:
    FloorplanSVG, *_ = _runtime_imports()
    dataset = FloorplanSVG(
        str(data_path) + "\\",
        split_file,
        format="lmdb",
        augmentations=None,
        original_size=False,
    )
    length = len(dataset)
    if length == 0:
        raise ValueError(f"Dataset split {split_file} is empty at {data_path}")

    indices = sorted({0, max(0, length - 1), *(int(i * max(length - 1, 0) / max_items) for i in range(max_items))})
    for index in indices[: max_items + 2]:
        _ = dataset[index]


def _run_epoch(
    *,
    model: torch.nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer | None,
    scaler: torch.cuda.amp.GradScaler,
    device: torch.device,
    amp_enabled: bool,
    grad_clip_norm: float | None,
    accumulation_steps: int,
    max_steps: int,
    log_every_steps: int,
    progress_prefix: str,
) -> EpochMetrics:
    is_train = optimizer is not None
    model.train(is_train)

    total_loss = 0.0
    total_heatmap_loss = 0.0
    total_room_loss = 0.0
    total_icon_loss = 0.0
    total_room_acc = 0.0
    total_icon_acc = 0.0
    step_count = 0
    sample_count = 0
    skipped_steps = 0

    if is_train:
        optimizer.zero_grad(set_to_none=True)

    for batch_index, batch in enumerate(loader, start=1):
        images = batch["image"].to(device=device, dtype=torch.float32, non_blocking=device.type == "cuda")
        if torch.max(images).item() > 1.5:
            images = 2.0 * (images / 255.0) - 1.0
        labels = batch["label"].to(device=device, dtype=torch.float32, non_blocking=device.type == "cuda")

        with _autocast_context(device, amp_enabled):
            outputs = model(images)
            loss, parts = cubicasa_multitask_loss(outputs, labels)
            scaled_loss = loss / max(accumulation_steps, 1)

        tensors_to_check = [outputs, loss, parts["heatmap_loss"], parts["room_loss"], parts["icon_loss"]]
        if not all(torch.isfinite(tensor).all() for tensor in tensors_to_check):
            skipped_steps += 1
            if is_train:
                optimizer.zero_grad(set_to_none=True)
            continue

        if is_train:
            scaler.scale(scaled_loss).backward()
            if batch_index % accumulation_steps == 0:
                if grad_clip_norm is not None:
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip_norm)
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)

        room_acc, icon_acc = _compute_batch_metrics(outputs.detach(), labels)
        batch_size = int(images.shape[0])
        total_loss += float(loss.detach().cpu().item())
        total_heatmap_loss += float(parts["heatmap_loss"].detach().cpu().item())
        total_room_loss += float(parts["room_loss"].detach().cpu().item())
        total_icon_loss += float(parts["icon_loss"].detach().cpu().item())
        total_room_acc += room_acc
        total_icon_acc += icon_acc
        step_count += 1
        sample_count += batch_size

        if log_every_steps > 0 and step_count % log_every_steps == 0:
            running = {
                "phase": progress_prefix,
                "step": step_count,
                "loss": total_loss / step_count,
                "room_acc": total_room_acc / step_count,
                "icon_acc": total_icon_acc / step_count,
                "samples": sample_count,
                "skipped_steps": skipped_steps,
            }
            print(json.dumps(running, sort_keys=True), flush=True)

        if max_steps > 0 and step_count >= max_steps:
            break

    if is_train and step_count > 0 and step_count % accumulation_steps != 0:
        if grad_clip_norm is not None:
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip_norm)
        scaler.step(optimizer)
        scaler.update()
        optimizer.zero_grad(set_to_none=True)

    if step_count == 0:
        return EpochMetrics(
            loss=float("inf"),
            heatmap_loss=float("inf"),
            room_loss=float("inf"),
            icon_loss=float("inf"),
            room_acc=0.0,
            icon_acc=0.0,
            steps=0,
            samples=sample_count,
            skipped_steps=skipped_steps,
        )

    denominator = step_count
    return EpochMetrics(
        loss=total_loss / denominator,
        heatmap_loss=total_heatmap_loss / denominator,
        room_loss=total_room_loss / denominator,
        icon_loss=total_icon_loss / denominator,
        room_acc=total_room_acc / denominator,
        icon_acc=total_icon_acc / denominator,
        steps=step_count,
        samples=sample_count,
        skipped_steps=skipped_steps,
    )


def run_finetune(
    *,
    data_path: Path,
    run_dir: Path,
    epochs: int,
    batch_size: int,
    image_size: int,
    learning_rate: float,
    weight_decay: float,
    device_name: str = "auto",
    num_workers: int = 0,
    seed: int = 13,
    init_weights: Path | None = DEFAULT_BASELINE_WEIGHTS,
    resume_checkpoint: Path | None = None,
    max_train_steps_per_epoch: int = 0,
    max_val_steps: int = 0,
    accumulation_steps: int = 1,
    grad_clip_norm: float | None = 1.0,
    amp_enabled: bool = False,
    enable_color_jitter: bool = True,
    model_variant: str = "baseline",
    export_inference_checkpoint: Path | None = None,
    log_every_steps: int = 100,
) -> dict[str, Any]:
    if image_size < 128:
        raise ValueError("image_size must be at least 128 for hg_furukawa_original training.")
    _seed_everything(seed)
    device = _device_from_name(device_name)
    effective_num_workers = _normalize_num_workers(num_workers)
    if device.type == "cuda":
        torch.backends.cudnn.benchmark = True

    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoints_dir = run_dir / "checkpoints"
    logs_dir = run_dir / "logs"
    checkpoints_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    tensorboard_writer = None
    try:
        from tensorboardX import SummaryWriter

        tensorboard_writer = SummaryWriter(str(run_dir / "tensorboard"))
    except Exception:
        tensorboard_writer = None

    config = {
        "data_path": str(data_path),
        "run_dir": str(run_dir),
        "epochs": epochs,
        "batch_size": batch_size,
        "image_size": image_size,
        "learning_rate": learning_rate,
        "weight_decay": weight_decay,
        "device_name": device_name,
        "resolved_device": str(device),
        "num_workers": num_workers,
        "effective_num_workers": effective_num_workers,
        "seed": seed,
        "init_weights": str(init_weights) if init_weights else None,
        "resume_checkpoint": str(resume_checkpoint) if resume_checkpoint else None,
        "max_train_steps_per_epoch": max_train_steps_per_epoch,
        "max_val_steps": max_val_steps,
        "accumulation_steps": accumulation_steps,
        "grad_clip_norm": grad_clip_norm,
        "amp_enabled": amp_enabled,
        "enable_color_jitter": enable_color_jitter,
        "model_variant": model_variant,
        "log_every_steps": log_every_steps,
    }
    (run_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    model = _build_model(device, init_weights=init_weights if resume_checkpoint is None else None)
    optimizer = AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
    scheduler = ReduceLROnPlateau(optimizer, mode="min", factor=0.5, patience=1)
    scaler = torch.amp.GradScaler("cuda", enabled=amp_enabled and device.type == "cuda")

    start_epoch = 0
    global_step = 0
    best_val_loss = float("inf")
    if resume_checkpoint is not None and resume_checkpoint.exists():
        checkpoint = torch.load(str(resume_checkpoint), map_location=device, weights_only=False)
        model.load_state_dict(checkpoint["model_state"])
        optimizer.load_state_dict(checkpoint["optimizer_state"])
        scheduler.load_state_dict(checkpoint["scheduler_state"])
        scaler.load_state_dict(checkpoint.get("scaler_state", {}))
        start_epoch = int(checkpoint.get("epoch", 0)) + 1
        global_step = int(checkpoint.get("global_step", 0))
        best_val_loss = float(checkpoint.get("best_val_loss", best_val_loss))

    _verify_dataset_access(data_path=data_path, split_file="train.txt")
    _verify_dataset_access(data_path=data_path, split_file="val.txt")

    train_loader = _make_dataloader(
        data_path=data_path,
        split_file="train.txt",
        image_size=image_size,
        batch_size=batch_size,
        num_workers=effective_num_workers,
        shuffle=True,
        enable_color_jitter=enable_color_jitter,
        pin_memory=device.type == "cuda",
    )
    val_loader = _make_dataloader(
        data_path=data_path,
        split_file="val.txt",
        image_size=image_size,
        batch_size=1,
        num_workers=effective_num_workers,
        shuffle=False,
        enable_color_jitter=False,
        pin_memory=device.type == "cuda",
    )

    history_path = run_dir / "history.jsonl"
    best_inference_checkpoint = export_inference_checkpoint or (checkpoints_dir / "best_inference.pt")
    latest_checkpoint = checkpoints_dir / "latest.pt"
    best_checkpoint = checkpoints_dir / "best_val.pt"
    last_train_metrics = EpochMetrics(0, 0, 0, 0, 0, 0, 0, 0)
    last_val_metrics = EpochMetrics(0, 0, 0, 0, 0, 0, 0, 0)

    for epoch in range(start_epoch, epochs):
        train_metrics = _run_epoch(
            model=model,
            loader=train_loader,
            optimizer=optimizer,
            scaler=scaler,
            device=device,
            amp_enabled=amp_enabled,
            grad_clip_norm=grad_clip_norm,
            accumulation_steps=accumulation_steps,
            max_steps=max_train_steps_per_epoch,
            log_every_steps=log_every_steps,
            progress_prefix=f"train_epoch_{epoch}",
        )
        val_metrics = _run_epoch(
            model=model,
            loader=val_loader,
            optimizer=None,
            scaler=scaler,
            device=device,
            amp_enabled=amp_enabled,
            grad_clip_norm=None,
            accumulation_steps=1,
            max_steps=max_val_steps,
            log_every_steps=log_every_steps,
            progress_prefix=f"val_epoch_{epoch}",
        )
        global_step += train_metrics.steps
        scheduler.step(val_metrics.loss)
        print(
            f"Epoch {epoch+1}/{epochs}  "
            f"train_loss={train_metrics.loss:.4f}  "
            f"val_loss={val_metrics.loss:.4f}  "
            f"room_acc={val_metrics.room_acc:.3f}  "
            f"icon_acc={val_metrics.icon_acc:.3f}",
            flush=True,
        )

        record = {
            "epoch": epoch,
            "global_step": global_step,
            "train": asdict(train_metrics),
            "val": asdict(val_metrics),
            "learning_rate": optimizer.param_groups[0]["lr"],
        }
        _append_jsonl(history_path, record)

        if tensorboard_writer is not None:
            tensorboard_writer.add_scalar("train/loss", train_metrics.loss, epoch)
            tensorboard_writer.add_scalar("val/loss", val_metrics.loss, epoch)
            tensorboard_writer.add_scalar("train/room_acc", train_metrics.room_acc, epoch)
            tensorboard_writer.add_scalar("val/room_acc", val_metrics.room_acc, epoch)
            tensorboard_writer.add_scalar("train/icon_acc", train_metrics.icon_acc, epoch)
            tensorboard_writer.add_scalar("val/icon_acc", val_metrics.icon_acc, epoch)
            tensorboard_writer.add_scalar("optimizer/lr", optimizer.param_groups[0]["lr"], epoch)

        last_train_metrics = train_metrics
        last_val_metrics = val_metrics
        _save_training_checkpoint(
            latest_checkpoint,
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=scaler,
            epoch=epoch,
            global_step=global_step,
            best_val_loss=best_val_loss,
            config=config,
            last_train_metrics=train_metrics,
            last_val_metrics=val_metrics,
        )

        if val_metrics.loss < best_val_loss:
            best_val_loss = val_metrics.loss
            _save_training_checkpoint(
                best_checkpoint,
                model=model,
                optimizer=optimizer,
                scheduler=scheduler,
                scaler=scaler,
                epoch=epoch,
                global_step=global_step,
                best_val_loss=best_val_loss,
                config=config,
                last_train_metrics=train_metrics,
                last_val_metrics=val_metrics,
            )
            _export_inference_checkpoint(
                best_inference_checkpoint,
                model=model,
                model_variant=model_variant,
                epoch=epoch,
                global_step=global_step,
                val_metrics=val_metrics,
                train_metrics=train_metrics,
                source_checkpoint=str(best_checkpoint),
            )

    if tensorboard_writer is not None:
        tensorboard_writer.close()

    summary = {
        "run_dir": str(run_dir),
        "device": str(device),
        "cuda_available": torch.cuda.is_available(),
        "epochs_completed": max(0, epochs - start_epoch),
        "final_epoch": epochs - 1 if epochs > 0 else None,
        "global_step": global_step,
        "best_val_loss": best_val_loss,
        "latest_checkpoint": str(latest_checkpoint),
        "best_checkpoint": str(best_checkpoint),
        "best_inference_checkpoint": str(best_inference_checkpoint),
        "last_train_metrics": asdict(last_train_metrics),
        "last_val_metrics": asdict(last_val_metrics),
        "data_path": str(data_path),
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a full fine-tune over a CubiCasa-compatible LMDB dataset.")
    parser.add_argument(
        "--data-path",
        type=Path,
        default=_resolve_default_data_path(),
        help="Directory containing train.txt/val.txt/test.txt and cubi_lmdb/.",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=Path("data") / "training" / "runs" / f"finetune_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        help="Output directory for logs and checkpoints.",
    )
    parser.add_argument("--epochs", type=int, default=1, help="Number of training epochs.")
    parser.add_argument("--batch-size", type=int, default=2, help="Training batch size.")
    parser.add_argument("--image-size", type=int, default=256, help="Square resize target for training/eval.")
    parser.add_argument("--learning-rate", type=float, default=1e-4, help="AdamW learning rate.")
    parser.add_argument("--weight-decay", type=float, default=1e-4, help="AdamW weight decay.")
    parser.add_argument("--device", type=str, default="auto", help="Device to use: auto, cuda, cpu.")
    parser.add_argument("--num-workers", type=int, default=0, help="DataLoader workers.")
    parser.add_argument("--seed", type=int, default=13, help="Random seed.")
    parser.add_argument(
        "--init-weights",
        type=Path,
        default=DEFAULT_BASELINE_WEIGHTS,
        help="Initial model weights. Use empty string to train from scratch.",
    )
    parser.add_argument("--resume", type=Path, default=None, help="Resume from a training checkpoint.")
    parser.add_argument("--max-train-steps-per-epoch", type=int, default=0, help="Optional train step cap per epoch.")
    parser.add_argument("--max-val-steps", type=int, default=0, help="Optional validation step cap per epoch.")
    parser.add_argument("--accumulation-steps", type=int, default=1, help="Gradient accumulation steps.")
    parser.add_argument("--grad-clip-norm", type=float, default=1.0, help="Gradient clipping norm. Use <=0 to disable.")
    parser.add_argument("--amp", action="store_true", help="Enable mixed precision on CUDA.")
    parser.add_argument("--no-amp", action="store_true", help="Force-disable mixed precision.")
    parser.add_argument("--no-color-jitter", action="store_true", help="Disable color jitter in training.")
    parser.add_argument("--model-variant", type=str, default="baseline", help="Variant label for exported inference checkpoint.")
    parser.add_argument("--export-inference-checkpoint", type=Path, default=None, help="Optional path for best inference checkpoint.")
    parser.add_argument("--log-every-steps", type=int, default=100, help="Emit running metrics every N steps.")
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=None,
        help="Optional explicit location for the final summary JSON.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    init_weights = None if str(args.init_weights).strip() == "" else args.init_weights
    summary = run_finetune(
        data_path=args.data_path,
        run_dir=args.run_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        image_size=args.image_size,
        learning_rate=args.learning_rate,
        weight_decay=args.weight_decay,
        device_name=args.device,
        num_workers=args.num_workers,
        seed=args.seed,
        init_weights=init_weights,
        resume_checkpoint=args.resume,
        max_train_steps_per_epoch=args.max_train_steps_per_epoch,
        max_val_steps=args.max_val_steps,
        accumulation_steps=max(args.accumulation_steps, 1),
        grad_clip_norm=None if args.grad_clip_norm <= 0 else args.grad_clip_norm,
        amp_enabled=args.amp and not args.no_amp,
        enable_color_jitter=not args.no_color_jitter,
        model_variant=args.model_variant,
        export_inference_checkpoint=args.export_inference_checkpoint,
        log_every_steps=args.log_every_steps,
    )
    if args.output_summary:
        args.output_summary.parent.mkdir(parents=True, exist_ok=True)
        args.output_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
