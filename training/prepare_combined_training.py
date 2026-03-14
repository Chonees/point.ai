from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.create_unified_index import create_unified_index
from training.export_lmdb import export_splits_to_cubi_layout


def prepare_combined_training(
    *,
    manifests: list[Path],
    output_root: Path,
    seed: int,
) -> dict[str, object]:
    index_dir = output_root / "index"
    cubi_dir = output_root / "cubi_layout"

    combined_entries: list[dict[str, object]] = []
    for manifest in manifests:
        import json as _json

        for line in manifest.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entry = _json.loads(line)
                entry["_manifest_path"] = str(manifest)
                combined_entries.append(entry)

    temp_manifest = output_root / "combined_manifest.jsonl"
    temp_manifest.parent.mkdir(parents=True, exist_ok=True)
    temp_manifest.write_text(
        "\n".join(json.dumps(entry) for entry in combined_entries) + ("\n" if combined_entries else ""),
        encoding="utf-8",
    )

    splits = create_unified_index([temp_manifest], index_dir, seed=seed)

    layout = export_splits_to_cubi_layout(
        manifest_path=temp_manifest,
        split_dir=index_dir,
        output_dir=cubi_dir,
        overwrite=True,
    )

    summary = {
        "output_root": str(output_root),
        "manifest_paths": [str(path) for path in manifests],
        "split_counts": {name: len(items) for name, items in splits.items()},
        "cubi_layout": layout,
    }
    (output_root / "prepare_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a combined CubiCasa-compatible training layout from multiple manifests.")
    parser.add_argument("manifests", nargs="+", type=Path, help="Manifest JSONL files to combine.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "training" / "combined_ready",
        help="Root directory for combined splits and LMDB layout.",
    )
    parser.add_argument("--seed", type=int, default=13, help="Split seed.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    summary = prepare_combined_training(
        manifests=args.manifests,
        output_root=args.output,
        seed=args.seed,
    )
    print(f"Prepared combined layout at {args.output} with splits {summary['split_counts']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
