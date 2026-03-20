"""
segformer_dataset.py — PyTorch Dataset for SegFormer floor plan training.

Reads image.png + label_merged.npy directly from disk (no LMDB).
Resizes to fixed size, applies augmentations for training.
"""
from __future__ import annotations

import random
from pathlib import Path

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset

# ImageNet normalization (SegFormer pretrained stats)
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class FloorPlanSegFormerDataset(Dataset):
    """Dataset that loads image + merged label for SegFormer training."""

    def __init__(
        self,
        sample_dirs: list[Path],
        image_size: int = 512,
        augment: bool = False,
    ):
        self.sample_dirs = sample_dirs
        self.image_size = image_size
        self.augment = augment

    def __len__(self) -> int:
        return len(self.sample_dirs)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        sample_dir = self.sample_dirs[idx]

        # Load image
        img_path = sample_dir / "image.png"
        img = cv2.imread(str(img_path))
        if img is None:
            raise FileNotFoundError(f"Cannot read {img_path}")
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # Load merged label
        label_path = sample_dir / "label_merged.npy"
        label = np.load(str(label_path))  # (H, W) uint8

        # Augmentations (before resize for variety)
        if self.augment:
            img, label = self._augment(img, label)

        # Resize
        img = cv2.resize(img, (self.image_size, self.image_size), interpolation=cv2.INTER_AREA)
        label = cv2.resize(label, (self.image_size, self.image_size), interpolation=cv2.INTER_NEAREST)

        # Normalize image: [0,255] → [0,1] → ImageNet norm
        img = img.astype(np.float32) / 255.0
        img = (img - IMAGENET_MEAN) / IMAGENET_STD

        # To tensors
        pixel_values = torch.from_numpy(img.transpose(2, 0, 1))  # (3, H, W)
        labels = torch.from_numpy(label.astype(np.int64))  # (H, W)

        return {"pixel_values": pixel_values, "labels": labels}

    def _augment(self, img: np.ndarray, label: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        # Random horizontal flip
        if random.random() > 0.5:
            img = np.fliplr(img).copy()
            label = np.fliplr(label).copy()

        # Random vertical flip
        if random.random() > 0.5:
            img = np.flipud(img).copy()
            label = np.flipud(label).copy()

        # Random 90/180/270 rotation
        k = random.randint(0, 3)
        if k > 0:
            img = np.rot90(img, k).copy()
            label = np.rot90(label, k).copy()

        # Color jitter (image only)
        if random.random() > 0.5:
            # Brightness
            factor = random.uniform(0.8, 1.2)
            img = np.clip(img * factor, 0, 255).astype(np.uint8)

        if random.random() > 0.5:
            # Contrast
            factor = random.uniform(0.8, 1.2)
            mean = img.mean()
            img = np.clip((img - mean) * factor + mean, 0, 255).astype(np.uint8)

        return img, label


def discover_samples(root: Path) -> list[Path]:
    """Find all sample directories with image.png + label_merged.npy."""
    samples = []
    for subdir in sorted(root.iterdir()):
        if not subdir.is_dir():
            continue
        if (subdir / "label_merged.npy").exists() and (subdir / "image.png").exists():
            samples.append(subdir)
        else:
            # Check one level deeper
            for child in sorted(subdir.iterdir()):
                if child.is_dir() and (child / "label_merged.npy").exists() and (child / "image.png").exists():
                    samples.append(child)
    return samples


def split_samples(
    samples: list[Path], val_ratio: float = 0.15, seed: int = 42
) -> tuple[list[Path], list[Path]]:
    """Split samples into train/val."""
    rng = random.Random(seed)
    shuffled = list(samples)
    rng.shuffle(shuffled)
    n_val = max(1, int(len(shuffled) * val_ratio))
    return shuffled[n_val:], shuffled[:n_val]
