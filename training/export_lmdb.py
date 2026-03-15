from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path
from typing import Any

import cv2
import lmdb
import numpy as np
import torch

from training.common import load_jsonl


def _ensure_trailing_sep(path: Path) -> str:
    text = str(path)
    if text.endswith(("/", "\\")):
        return text
    return text + "\\"


def resolve_manifest_entry_paths(manifest_path: Path, entry: dict[str, Any]) -> dict[str, Path]:
    source_manifest = Path(entry.get("_manifest_path", manifest_path))
    base_dir = source_manifest.parent
    return {
        "source_manifest": source_manifest,
        "base_dir": base_dir,
        "image_path": base_dir / entry["image_path"],
        "label_path": base_dir / entry["label_path"],
        "heatmaps_path": base_dir / entry["heatmaps_path"],
        "meta_path": base_dir / entry["meta_path"],
    }


def load_manifest_entry(manifest_path: Path, entry: dict[str, Any]) -> dict[str, Any]:
    paths = resolve_manifest_entry_paths(manifest_path, entry)
    image_path = paths["image_path"]
    label_path = paths["label_path"]
    heatmaps_path = paths["heatmaps_path"]

    image_bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise FileNotFoundError(f"Could not read image at {image_path}")
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    image_chw = np.moveaxis(image_rgb, -1, 0).astype(np.float32)

    label = np.load(label_path).astype(np.float32)
    heatmaps_raw = json.loads(heatmaps_path.read_text(encoding="utf-8"))
    heatmaps = {
        int(channel): [(float(x), float(y)) for x, y in coords]
        for channel, coords in heatmaps_raw.items()
    }

    return {
        "image": torch.tensor(image_chw),
        "label": torch.tensor(label),
        "folder": entry["sample_id"],
        "heatmaps": heatmaps,
        "scale": float(entry.get("scale", 1.0)),
    }


def estimate_manifest_entry_bytes(manifest_path: Path, entry: dict[str, Any]) -> int:
    paths = resolve_manifest_entry_paths(manifest_path, entry)
    total = 0
    for key in ("image_path", "label_path", "heatmaps_path", "meta_path"):
        total += paths[key].stat().st_size
    return total


def estimate_lmdb_map_size_bytes(
    manifest_path: Path,
    entries: list[dict[str, Any]],
    *,
    overhead_factor: float = 4.0,
    minimum_bytes: int = int(8e9),
) -> int:
    raw_size = sum(estimate_manifest_entry_bytes(manifest_path, entry) for entry in entries)
    estimated = int(max(raw_size * overhead_factor + int(1e9), minimum_bytes))
    # LMDB map size works better aligned to a large page boundary.
    block = 1 << 30
    remainder = estimated % block
    if remainder:
        estimated += block - remainder
    return estimated


def export_manifest_entries_to_lmdb(
    manifest_path: Path,
    entries: list[dict[str, Any]],
    output_dir: Path,
    *,
    lmdb_folder: str = "cubi_lmdb",
    overwrite: bool = True,
    map_size_bytes: int | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    lmdb_dir = output_dir / lmdb_folder
    lmdb_dir.mkdir(parents=True, exist_ok=True)

    effective_map_size = map_size_bytes or estimate_lmdb_map_size_bytes(manifest_path, entries)
    env = lmdb.open(str(lmdb_dir), map_size=effective_map_size)
    written = 0
    try:
        for entry in entries:
            sample = load_manifest_entry(manifest_path, entry)
            key = entry["sample_id"].encode("utf-8")
            payload = pickle.dumps(sample)
            while True:
                try:
                    with env.begin(write=True) as txn:
                        if not overwrite and txn.get(key) is not None:
                            break
                        txn.put(key, payload)
                        written += 1
                    break
                except lmdb.MapFullError:
                    effective_map_size *= 2
                    env.set_mapsize(effective_map_size)
    finally:
        env.close()

    return {
        "lmdb_dir": str(lmdb_dir),
        "entries_written": written,
        "entry_count": len(entries),
        "map_size_bytes": effective_map_size,
    }


def export_splits_to_cubi_layout(
    *,
    manifest_path: Path,
    split_dir: Path,
    output_dir: Path,
    lmdb_folder: str = "cubi_lmdb",
    overwrite: bool = True,
    map_size_bytes: int | None = None,
) -> dict[str, Any]:
    split_entries: dict[str, list[dict[str, Any]]] = {}
    all_entries_by_id: dict[str, dict[str, Any]] = {}
    duplicated_singleton_splits: list[str] = []

    for split_name in ("train", "val", "test"):
        entries = load_jsonl(split_dir / f"{split_name}.jsonl")
        split_entries[split_name] = entries
        for entry in entries:
            all_entries_by_id[entry["sample_id"]] = entry

    export_summary = export_manifest_entries_to_lmdb(
        manifest_path,
        list(all_entries_by_id.values()),
        output_dir,
        lmdb_folder=lmdb_folder,
        overwrite=overwrite,
        map_size_bytes=map_size_bytes,
    )

    for split_name, entries in split_entries.items():
        txt_path = output_dir / f"{split_name}.txt"
        txt_entries = [entry["sample_id"] for entry in entries]
        if len(txt_entries) == 1:
            txt_entries.append(txt_entries[0])
            duplicated_singleton_splits.append(split_name)
        txt_path.write_text(
            "\n".join(txt_entries) + ("\n" if txt_entries else ""),
            encoding="utf-8",
        )

    layout_summary = {
        "data_path": _ensure_trailing_sep(output_dir),
        "lmdb_folder": f"{lmdb_folder}/",
        "split_counts": {name: len(items) for name, items in split_entries.items()},
        "duplicated_singleton_splits": duplicated_singleton_splits,
        **export_summary,
    }
    (output_dir / "layout_summary.json").write_text(
        json.dumps(layout_summary, indent=2),
        encoding="utf-8",
    )
    return layout_summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export converted training samples into CubiCasa-compatible LMDB layout.")
    parser.add_argument("--manifest", type=Path, required=True, help="Manifest JSONL generated by a converter.")
    parser.add_argument("--split-dir", type=Path, required=True, help="Directory containing train/val/test JSONL files.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "training" / "cubi_resplan_ready",
        help="Output directory that will contain cubi_lmdb/ and split txt files.",
    )
    parser.add_argument("--lmdb-folder", type=str, default="cubi_lmdb", help="Name of the LMDB subdirectory.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing LMDB keys.")
    parser.add_argument(
        "--map-size-gb",
        type=float,
        default=0.0,
        help="Optional LMDB map size in GiB. Use 0 to auto-estimate.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    summary = export_splits_to_cubi_layout(
        manifest_path=args.manifest,
        split_dir=args.split_dir,
        output_dir=args.output,
        lmdb_folder=args.lmdb_folder,
        overwrite=args.overwrite,
        map_size_bytes=int(args.map_size_gb * (1 << 30)) if args.map_size_gb > 0 else None,
    )
    print(
        f"Exported {summary['entries_written']} entries to {summary['lmdb_dir']} "
        f"with splits {summary['split_counts']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
