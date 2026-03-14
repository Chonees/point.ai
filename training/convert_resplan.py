from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry import MultiPolygon, Polygon
from skimage.morphology import skeletonize

from training.common import (
    DEFAULT_IMAGE_SIZE,
    DEFAULT_PADDING,
    ICON_LABELS,
    ICON_RENDER_COLORS,
    ROOM_LABELS,
    ROOM_RENDER_COLORS,
    ConvertedSample,
    draw_geometry,
    empty_heatmaps,
    normalize_geometry_dict,
    save_converted_sample,
    write_jsonl,
)

DEFAULT_RESPLAN_PATH = (
    Path(__file__).resolve().parents[1]
    / ".."
    / "floorplan-research"
    / "ResPlan"
    / "ResPlan.pkl"
).resolve()

RESPLAN_ROOM_MAPPING = {
    "living": ROOM_LABELS["living"],
    "bedroom": ROOM_LABELS["bedroom"],
    "bathroom": ROOM_LABELS["bath"],
    "kitchen": ROOM_LABELS["kitchen"],
    "storage": ROOM_LABELS["storage"],
    "stair": ROOM_LABELS["room"],
}

RESPLAN_OUTDOOR_KEYS = ("balcony", "veranda", "garden", "land", "parking", "pool")
RESPLAN_ICON_MAPPING = {
    "window": ICON_LABELS["window"],
    "door": ICON_LABELS["door"],
    "front_door": ICON_LABELS["door"],
}

ORTHOGONAL_DIRECTIONS = {
    "right": (1, 0),
    "down": (0, 1),
    "left": (-1, 0),
    "up": (0, -1),
}
ENDPOINT_CHANNELS = {
    "right": 0,
    "down": 1,
    "left": 2,
    "up": 3,
}
L_CHANNELS = {
    frozenset({"up", "right"}): 4,
    frozenset({"right", "down"}): 5,
    frozenset({"down", "left"}): 6,
    frozenset({"left", "up"}): 7,
}
T_CHANNELS = {
    "up": 8,
    "right": 9,
    "down": 10,
    "left": 11,
}
OPPOSITE_DIRECTIONS = {
    frozenset({"left", "right"}),
    frozenset({"up", "down"}),
}


def load_resplan(path: Path = DEFAULT_RESPLAN_PATH) -> list[dict[str, Any]]:
    with path.open("rb") as handle:
        data = pickle.load(handle)
    if not isinstance(data, list):
        raise TypeError("Expected ResPlan pickle to contain a list of plans.")
    return data


def _plan_geometries(plan: dict[str, Any]) -> dict[str, Any]:
    keys = set(RESPLAN_ROOM_MAPPING) | set(RESPLAN_OUTDOOR_KEYS) | set(RESPLAN_ICON_MAPPING) | {"wall", "inner"}
    return {key: plan.get(key) for key in keys}


def _count_non_empty(geometry: Any) -> int:
    if geometry is None or getattr(geometry, "is_empty", True):
        return 0
    if isinstance(geometry, Polygon):
        return 1
    if isinstance(geometry, MultiPolygon):
        return sum(1 for geom in geometry.geoms if not geom.is_empty)
    if hasattr(geometry, "geoms"):
        return sum(1 for geom in geometry.geoms if not geom.is_empty)
    return 1


def _add_bbox_opening_points(geometry: Any, heatmaps: dict[int, list[tuple[int, int]]], image_size: int) -> None:
    if geometry is None or getattr(geometry, "is_empty", True):
        return
    geometries = geometry.geoms if hasattr(geometry, "geoms") else [geometry]
    for item in geometries:
        if item.is_empty:
            continue
        min_x, min_y, max_x, max_y = item.bounds
        left = (int(round(min_x)), int(round((min_y + max_y) / 2)))
        right = (int(round(max_x)), int(round((min_y + max_y) / 2)))
        up = (int(round((min_x + max_x) / 2)), int(round(min_y)))
        down = (int(round((min_x + max_x) / 2)), int(round(max_y)))
        for channel, point in zip((13, 14, 15, 16), (left, right, up, down)):
            x = int(np.clip(point[0], 0, image_size - 1))
            y = int(np.clip(point[1], 0, image_size - 1))
            heatmaps[channel].append((x, y))


