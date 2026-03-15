from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any

import cv2
import numpy as np

from training.common import ICON_LABELS, ROOM_LABELS, load_jsonl, write_jsonl
from training.export_lmdb import resolve_manifest_entry_paths


def load_entry_arrays(manifest_path: Path, entry: dict[str, Any]) -> dict[str, Any]:
    paths = resolve_manifest_entry_paths(manifest_path, entry)
    image_bgr = cv2.imread(str(paths["image_path"]), cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise FileNotFoundError(f"Could not read image at {paths['image_path']}")
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    label = np.load(paths["label_path"]).astype(np.uint8)
    heatmaps = json.loads(paths["heatmaps_path"].read_text(encoding="utf-8"))
    meta = json.loads(paths["meta_path"].read_text(encoding="utf-8"))
    return {
        "image": image_rgb,
        "label": label,
        "heatmaps": {int(channel): coords for channel, coords in heatmaps.items()},
        "meta": meta,
    }


def score_sample(entry: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any]:
    image = sample["image"]
    label = sample["label"]
    heatmaps = sample["heatmaps"]
    meta = sample["meta"]

    room_mask = label[0]
    icon_mask = label[1]
    height, width = room_mask.shape
    total_pixels = int(height * width)
    wall_pixels = int(np.count_nonzero(room_mask == ROOM_LABELS["wall"]))
    outdoor_pixels = int(np.count_nonzero(room_mask == ROOM_LABELS["outdoor"]))
    room_pixels = int(
        np.count_nonzero(
            ~np.isin(
                room_mask,
                [ROOM_LABELS["background"], ROOM_LABELS["outdoor"], ROOM_LABELS["wall"]],
            )
        )
    )
    opening_pixels = int(np.count_nonzero(np.isin(icon_mask, [ICON_LABELS["window"], ICON_LABELS["door"]])))
    icon_pixels = int(np.count_nonzero(icon_mask != ICON_LABELS["background"]))

    room_labels_present = sorted(int(v) for v in np.unique(room_mask))
    icon_labels_present = sorted(int(v) for v in np.unique(icon_mask))
    semantic_room_count = len(
        [
            value
            for value in room_labels_present
            if value not in {ROOM_LABELS["background"], ROOM_LABELS["outdoor"], ROOM_LABELS["wall"]}
        ]
    )
    active_heatmap_channels = sum(1 for coords in heatmaps.values() if coords)
    heatmap_point_count = sum(len(coords) for coords in heatmaps.values())

    wall_ratio = wall_pixels / max(total_pixels, 1)
    room_ratio = room_pixels / max(total_pixels, 1)
    opening_ratio = opening_pixels / max(total_pixels, 1)

    flags: list[str] = []
    if wall_pixels == 0:
        flags.append("no_walls")
    if room_pixels == 0:
        flags.append("no_rooms")
    if opening_pixels == 0:
        flags.append("no_openings")
    if heatmap_point_count < 4:
        flags.append("sparse_heatmaps")
    if wall_ratio < 0.01:
        flags.append("wall_ratio_too_low")
    if wall_ratio > 0.60:
        flags.append("wall_ratio_too_high")
    if min(height, width) < 96:
        flags.append("tiny_image")
    if max(height, width) > 2048:
        flags.append("oversized_image")
    if semantic_room_count < 2:
        flags.append("limited_room_diversity")

    score = 0
    if wall_pixels > 0:
        score += 15
        if 0.03 <= wall_ratio <= 0.35:
            score += 10
    if room_pixels > 0:
        score += 10
        score += min(semantic_room_count * 5, 20)
    if opening_pixels > 0:
        score += 15
    if active_heatmap_channels >= 6:
        score += 15
    elif active_heatmap_channels >= 2:
        score += 8
    if min(height, width) >= 128:
        score += 10
    if max(height, width) <= 1024:
        score += 5

    for flag in flags:
        if flag in {"no_walls", "no_rooms"}:
            score -= 30
        elif flag in {"wall_ratio_too_low", "wall_ratio_too_high"}:
            score -= 15
        elif flag == "no_openings":
            score -= 10
        else:
            score -= 5
    score = max(0, min(100, score))

    return {
        "sample_id": entry["sample_id"],
        "dataset": entry["dataset"],
        "source_id": entry.get("source_id"),
        "image_shape": [int(height), int(width)],
        "wall_pixels": wall_pixels,
        "room_pixels": room_pixels,
        "outdoor_pixels": outdoor_pixels,
        "opening_pixels": opening_pixels,
        "icon_pixels": icon_pixels,
        "wall_ratio": wall_ratio,
        "room_ratio": room_ratio,
        "opening_ratio": opening_ratio,
        "room_labels_present": room_labels_present,
        "icon_labels_present": icon_labels_present,
        "semantic_room_count": semantic_room_count,
        "active_heatmap_channels": active_heatmap_channels,
        "heatmap_point_count": heatmap_point_count,
        "flags": flags,
        "quality_score": score,
        "meta_snapshot": {
            "area": meta.get("area"),
            "net_area": meta.get("net_area"),
            "unit_type": meta.get("unit_type"),
            "source_split": meta.get("source_split"),
            "source_partition": meta.get("source_partition"),
        },
    }


def summarize_audit(records: list[dict[str, Any]], *, manifest_path: Path) -> dict[str, Any]:
    if not records:
        return {
            "manifest_path": str(manifest_path),
            "sample_count": 0,
            "dataset_counts": {},
            "average_quality_score": 0.0,
            "flag_counts": {},
        }

    dataset_counts: dict[str, int] = {}
    flag_counts: dict[str, int] = {}
    for record in records:
        dataset_counts[record["dataset"]] = dataset_counts.get(record["dataset"], 0) + 1
        for flag in record["flags"]:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1

    scores = [record["quality_score"] for record in records]
    return {
        "manifest_path": str(manifest_path),
        "sample_count": len(records),
        "dataset_counts": dataset_counts,
        "average_quality_score": mean(scores),
        "min_quality_score": min(scores),
        "max_quality_score": max(scores),
        "flag_counts": flag_counts,
    }


def audit_manifest(
    manifest_path: Path,
    output_dir: Path,
    *,
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    entries = load_jsonl(manifest_path)
    if limit is not None:
        entries = entries[:limit]

    records: list[dict[str, Any]] = []
    for entry in entries:
        sample = load_entry_arrays(manifest_path, entry)
        records.append(score_sample(entry, sample))

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = manifest_path.stem.replace("_manifest", "")
    report_path = output_dir / f"{stem}_audit.jsonl"
    summary_path = output_dir / f"{stem}_audit_summary.json"
    write_jsonl(report_path, records)
    summary = summarize_audit(records, manifest_path=manifest_path)
    summary["report_path"] = str(report_path)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return records, summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit converted training manifests and score dataset richness.")
    parser.add_argument("manifests", nargs="+", type=Path, help="Manifest JSONL files to audit.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "training" / "audits",
        help="Directory where audit JSONL and summary files will be written.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Optional per-manifest record limit. Use 0 for all.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    limit = None if args.limit == 0 else args.limit
    summaries = []
    for manifest in args.manifests:
        _, summary = audit_manifest(manifest, args.output, limit=limit)
        summaries.append(summary)
    print(json.dumps(summaries, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
