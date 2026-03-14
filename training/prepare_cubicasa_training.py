from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.convert_cubicasa import DEFAULT_CUBICASA_DIR, convert_cubicasa_dataset
from training.create_unified_index import create_unified_index
from training.export_lmdb import export_splits_to_cubi_layout


def prepare_cubicasa_training(
    *,
    input_dir: Path,
    output_root: Path,
    limit: int | None,
    preview_limit: int,
    seed: int,
    use_original: bool,
) -> dict[str, object]:
    converted_dir = output_root / "converted"
    index_dir = output_root / "index"
    cubi_dir = output_root / "cubi_layout"

    manifest = convert_cubicasa_dataset(
        input_dir,
        converted_dir,
        limit=limit,
        preview_limit=preview_limit,
        use_original=use_original,
    )
    manifest_path = converted_dir / "cubicasa_manifest.jsonl"
    splits = create_unified_index([manifest_path], index_dir, seed=seed)
    layout = export_splits_to_cubi_layout(
        manifest_path=manifest_path,
        split_dir=index_dir,
        output_dir=cubi_dir,
        overwrite=True,
    )

    summary = {
        "input_dir": str(input_dir),
        "output_root": str(output_root),
        "converted_sample_count": len(manifest),
        "split_counts": {name: len(items) for name, items in splits.items()},
        "use_original": use_original,
        "cubi_layout": layout,
    }
    (output_root / "prepare_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert CubiCasa and prepare a CubiCasa-compatible training layout.")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_CUBICASA_DIR,
        help="Path to the CubiCasa dataset root.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "training" / "cubicasa_ready",
        help="Root directory for converted data, splits, and LMDB layout.",
    )
    parser.add_argument("--limit", type=int, default=100, help="Maximum number of samples. Use 0 for all.")
    parser.add_argument("--preview-limit", type=int, default=20, help="How many preview PNGs to write.")
    parser.add_argument("--seed", type=int, default=13, help="Split seed.")
    parser.add_argument("--use-original", action="store_true", help="Use F1_original.png when available.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    summary = prepare_cubicasa_training(
        input_dir=args.input,
        output_root=args.output,
        limit=None if args.limit == 0 else args.limit,
        preview_limit=args.preview_limit,
        seed=args.seed,
        use_original=args.use_original,
    )
    print(
        f"Prepared {summary['converted_sample_count']} CubiCasa samples in {args.output}. "
        f"Splits: {summary['split_counts']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