def _extract_wall_heatmaps(wall_mask: np.ndarray) -> dict[int, list[tuple[int, int]]]:
    heatmaps = {channel: [] for channel in range(13)}
    if not wall_mask.any():
        return heatmaps

    skeleton = skeletonize(wall_mask > 0)
    height, width = skeleton.shape

    for y in range(1, height - 1):
        for x in range(1, width - 1):
            if not skeleton[y, x]:
                continue

            neighbors: list[str] = []
            for direction, (dx, dy) in ORTHOGONAL_DIRECTIONS.items():
                if skeleton[y + dy, x + dx]:
                    neighbors.append(direction)

            degree = len(neighbors)
            if degree == 1:
                heatmaps[ENDPOINT_CHANNELS[neighbors[0]]].append((x, y))
                continue

            if degree == 2:
                directions = frozenset(neighbors)
                if directions in OPPOSITE_DIRECTIONS:
                    continue
                channel = L_CHANNELS.get(directions)
                if channel is not None:
                    heatmaps[channel].append((x, y))
                continue

            if degree == 3:
                missing = next(
                    direction
                    for direction in ORTHOGONAL_DIRECTIONS
                    if direction not in neighbors
                )
                heatmaps[T_CHANNELS[missing]].append((x, y))
                continue

            if degree >= 4:
                heatmaps[12].append((x, y))

    return heatmaps


def convert_resplan_plan(
    plan: dict[str, Any],
    *,
    image_size: int = DEFAULT_IMAGE_SIZE,
    padding: int = DEFAULT_PADDING,
) -> ConvertedSample:
    normalized_geometries, transform_meta = normalize_geometry_dict(
        _plan_geometries(plan),
        image_size=image_size,
        padding=padding,
    )

    room_mask = np.zeros((image_size, image_size), dtype=np.uint8)
    icon_mask = np.zeros((image_size, image_size), dtype=np.uint8)
    image = np.full((image_size, image_size, 3), 255, dtype=np.uint8)

    draw_geometry(room_mask, normalized_geometries.get("inner"), ROOM_LABELS["room"])
    draw_geometry(
        image,
        normalized_geometries.get("inner"),
        ROOM_RENDER_COLORS[ROOM_LABELS["room"]],
        clear_value=ROOM_RENDER_COLORS[ROOM_LABELS["background"]],
    )

    for key in RESPLAN_OUTDOOR_KEYS:
        geometry = normalized_geometries.get(key)
        draw_geometry(room_mask, geometry, ROOM_LABELS["outdoor"])
        draw_geometry(
            image,
            geometry,
            ROOM_RENDER_COLORS[ROOM_LABELS["outdoor"]],
            clear_value=ROOM_RENDER_COLORS[ROOM_LABELS["background"]],
        )

    for key, label in RESPLAN_ROOM_MAPPING.items():
        geometry = normalized_geometries.get(key)
        draw_geometry(room_mask, geometry, label)
        draw_geometry(
            image,
            geometry,
            ROOM_RENDER_COLORS[label],
            clear_value=ROOM_RENDER_COLORS[ROOM_LABELS["background"]],
        )

    wall_geometry = normalized_geometries.get("wall")
    wall_mask = np.zeros((image_size, image_size), dtype=np.uint8)
    draw_geometry(wall_mask, wall_geometry, 1)
    room_mask[wall_mask > 0] = ROOM_LABELS["wall"]
    image[wall_mask > 0] = ROOM_RENDER_COLORS[ROOM_LABELS["wall"]]

    for key, label in RESPLAN_ICON_MAPPING.items():
        geometry = normalized_geometries.get(key)
        draw_geometry(icon_mask, geometry, label)
        draw_geometry(
            image,
            geometry,
            ICON_RENDER_COLORS[label],
            clear_value=ROOM_RENDER_COLORS[ROOM_LABELS["background"]],
        )

    heatmaps = empty_heatmaps()
    for channel, coords in _extract_wall_heatmaps(wall_mask > 0).items():
        heatmaps[channel] = coords

    for key in RESPLAN_ICON_MAPPING:
        _add_bbox_opening_points(normalized_geometries.get(key), heatmaps, image_size)

    label = np.stack([room_mask, icon_mask], axis=0)
    sample_id = f"resplan-{int(plan.get('id', 0)):05d}"
    source_id = str(plan.get("id", sample_id))
    meta = {
        "dataset": "resplan",
        "source_id": source_id,
        "unit_type": plan.get("unitType"),
        "wall_depth": float(plan.get("wall_depth", 0.0) or 0.0),
        "net_area": float(plan.get("net_area", 0.0) or 0.0),
        "area": float(plan.get("area", 0.0) or 0.0),
        "transform": transform_meta,
        "counts": {
            "wall_polygons": _count_non_empty(plan.get("wall")),
            "door_polygons": _count_non_empty(plan.get("door")) + _count_non_empty(plan.get("front_door")),
            "window_polygons": _count_non_empty(plan.get("window")),
        },
        "room_labels_present": sorted(int(value) for value in np.unique(room_mask)),
        "icon_labels_present": sorted(int(value) for value in np.unique(icon_mask)),
        "heatmap_counts": {str(channel): len(coords) for channel, coords in heatmaps.items()},
    }
    image_chw = np.moveaxis(image, -1, 0)

    return ConvertedSample(
        dataset="resplan",
        sample_id=sample_id,
        source_id=source_id,
        image=image_chw,
        label=label,
        heatmaps=heatmaps,
        scale=float(transform_meta["normalized_scale"]),
        meta=meta,
    )


