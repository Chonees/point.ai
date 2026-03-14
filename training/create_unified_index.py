from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

from training.common import load_jsonl, write_jsonl


def build_dataset_splits(
    entries: list[dict[str, Any]],
    *,
    seed: int = 13,
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        grouped[entry["dataset"]].append(dict(entry))

    rng = random.Random(seed)
    train: list[dict[str, Any]] = []
    val: list[dict[str, Any]] = []
    test: list[dict[str, Any]] = []

    for dataset_entries in grouped.values():
        rng.shuffle(dataset_entries)
        total = len(dataset_entries)
        train_count = int(total * train_ratio)
        val_count = int(total * val_ratio)
        test_count = total - train_count - val_count

        if total >= 3:
            if val_count == 0:
                val_count = 1
                train_count = max(train_count - 1, 1)
            if test_count == 0:
                test_count = 1
                train_count = max(train_count - 1, 1)
        elif total == 2:
            train_count = 1
            val_count = 0
            test_count = 1
        elif total == 1:
            train_count = 1
            val_count = 0
            test_count = 0

        train.extend(dataset_entries[:train_count])
        val.extend(dataset_entries[train_count : train_count + val_count])
        test.extend(dataset_entries[train_count + val_count : train_count + val_count + test_count])

    return {
        "train": sorted(train, key=lambda entry: (entry["dataset"], entry["sample_id"])),
        "val": sorted(val, key=lambda entry: (entry["dataset"], entry["sample_id"])),
        "test": sorted(test, key=lambda entry: (entry["dataset"], entry["sample_id"])),
    }


def create_unified_index(
    manifest_paths: list[Path],
    output_dir: Path,
    *,
    seed: int = 13,
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
) -> dict[str, list[dict[str, Any]]]:
    entries: list[dict[str, Any]] = []
    for manifest_path in manifest_paths:
        entries.extend(load_jsonl(manifest_path))

    splits = build_dataset_splits(
        entries,
        seed=seed,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    for split_name, split_entries in splits.items():
        write_jsonl(output_dir / f"{split_name}.jsonl", split_entries)

    summary = {
        "seed": seed,
        "train_ratio": train_ratio,
        "val_ratio": val_ratio,
        "test_ratio": max(0.0, 1.0 - train_ratio - val_ratio),
        "counts": {split_name: len(split_entries) for split_name, split_entries in splits.items()},
        "datasets": sorted({entry["dataset"] for entry in entries}),
        "manifest_paths": [str(path) for path in manifest_paths],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return splits


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create reproducible train/val/test splits from converted manifests.")
    parser.add_argument("manifests", nargs="+", type=Path, help="Input manifest JSONL files.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "training" / "unified_index",
        help="Directory where train/val/test JSONL files will be written.",
    )
    parser.add_argument("--seed", type=int, default=13, help="Shuffle seed.")
    parser.add_argument("--train-ratio", type=float, default=0.8, help="Train split ratio.")
    parser.add_argument("--val-ratio", type=float, default=0.1, help="Validation split ratio.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    create_unified_index(
        args.manifests,
        args.output,
        seed=args.seed,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
    )
    print(f"Wrote unified index to {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
