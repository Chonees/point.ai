from __future__ import annotations

import argparse
import json
import tarfile
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image
from skimage.morphology import skeletonize
from svgpathtools import parse_path

from training.common import (
    ICON_LABELS,
    ROOM_LABELS,
    ConvertedSample,
    empty_heatmaps,
    save_converted_sample,
    write_jsonl,
)


DEFAULT_FLOORPLANCAD_DIR = (
    Path(__file__).resolve().parents[1]
    / ".."
    / "floorplan-research"
    / "FloorPlanCAD"
    / "floorplancad-dataset"
).resolve()

SVG_NAMESPACE = "{http://www.w3.org/2000/svg}"
INKSCAPE_NAMESPACE = "{http://www.inkscape.org/namespaces/inkscape}"
WALL_LAYERS = {"WALL", "COLUMN"}
WINDOW_LAYERS = {"WINDOW"}
DOOR_LAYERS = {"DOOR_FIRE", "DOOR", "DOOR_FIRE_TEXT"}
DETAIL_LAYER = "0"
DETAIL_WINDOW_STROKES = {"rgb(178,0,178)"}

ORTHOGONAL_DIRECTIONS = {
    "right": (1, 0),
    "down": (0, 1),
    "left": (-1, 0),
    "up": (0, -1),
}
ENDPOINT_CHANNELS = {"right": 0, "down": 1, "left": 2, "up": 3}
L_CHANNELS = {
    frozenset({"up", "right"}): 4,
    frozenset({"right", "down"}): 5,
    frozenset({"down", "left"}): 6,
    frozenset({"left", "up"}): 7,
}
T_CHANNELS = {"up": 8, "right": 9, "down": 10, "left": 11}
OPPOSITE_DIRECTIONS = {frozenset({"left", "right"}), frozenset({"up", "down"})}


def _root_file_stems(archive: tarfile.TarFile) -> list[str]:
    stems: dict[str, set[str]] = {}
    for member in archive:
        name = member.name
        if "/" in name:
            continue
        path = Path(name)
        if path.suffix.lower() not in {".png", ".svg"}:
            continue
        stems.setdefault(path.stem, set()).add(path.suffix.lower())
    return sorted(stem for stem, suffixes in stems.items() if {".png", ".svg"}.issubset(suffixes))


def _parse_view_box(root: ET.Element, width: int, height: int) -> tuple[float, float, float, float]:
    view_box = root.attrib.get("viewBox")
    if not view_box:
        return 0.0, 0.0, float(width), float(height)
    values = [float(token) for token in view_box.replace(",", " ").split()]
    if len(values) != 4:
        return 0.0, 0.0, float(width), float(height)
    return values[0], values[1], values[2], values[3]


def _sample_path_points(path_data: str) -> np.ndarray:
    path = parse_path(path_data)
    points: list[tuple[float, float]] = []
    for segment in path:
        try:
            seg_length = max(1.0, float(segment.length(error=1e-3)))
        except Exception:
            seg_length = 6.0
        steps = max(8, min(96, int(seg_length * 1.5)))
        for idx in range(steps + 1):
            point = segment.point(idx / steps)
            points.append((point.real, point.imag))
    if not points:
        return np.zeros((0, 2), dtype=np.float32)
    return np.asarray(points, dtype=np.float32)


def _scaled_points(points: np.ndarray, width: int, height: int, view_box: tuple[float, float, float, float]) -> np.ndarray:
    min_x, min_y, vb_width, vb_height = view_box
    scale_x = width / max(vb_width, 1e-6)
    scale_y = height / max(vb_height, 1e-6)
    scaled = points.copy()
    scaled[:, 0] = (scaled[:, 0] - min_x) * scale_x
    scaled[:, 1] = (scaled[:, 1] - min_y) * scale_y
    scaled = np.rint(scaled).astype(np.int32)
    scaled[:, 0] = np.clip(scaled[:, 0], 0, width - 1)
    scaled[:, 1] = np.clip(scaled[:, 1], 0, height - 1)
    return scaled


def _draw_path(mask: np.ndarray, points: np.ndarray, thickness: int) -> None:
    if points.shape[0] < 2:
        return
    cv2.polylines(mask, [points], False, 1, thickness=thickness, lineType=cv2.LINE_AA)


def _draw_circle(mask: np.ndarray, cx: float, cy: float, radius: float, width: int, height: int, view_box: tuple[float, float, float, float], thickness: int) -> None:
    min_x, min_y, vb_width, vb_height = view_box
    scale_x = width / max(vb_width, 1e-6)
    scale_y = height / max(vb_height, 1e-6)
    x = int(round((cx - min_x) * scale_x))
    y = int(round((cy - min_y) * scale_y))
    r = max(1, int(round(radius * (scale_x + scale_y) / 2)))
    cv2.circle(mask, (np.clip(x, 0, width - 1), np.clip(y, 0, height - 1)), r, 1, thickness=thickness, lineType=cv2.LINE_AA)


