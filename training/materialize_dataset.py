from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from training.common import load_jsonl, write_jsonl
from training.export_lmdb import resolve_manifest_entry_paths


def _normalized_relpath(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _copy_file_resilient(
    source: Path,
    target: Path,
    *,
    retries: int,
    chunk_size_bytes: int,
    skip_existing: bool,
) -> None:
    source_size = source.stat().st_size
    if skip_existing and target.exists() and target.stat().st_size == source_size:
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    last_error: OSError | None = None
    for attempt in range(retries + 1):
        try:
            existing_size = target.stat().st_size if target.exists() else 0
            if existing_size > source_size:
                target.unlink(missing_ok=True)
                existing_size = 0

            with source.open("rb") as src, target.open("ab" if existing_size else "wb") as dst:
                if existing_size:
                    src.seek(existing_size)
                while True:
                    chunk = src.read(chunk_size_bytes)
                    if not chunk:
                        break
                    dst.write(chunk)
                dst.flush()
                os.fsync(dst.fileno())
            if target.stat().st_size != source_size:
                raise OSError(
                    f"Size mismatch after copy: {source} -> {target} "
                    f"({source_size} != {target.stat().st_size})"
                )
            return
        except OSError as exc:
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(min(2 ** attempt, 10))
    assert last_error is not None
    raise last_error


def materialize_manifest(
    *,
    manifest_path: Path,
    output_root: Path,
    include_preview: bool = False,
    retries: int = 5,
    chunk_size_mb: int = 4,
    skip_existing: bool = True,
) -> list[dict[str, Any]]:
    output_root.mkdir(parents=True, exist_ok=True)
    samples_root = output_root / "samples"
    entries = load_jsonl(manifest_path)
    materialized_entries: list[dict[str, Any]] = []
    chunk_size_bytes = chunk_size_mb * 1024 * 1024

    for entry in entries:
        resolved = resolve_manifest_entry_paths(manifest_path, entry)
        sample_root = samples_root / entry["dataset"] / entry["sample_id"]
        sample_root.mkdir(parents=True, exist_ok=True)

        file_map = {
            "image_path": sample_root / "image.png",
            "label_path": sample_root / "label.npy",
            "heatmaps_path": sample_root / "heatmaps.json",
            "meta_path": sample_root / "meta.json",
        }
        if include_preview and entry.get("preview_path"):
            file_map["preview_path"] = sample_root / "preview.png"

        for key, target in file_map.items():
            source_key = key if key != "preview_path" else "preview_path"
            if source_key == "preview_path":
                source_manifest = Path(entry.get("_manifest_path", manifest_path))
                preview_path = source_manifest.parent / entry["preview_path"]
                if preview_path.exists():
                    _copy_file_resilient(
                        preview_path,
                        target,
                        retries=retries,
                        chunk_size_bytes=chunk_size_bytes,
                        skip_existing=skip_existing,
                    )
                continue

            resolved_key = key
            source_path = resolved[resolved_key]
            _copy_file_resilient(
                source_path,
                target,
                retries=retries,
                chunk_size_bytes=chunk_size_bytes,
                skip_existing=skip_existing,
            )

        new_entry = dict(entry)
        new_entry.pop("_manifest_path", None)
        for key, target in file_map.items():
            new_entry[key] = _normalized_relpath(target, output_root)
        if not include_preview:
            new_entry["preview_path"] = None
        materialized_entries.append(new_entry)

    write_jsonl(output_root / "combined_manifest.jsonl", materialized_entries)
    return materialized_entries


def materialize_splits(
    *,
    split_dir: Path,
    materialized_entries: list[dict[str, Any]],
    output_root: Path,
) -> dict[str, int]:
    entries_by_id = {entry["sample_id"]: entry for entry in materialized_entries}
    output_index = output_root / "index"
    output_index.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    for split_name in ("train", "val", "test"):
        source_entries = load_jsonl(split_dir / f"{split_name}.jsonl")
        rewritten = [entries_by_id[entry["sample_id"]] for entry in source_entries if entry["sample_id"] in entries_by_id]
        write_jsonl(output_index / f"{split_name}.jsonl", rewritten)
        counts[split_name] = len(rewritten)

    summary = {
        "counts": counts,
        "manifest_path": str(output_root / "combined_manifest.jsonl"),
    }
    (output_index / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return counts


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize a manifest-based dataset into a self-contained local folder.")
    parser.add_argument("--manifest", type=Path, required=True, help="Source combined manifest JSONL.")
    parser.add_argument("--output", type=Path, required=True, help="Destination root for copied samples and rewritten manifest.")
    parser.add_argument("--split-dir", type=Path, help="Optional split directory with train/val/test JSONL files to rewrite locally.")
    parser.add_argument("--include-preview", action="store_true", help="Copy preview images when present.")
    parser.add_argument("--retries", type=int, default=5, help="Retries per file copy on transient I/O errors.")
    parser.add_argument("--chunk-mb", type=int, default=4, help="Chunk size in MiB for file copies.")
    parser.add_argument("--no-resume", action="store_true", help="Do not reuse already copied files with matching size.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    materialized_entries = materialize_manifest(
        manifest_path=args.manifest,
        output_root=args.output,
        include_preview=args.include_preview,
        retries=args.retries,
        chunk_size_mb=args.chunk_mb,
        skip_existing=not args.no_resume,
    )
    split_counts = None
    if args.split_dir:
        split_counts = materialize_splits(
            split_dir=args.split_dir,
            materialized_entries=materialized_entries,
            output_root=args.output,
        )

    summary = {
        "output_root": str(args.output),
        "source_manifest": str(args.manifest),
        "sample_count": len(materialized_entries),
        "split_counts": split_counts,
        "include_preview": args.include_preview,
    }
    (args.output / "materialize_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
