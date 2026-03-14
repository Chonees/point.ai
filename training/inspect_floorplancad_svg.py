from __future__ import annotations

import argparse
import json
import tarfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any


SVG_NS = {"svg": "http://www.w3.org/2000/svg", "inkscape": "http://www.inkscape.org/namespaces/inkscape"}


def extract_svg_semantics(svg_text: str) -> dict[str, Any]:
    root = ET.fromstring(svg_text)
    layers: Counter[str] = Counter()
    semantic_ids: Counter[str] = Counter()
    stroke_colors: Counter[str] = Counter()
    element_tags: Counter[str] = Counter()

    for element in root.iter():
        tag = element.tag.split("}", 1)[-1]
        element_tags[tag] += 1

        semantic_id = element.attrib.get("semantic-id")
        if semantic_id:
            semantic_ids[semantic_id] += 1

        stroke = element.attrib.get("stroke")
        if stroke:
            stroke_colors[stroke] += 1

        label = element.attrib.get(f"{{{SVG_NS['inkscape']}}}label")
        if label:
            layers[label] += 1

    return {
        "view_box": root.attrib.get("viewBox"),
        "layers": dict(layers.most_common()),
        "semantic_ids": dict(semantic_ids.most_common()),
        "stroke_colors": dict(stroke_colors.most_common()),
        "element_tags": dict(element_tags.most_common()),
    }


def inspect_floorplancad_svgs(
    dataset_dir: Path,
    *,
    sample_limit_per_archive: int = 10,
) -> dict[str, Any]:
    archives = sorted(dataset_dir.glob("*.tar.xz"))
    archive_reports: list[dict[str, Any]] = []

    for archive_path in archives:
        layer_totals: Counter[str] = Counter()
        semantic_totals: Counter[str] = Counter()
        color_totals: Counter[str] = Counter()
        tag_totals: Counter[str] = Counter()
        sampled_files: list[dict[str, Any]] = []
        sampled = 0

        with tarfile.open(archive_path, "r:xz") as archive:
            for member in archive:
                if sampled >= sample_limit_per_archive:
                    break
                if not member.name.endswith(".svg") or "/" in member.name:
                    continue
                raw = archive.extractfile(member)
                if raw is None:
                    continue
                semantics = extract_svg_semantics(raw.read().decode("utf-8", errors="ignore"))
                sampled_files.append({"name": member.name, **semantics})
                layer_totals.update(semantics["layers"])
                semantic_totals.update(semantics["semantic_ids"])
                color_totals.update(semantics["stroke_colors"])
                tag_totals.update(semantics["element_tags"])
                sampled += 1

        archive_reports.append(
            {
                "archive": str(archive_path),
                "sampled_svg_count": sampled,
                "layer_totals": dict(layer_totals.most_common()),
                "semantic_id_totals": dict(semantic_totals.most_common()),
                "stroke_color_totals": dict(color_totals.most_common()),
                "element_tag_totals": dict(tag_totals.most_common()),
                "sampled_files": sampled_files,
            }
        )

    return {
        "dataset_dir": str(dataset_dir),
        "archive_count": len(archives),
        "sample_limit_per_archive": sample_limit_per_archive,
        "archives": archive_reports,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect FloorPlanCAD SVG semantics across sampled archive members.")
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
        default=Path("data") / "training" / "floorplancad_svg_report.json",
        help="Where to write the SVG report.",
    )
    parser.add_argument("--sample-limit", type=int, default=10, help="How many root-level SVGs to inspect per archive.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    report = inspect_floorplancad_svgs(args.input, sample_limit_per_archive=args.sample_limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote FloorPlanCAD SVG report to {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
