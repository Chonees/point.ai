"""
convert_labels_segformer.py — Merge 2-channel CubiCasa labels into
single-channel SegFormer-compatible labels (14 classes).

Channel 0 (rooms):  background(0), outdoor(1), wall(2), kitchen(3),
                    living(4), bedroom(5), bath(6), entry(7), railing(8),
                    storage(9), garage(10), room(11)
Channel 1 (icons):  window(1) → 12, door(2) → 13
                    Icons 3-10 ignored (not used for DXF).

Usage:
    python -m training.convert_labels_segformer --input D:/training_v2/converted/cubicasa
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

MERGED_CLASSES = {
    0: "background",
    1: "outdoor",
    2: "wall",
    3: "kitchen",
    4: "living",
    5: "bedroom",
    6: "bath",
    7: "entry",
    8: "railing",
    9: "storage",
    10: "garage",
    11: "room",
    12: "window",
    13: "door",
}

NUM_CLASSES = len(MERGED_CLASSES)


def merge_label(label_2ch: np.ndarray) -> np.ndarray:
    """Convert (2, H, W) CubiCasa label to (H, W) merged label with 14 classes."""
    rooms = label_2ch[0]  # (H, W), values 0-11
    icons = label_2ch[1]  # (H, W), values 0-10

    merged = rooms.copy()  # base = room classes 0-11

    # Icons take priority where present
    merged[icons == 1] = 12  # window
    merged[icons == 2] = 13  # door
    # Icons 3-10 ignored — pixels keep their room class

    return merged.astype(np.uint8)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert labels to SegFormer format")
    parser.add_argument("--input", type=str, required=True, help="Root dir with cubicasa/ and pointai/ subdirs")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing label_merged.npy")
    args = parser.parse_args()

    root = Path(args.input)
    class_pixels: dict[int, int] = defaultdict(int)
    done = skipped = errors = 0

    # Find all sample directories
    sample_dirs: list[Path] = []
    for subdir in sorted(root.iterdir()):
        if subdir.is_dir():
            # Check if it's a sample dir (has label.npy) or a parent dir
            if (subdir / "label.npy").exists():
                sample_dirs.append(subdir)
            else:
                # Recurse one level (cubicasa/cubicasa-xxx, pointai/pointai-xxx)
                for child in sorted(subdir.iterdir()):
                    if child.is_dir() and (child / "label.npy").exists():
                        sample_dirs.append(child)

    print(f"Found {len(sample_dirs)} samples")

    for sample_dir in sample_dirs:
        out_path = sample_dir / "label_merged.npy"
        if out_path.exists() and not args.overwrite:
            skipped += 1
            continue

        try:
            label = np.load(str(sample_dir / "label.npy"))
            if label.ndim != 3 or label.shape[0] != 2:
                print(f"  SKIP {sample_dir.name}: unexpected shape {label.shape}")
                skipped += 1
                continue

            merged = merge_label(label)
            np.save(str(out_path), merged)

            # Accumulate class stats
            for cls_id in range(NUM_CLASSES):
                class_pixels[cls_id] += int(np.sum(merged == cls_id))

            done += 1
        except Exception as e:
            errors += 1
            if errors <= 10:
                print(f"  ERROR {sample_dir.name}: {e}")

        if done > 0 and done % 500 == 0:
            print(f"  Progress: done={done} skipped={skipped} errors={errors}")

    print(f"\nDone: {done}  Skipped: {skipped}  Errors: {errors}")

    # Print class distribution
    total = sum(class_pixels.values()) or 1
    print(f"\n{'Class':<15} {'Pixels':>12} {'%':>8}")
    print("-" * 37)
    for cls_id in range(NUM_CLASSES):
        name = MERGED_CLASSES[cls_id]
        count = class_pixels[cls_id]
        pct = count / total * 100
        print(f"{name:<15} {count:>12,} {pct:>7.2f}%")

    # Save stats
    stats_path = root / "segformer_class_stats.json"
    stats = {
        "total_pixels": total,
        "num_samples": done,
        "classes": {
            str(cls_id): {"name": MERGED_CLASSES[cls_id], "pixels": class_pixels[cls_id]}
            for cls_id in range(NUM_CLASSES)
        },
    }
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\nStats saved to {stats_path}")


if __name__ == "__main__":
    main()
