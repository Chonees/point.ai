from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from training.common import load_jsonl, write_jsonl
from training.create_unified_index import create_unified_index
from training.dataset_audit import audit_manifest
from training.export_lmdb import export_splits_to_cubi_layout


def _load_audit_map(report_path: Path) -> dict[str, dict[str, Any]]:
    return {row["sample_id"]: row for row in load_jsonl(report_path)}


def _should_drop(record: dict[str, Any], *, min_score: int, require_openings: bool) -> bool:
    critical_flags = {"no_walls", "no_rooms", "wall_ratio_too_low", "wall_ratio_too_high", "tiny_image"}
    if any(flag in critical_flags for flag in record["flags"]):
        return True
    if require_openings and "no_openings" in record["flags"]:
        return True
    return int(record["quality_score"]) < min_score


def prepare_curated_training(
    *,
    manifests: list[Path],
    output_root: Path,
    seed: int,
    min_score: int = 35,
    require_openings: bool = False,
    map_size_bytes: int | None = None,
    export_layout: bool = True,
) -> dict[str, Any]:
    audit_dir = output_root / "audits"
    combined_entries: list[dict[str, Any]] = []
    kept_counts: dict[str, int] = {}
    dropped_counts: dict[str, int] = {}
    audit_summaries: list[dict[str, Any]] = []

    for manifest in manifests:
        _, audit_summary = audit_manifest(manifest, audit_dir)
        audit_summaries.append(audit_summary)
        stem = manifest.stem.replace("_manifest", "")
        audit_map = _load_audit_map(audit_dir / f"{stem}_audit.jsonl")

        for entry in load_jsonl(manifest):
            record = audit_map.get(entry["sample_id"])
            if record is None:
                continue
            dataset = entry["dataset"]
            if _should_drop(record, min_score=min_score, require_openings=require_openings):
                dropped_counts[dataset] = dropped_counts.get(dataset, 0) + 1
                continue

            enriched = dict(entry)
            enriched["_manifest_path"] = str(manifest)
            enriched["quality_score"] = record["quality_score"]
            enriched["quality_flags"] = record["flags"]
            combined_entries.append(enriched)
            kept_counts[dataset] = kept_counts.get(dataset, 0) + 1

    temp_manifest = output_root / "combined_manifest.jsonl"
    write_jsonl(temp_manifest, combined_entries)

    index_dir = output_root / "index"
    splits = create_unified_index([temp_manifest], index_dir, seed=seed)
    layout: dict[str, Any] | None = None
    if export_layout:
        cubi_dir = output_root / "cubi_layout"
        layout = export_splits_to_cubi_layout(
            manifest_path=temp_manifest,
            split_dir=index_dir,
            output_dir=cubi_dir,
            overwrite=True,
            map_size_bytes=map_size_bytes,
        )

    summary = {
        "output_root": str(output_root),
        "manifest_paths": [str(path) for path in manifests],
        "min_score": min_score,
        "require_openings": require_openings,
        "export_layout": export_layout,
        "kept_counts": kept_counts,
        "dropped_counts": dropped_counts,
        "total_kept": len(combined_entries),
        "split_counts": {name: len(items) for name, items in splits.items()},
        "audit_summaries": audit_summaries,
        "cubi_layout": layout,
    }
    (output_root / "prepare_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a curated combined dataset from audited manifests.")
    parser.add_argument("manifests", nargs="+", type=Path, help="Manifest JSONL files to combine and curate.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "training" / "combined_curated",
        help="Output directory for curated manifest, audits, splits and LMDB layout.",
    )
    parser.add_argument("--seed", type=int, default=13, help="Split seed.")
    parser.add_argument("--min-score", type=int, default=35, help="Minimum audit quality score to keep a sample.")
    parser.add_argument("--require-openings", action="store_true", help="Drop samples without doors/windows.")
    parser.add_argument(
        "--map-size-gb",
        type=float,
        default=0.0,
        help="Optional LMDB map size in GiB. Use 0 to auto-estimate.",
    )
    parser.add_argument(
        "--skip-layout",
        action="store_true",
        help="Build curated manifest and splits only, without exporting a combined LMDB layout.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    summary = prepare_curated_training(
        manifests=args.manifests,
        output_root=args.output,
        seed=args.seed,
        min_score=args.min_score,
        require_openings=args.require_openings,
        map_size_bytes=int(args.map_size_gb * (1 << 30)) if args.map_size_gb > 0 else None,
        export_layout=not args.skip_layout,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
