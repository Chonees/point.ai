from __future__ import annotations

import argparse
import json
import tarfile
from collections import Counter
from pathlib import Path
from typing import Any


ANNOTATION_HINTS = (".json", ".xml", ".txt", ".csv", "annotation", "label")
IMAGE_HINTS = (".png", ".jpg", ".jpeg", ".bmp")


def inspect_archive(path: Path, *, scan_limit: int = 5000) -> dict[str, Any]:
    top_level_dirs: Counter[str] = Counter()
    extension_counts: Counter[str] = Counter()
    annotation_like: list[str] = []
    image_like: list[str] = []
    scanned = 0

    with tarfile.open(path, "r:xz") as archive:
        for member in archive:
            scanned += 1
            name = member.name
            parts = [part for part in name.split("/") if part]
            if parts:
                top_level_dirs[parts[0]] += 1

            suffix = Path(name).suffix.lower()
            extension_counts[suffix or "<no_ext>"] += 1

            lowered = name.lower()
            if any(hint in lowered for hint in ANNOTATION_HINTS):
                if len(annotation_like) < 50:
                    annotation_like.append(name)

            if lowered.endswith(IMAGE_HINTS):
                if len(image_like) < 50:
                    image_like.append(name)

            if scanned >= scan_limit:
                break

    return {
        "archive": str(path),
        "members_scanned": scanned,
        "top_level_dirs": dict(top_level_dirs.most_common()),
        "extension_counts": dict(extension_counts.most_common()),
        "annotation_like_members": annotation_like,
        "image_like_members": image_like,
    }


def inspect_dataset_dir(dataset_dir: Path, *, scan_limit: int = 5000) -> dict[str, Any]:
    archives = sorted(dataset_dir.glob("*.tar.xz"))
    results = [inspect_archive(path, scan_limit=scan_limit) for path in archives]
    return {
        "dataset_dir": str(dataset_dir),
        "archive_count": len(archives),
        "archives": results,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect FloorPlanCAD tar archives without extracting the full dataset.")
    parser.add_argument(
        "--input",
        type=Path,
        default=(
            Path(__file__).resolve().parents[1]
            / ".."
            / "floorplan-research"
            / "FloorPlanCAD"
            / "floorplancad-dataset"
        ).resolve(),
        help="Directory containing FloorPlanCAD tar.xz archives.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "training" / "floorplancad_inspection.json",
        help="Where to write the inspection report.",
    )
    parser.add_argument("--scan-limit", type=int, default=5000, help="Maximum members to inspect per archive.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    report = inspect_dataset_dir(args.input, scan_limit=args.scan_limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote FloorPlanCAD inspection report to {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