def convert_resplan_dataset(
    plans: list[dict[str, Any]],
    output_dir: Path,
    *,
    limit: int | None = None,
    image_size: int = DEFAULT_IMAGE_SIZE,
    padding: int = DEFAULT_PADDING,
    preview_limit: int = 20,
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = plans[:limit] if limit is not None else plans
    manifest: list[dict[str, Any]] = []

    for index, plan in enumerate(selected):
        sample = convert_resplan_plan(plan, image_size=image_size, padding=padding)
        entry = save_converted_sample(
            sample,
            output_dir,
            write_preview=index < preview_limit,
        )
        manifest.append(entry)

    manifest_path = output_dir / "resplan_manifest.jsonl"
    write_jsonl(manifest_path, manifest)

    summary = {
        "dataset": "resplan",
        "sample_count": len(manifest),
        "manifest_path": str(manifest_path),
        "image_size": image_size,
        "preview_limit": preview_limit,
    }
    (output_dir / "resplan_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    return manifest


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert ResPlan to Point.ai training samples.")
    parser.add_argument("--input", type=Path, default=DEFAULT_RESPLAN_PATH, help="Path to ResPlan.pkl")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "training" / "resplan_pilot",
        help="Output directory for converted samples.",
    )
    parser.add_argument("--limit", type=int, default=100, help="Maximum number of plans to convert.")
    parser.add_argument("--image-size", type=int, default=DEFAULT_IMAGE_SIZE, help="Output raster size.")
    parser.add_argument("--padding", type=int, default=DEFAULT_PADDING, help="Padding added during normalization.")
    parser.add_argument(
        "--preview-limit",
        type=int,
        default=20,
        help="How many samples should include preview images.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    plans = load_resplan(args.input)
    manifest = convert_resplan_dataset(
        plans,
        args.output,
        limit=args.limit,
        image_size=args.image_size,
        padding=args.padding,
        preview_limit=args.preview_limit,
    )
    print(f"Converted {len(manifest)} ResPlan sample(s) into {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
