from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from training.common import ConvertedSample, save_converted_sample, write_jsonl

DEFAULT_CUBICASA_DIR = (
    Path(__file__).resolve().parents[1]
    / ".."
    / "floorplan-research"
    / "CubiCasa5k"
    / "cubicasa5k"
    / "cubicasa5k"
).resolve()

_CUBICASA_ROOT = (
    Path(__file__).resolve().parents[1]
    / ".."
    / "floorplan-research"
    / "CubiCasa5k"
).resolve()
if str(_CUBICASA_ROOT) not in sys.path:
    sys.path.insert(0, str(_CUBICASA_ROOT))


def _sample_image_name(use_original: bool) -> str:
    return "F1_original.png" if use_original else "F1_scaled.png"


def _resolve_image_path(sample_dir: Path, *, use_original: bool) -> tuple[Path, str]:
    preferred = sample_dir / _sample_image_name(use_original)
    if preferred.exists():
        return preferred, "original" if use_original else "scaled"

    fallback = sample_dir / "F1_scaled.png"
    if fallback.exists():
        return fallback, "scaled"

    raise FileNotFoundError(f"Could not find a CubiCasa floor image in {sample_dir}")


def collect_cubicasa_entries(
    input_dir: Path,
    *,
    include_splits: tuple[str, ...] = ("train", "val", "test"),
) -> list[dict[str, Any]]:
    """Collect unique CubiCasa sample folders from the original split files."""
    entries: list[dict[str, Any]] = []
    seen: set[Path] = set()

    for split_name in include_splits:
        split_file = input_dir / f"{split_name}.txt"
        if not split_file.exists():
            continue

        for raw_line in split_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            relative = Path(line.strip("/\\"))
            sample_dir = input_dir / relative
            if sample_dir in seen:
                continue
            if not sample_dir.exists():
                continue
            if not (sample_dir / "model.svg").exists():
                continue
            if not (sample_dir / "F1_scaled.png").exists():
                continue

            seen.add(sample_dir)
            entries.append(
                {
                    "split": split_name,
                    "relative_path": relative.as_posix(),
                    "sample_dir": sample_dir,
                }
            )

    if entries:
        return entries

    # Fallback for cases where split files are missing: discover folders directly.
    for svg_path in sorted(input_dir.rglob("model.svg")):
        sample_dir = svg_path.parent
        if not (sample_dir / "F1_scaled.png").exists():
            continue
        relative = sample_dir.relative_to(input_dir)
        entries.append(
            {
                "split": "unknown",
                "relative_path": relative.as_posix(),
                "sample_dir": sample_dir,
            }
        )
    return entries


def _load_house_class():
    try:
        from floortrans.loaders.house import House
    except Exception as exc:  # pragma: no cover - depends on local env
        raise RuntimeError(f"Could not import CubiCasa House parser: {exc}") from exc
    return House


def _load_cubicasa_arrays(sample_dir: Path, *, use_original: bool) -> dict[str, Any]:
    image_path, image_variant = _resolve_image_path(sample_dir, use_original=use_original)
    svg_path = sample_dir / "model.svg"

    image_bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise FileNotFoundError(f"Could not read CubiCasa image at {image_path}")
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    height, width = image_rgb.shape[:2]

    House = _load_house_class()
    house = House(str(svg_path), height, width)

    label = house.get_segmentation_tensor().astype(np.uint8)
    heatmaps = {
        int(channel): [(int(x), int(y)) for x, y in coords]
        for channel, coords in house.get_heatmap_dict().items()
    }
    image_chw = np.moveaxis(image_rgb, -1, 0).astype(np.uint8)

    floor_images = sorted(path.name for path in sample_dir.glob("F*_scaled.png"))
    floor_originals = sorted(path.name for path in sample_dir.glob("F*_original.png"))

    return {
        "image": image_chw,
        "label": label,
        "heatmaps": heatmaps,
        "scale": 1.0,
        "meta": {
            "dataset": "cubicasa",
            "source_id": sample_dir.name,
            "relative_path": sample_dir.name,
            "image_variant": image_variant,
            "image_shape": [int(height), int(width)],
            "floor_scaled_images": floor_images,
            "floor_original_images": floor_originals,
            "room_labels_present": sorted(int(value) for value in np.unique(label[0])),
            "icon_labels_present": sorted(int(value) for value in np.unique(label[1])),
            "heatmap_counts": {str(channel): len(coords) for channel, coords in heatmaps.items()},
        },
    }