def _extract_component_points(mask: np.ndarray) -> dict[int, list[tuple[int, int]]]:
    heatmaps = {channel: [] for channel in range(13)}
    if not mask.any():
        return heatmaps

    skeleton = skeletonize(mask > 0)
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
                missing = next(direction for direction in ORTHOGONAL_DIRECTIONS if direction not in neighbors)
                heatmaps[T_CHANNELS[missing]].append((x, y))
                continue
            if degree >= 4:
                heatmaps[12].append((x, y))

    return heatmaps


def _component_bboxes(mask: np.ndarray) -> list[tuple[int, int, int, int]]:
    count, labels, stats, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), connectivity=8)
    boxes: list[tuple[int, int, int, int]] = []
    for label in range(1, count):
        x, y, width, height, area = stats[label]
        if area <= 0:
            continue
        boxes.append((x, y, x + width - 1, y + height - 1))
    return boxes


def _add_opening_heatmaps(heatmaps: dict[int, list[tuple[int, int]]], boxes: list[tuple[int, int, int, int]]) -> None:
    for min_x, min_y, max_x, max_y in boxes:
        left = (min_x, int(round((min_y + max_y) / 2)))
        right = (max_x, int(round((min_y + max_y) / 2)))
        up = (int(round((min_x + max_x) / 2)), min_y)
        down = (int(round((min_x + max_x) / 2)), max_y)
        for channel, point in zip((13, 14, 15, 16), (left, right, up, down)):
            heatmaps[channel].append((int(point[0]), int(point[1])))


def _add_icon_corner_heatmaps(heatmaps: dict[int, list[tuple[int, int]]], boxes: list[tuple[int, int, int, int]]) -> None:
    for min_x, min_y, max_x, max_y in boxes:
        corners = ((min_x, min_y), (max_x, min_y), (min_x, max_y), (max_x, max_y))
        for channel, point in zip((17, 18, 19, 20), corners):
            heatmaps[channel].append((int(point[0]), int(point[1])))


def _interior_mask_from_walls(wall_mask: np.ndarray) -> np.ndarray:
    dilated = cv2.dilate((wall_mask > 0).astype(np.uint8), np.ones((3, 3), dtype=np.uint8), iterations=1)
    free = (dilated == 0).astype(np.uint8)
    count, labels = cv2.connectedComponents(free, connectivity=4)
    if count <= 1:
        return np.zeros_like(free)

    outside_labels = set(labels[0, :]) | set(labels[-1, :]) | set(labels[:, 0]) | set(labels[:, -1])
    outside_labels.discard(0)
    interior = np.zeros_like(free)
    for label in range(1, count):
        if label in outside_labels:
            continue
        interior[labels == label] = 1
    return interior


def _door_like_in_detail_layer(element: ET.Element) -> bool:
    if element.tag.split("}", 1)[-1] != "path":
        return False
    path_data = element.attrib.get("d", "")
    stroke = element.attrib.get("stroke")
    return "A " in path_data and stroke == "rgb(63,63,63)"


def _window_like_in_detail_layer(element: ET.Element) -> bool:
    if element.tag.split("}", 1)[-1] != "path":
        return False
    stroke = element.attrib.get("stroke")
    semantic_id = element.attrib.get("semantic-id")
    return semantic_id == "33" or stroke in DETAIL_WINDOW_STROKES