def convert_cubicasa_sample_dir(
    sample_dir: Path,
    *,
    split: str = "unknown",
    relative_path: str | None = None,
    use_original: bool = False,
) -> ConvertedSample:
    payload = _load_cubicasa_arrays(sample_dir, use_original=use_original)
    relative_path = relative_path or sample_dir.name
    relative_parts = Path(relative_path).parts
    partition = relative_parts[0] if relative_parts else "unknown"
    source_id = "/".join(relative_parts) if relative_parts else sample_dir.name
    safe_source_id = "-".join(part for part in relative_parts if part) or sample_dir.name
    sample_id = f"cubicasa-{safe_source_id}"

    meta = dict(payload["meta"])
    meta.update(
        {
            "dataset": "cubicasa",
            "source_id": source_id,
            "source_split": split,
            "source_partition": partition,
            "relative_path": relative_path,
        }
    )

    return ConvertedSample(
        dataset="cubicasa",
        sample_id=sample_id,
        source_id=source_id,
        image=payload["image"],
        label=payload["label"],
        heatmaps=payload["heatmaps"],
        scale=float(payload["scale"]),
        meta=meta,
    )


def convert_cubicasa_dataset(
    input_dir: Path,
    output_dir: Path,
    *,
    limit: int | None = None,
    preview_limit: int = 20,
    use_original: bool = False,
    include_splits: tuple[str, ...] = ("train", "val", "test"),
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    entries = collect_cubicasa_entries(input_dir, include_splits=include_splits)
    if limit is not None:
        entries = entries[:limit]

    manifest: list[dict[str, Any]] = []
    split_counts: dict[str, int] = {}
    partition_counts: dict[str, int] = {}

    errors = 0
    for index, entry in enumerate(entries):
        try:
            sample = convert_cubicasa_sample_dir(
                entry["sample_dir"],
                split=entry["split"],
                relative_path=entry["relative_path"],
                use_original=use_original,
            )
            manifest_entry = save_converted_sample(
                sample,
                output_dir,
                write_preview=index < preview_limit,
            )
            manifest_entry["source_split"] = entry["split"]
            manifest_entry["source_partition"] = sample.meta["source_partition"]
            manifest_entry["relative_path"] = entry["relative_path"]
            manifest.append(manifest_entry)

            split_counts[entry["split"]] = split_counts.get(entry["split"], 0) + 1
            partition = sample.meta["source_partition"]
            partition_counts[partition] = partition_counts.get(partition, 0) + 1
        except Exception as e:
            errors += 1
            if errors <= 10:
                print(f"  ERROR {entry['relative_path']}: {e}")

        if (index + 1) % 200 == 0:
            print(f"  Progress: {index + 1}/{len(entries)}  converted={len(manifest)} errors={errors}")

    manifest_path = output_dir / "cubicasa_manifest.jsonl"
    write_jsonl(manifest_path, manifest)

    summary = {
        "dataset": "cubicasa",
        "sample_count": len(manifest),
        "manifest_path": str(manifest_path),
        "preview_limit": preview_limit,
        "use_original": use_original,
        "split_counts": split_counts,
        "partition_counts": partition_counts,
    }
    (output_dir / "cubicasa_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return manifest


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert CubiCasa5k into Point.ai training samples.")
    parser.add_argument("--input", type=Path, default=DEFAULT_CUBICASA_DIR, help="Path to the CubiCasa dataset root.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "training" / "cubicasa_pilot",
        help="Output directory for converted samples.",
    )
    parser.add_argument("--limit", type=int, default=100, help="Maximum number of samples to convert. Use 0 for all.")
    parser.add_argument("--preview-limit", type=int, default=20, help="How many preview PNGs to write.")
    parser.add_argument("--use-original", action="store_true", help="Use F1_original.png instead of F1_scaled.png.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    manifest = convert_cubicasa_dataset(
        args.input,
        args.output,
        limit=None if args.limit == 0 else args.limit,
        preview_limit=args.preview_limit,
        use_original=args.use_original,
    )
    print(f"Converted {len(manifest)} CubiCasa sample(s) into {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