def convert_floorplancad_sample(
    *,
    image_rgb: np.ndarray,
    svg_text: str,
    sample_stem: str,
    archive_name: str,
) -> ConvertedSample:
    root = ET.fromstring(svg_text)
    height, width = image_rgb.shape[:2]
    view_box = _parse_view_box(root, width, height)

    wall_mask = np.zeros((height, width), dtype=np.uint8)
    window_mask = np.zeros((height, width), dtype=np.uint8)
    door_mask = np.zeros((height, width), dtype=np.uint8)

    layer_stats: dict[str, int] = {}

    for layer in root.findall(f"{SVG_NAMESPACE}g"):
        label = layer.attrib.get(f"{INKSCAPE_NAMESPACE}label", "").upper()
        for element in list(layer):
            tag = element.tag.split("}", 1)[-1]
            if tag == "path":
                path_data = element.attrib.get("d")
                if not path_data:
                    continue
                points = _scaled_points(_sample_path_points(path_data), width, height, view_box)
            elif tag == "circle":
                points = np.zeros((0, 2), dtype=np.int32)
            else:
                continue

            target_mask: np.ndarray | None = None
            thickness = 2
            if label in WALL_LAYERS:
                target_mask = wall_mask
                thickness = 4
            elif label in WINDOW_LAYERS or (label == DETAIL_LAYER and _window_like_in_detail_layer(element)):
                target_mask = window_mask
                thickness = 3
            elif label in DOOR_LAYERS or (label == DETAIL_LAYER and _door_like_in_detail_layer(element)):
                target_mask = door_mask
                thickness = 3

            if target_mask is None:
                continue

            layer_stats[label] = layer_stats.get(label, 0) + 1
            if tag == "path":
                _draw_path(target_mask, points, thickness=thickness)
            elif tag == "circle":
                _draw_circle(
                    target_mask,
                    float(element.attrib.get("cx", 0.0)),
                    float(element.attrib.get("cy", 0.0)),
                    float(element.attrib.get("r", 0.0)),
                    width,
                    height,
                    view_box,
                    thickness=thickness,
                )

    wall_mask = cv2.dilate(wall_mask, np.ones((3, 3), dtype=np.uint8), iterations=1)
    window_mask = cv2.dilate(window_mask, np.ones((3, 3), dtype=np.uint8), iterations=1)
    door_mask = cv2.dilate(door_mask, np.ones((3, 3), dtype=np.uint8), iterations=1)

    room_mask = np.zeros((height, width), dtype=np.uint8)
    room_mask[_interior_mask_from_walls(wall_mask) > 0] = ROOM_LABELS["room"]
    room_mask[wall_mask > 0] = ROOM_LABELS["wall"]

    icon_mask = np.zeros((height, width), dtype=np.uint8)
    icon_mask[window_mask > 0] = ICON_LABELS["window"]
    icon_mask[door_mask > 0] = ICON_LABELS["door"]

    heatmaps = empty_heatmaps()
    for channel, coords in _extract_component_points(wall_mask).items():
        heatmaps[channel] = coords

    opening_boxes = _component_bboxes((window_mask > 0).astype(np.uint8) | (door_mask > 0).astype(np.uint8))
    _add_opening_heatmaps(heatmaps, opening_boxes)
    _add_icon_corner_heatmaps(heatmaps, opening_boxes)

    label = np.stack([room_mask, icon_mask], axis=0)
    sample_id = f"floorplancad-{archive_name.replace('.tar.xz', '')}-{sample_stem}"
    meta = {
        "dataset": "floorplancad",
        "source_id": sample_stem,
        "archive": archive_name,
        "view_box": list(view_box),
        "image_shape": [int(height), int(width)],
        "active_layers": layer_stats,
        "room_labels_present": sorted(int(value) for value in np.unique(room_mask)),
        "icon_labels_present": sorted(int(value) for value in np.unique(icon_mask)),
        "heatmap_counts": {str(channel): len(coords) for channel, coords in heatmaps.items()},
    }

    return ConvertedSample(
        dataset="floorplancad",
        sample_id=sample_id,
        source_id=sample_stem,
        image=np.moveaxis(image_rgb, -1, 0).astype(np.uint8),
        label=label.astype(np.uint8),
        heatmaps=heatmaps,
        scale=1.0,
        meta=meta,
    )


def _load_png_from_tar(archive: tarfile.TarFile, member_name: str) -> np.ndarray:
    raw = archive.extractfile(member_name)
    if raw is None:
        raise FileNotFoundError(member_name)
    image = Image.open(BytesIO(raw.read())).convert("RGB")
    return np.asarray(image, dtype=np.uint8)


def _load_text_from_tar(archive: tarfile.TarFile, member_name: str) -> str:
    raw = archive.extractfile(member_name)
    if raw is None:
        raise FileNotFoundError(member_name)
    return raw.read().decode("utf-8", errors="ignore")


def convert_floorplancad_dataset(
    input_dir: Path,
    output_dir: Path,
    *,
    limit: int | None = None,
    preview_limit: int = 20,
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    converted = 0

    for archive_path in sorted(input_dir.glob("*.tar.xz")):
        with tarfile.open(archive_path, "r:xz") as archive:
            stems = _root_file_stems(archive)
            for stem in stems:
                if limit is not None and converted >= limit:
                    break
                png_name = f"{stem}.png"
                svg_name = f"{stem}.svg"
                sample = convert_floorplancad_sample(
                    image_rgb=_load_png_from_tar(archive, png_name),
                    svg_text=_load_text_from_tar(archive, svg_name),
                    sample_stem=stem,
                    archive_name=archive_path.name,
                )
                entry = save_converted_sample(
                    sample,
                    output_dir,
                    write_preview=converted < preview_limit,
                )
                manifest.append(entry)
                converted += 1
        if limit is not None and converted >= limit:
            break

    manifest_path = output_dir / "floorplancad_manifest.jsonl"
    write_jsonl(manifest_path, manifest)
    summary = {
        "dataset": "floorplancad",
        "sample_count": len(manifest),
        "manifest_path": str(manifest_path),
        "preview_limit": preview_limit,
    }
    (output_dir / "floorplancad_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return manifest


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert FloorPlanCAD into Point.ai training samples.")
    parser.add_argument("--input", type=Path, default=DEFAULT_FLOORPLANCAD_DIR, help="Directory containing FloorPlanCAD tar.xz archives.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "training" / "floorplancad_pilot",
        help="Output directory for converted samples.",
    )
    parser.add_argument("--limit", type=int, default=50, help="Maximum number of samples to convert. Use 0 for all.")
    parser.add_argument("--preview-limit", type=int, default=20, help="How many preview PNGs to write.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    manifest = convert_floorplancad_dataset(
        args.input,
        args.output,
        limit=None if args.limit == 0 else args.limit,
        preview_limit=args.preview_limit,
    )
    print(f"Converted {len(manifest)} FloorPlanCAD sample(s) into {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
