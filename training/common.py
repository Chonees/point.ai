from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from shapely import affinity
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon

DEFAULT_IMAGE_SIZE = 256
DEFAULT_PADDING = 8

ROOM_LABELS = {
    "background": 0,
    "outdoor": 1,
    "wall": 2,
    "kitchen": 3,
    "living": 4,
    "bedroom": 5,
    "bath": 6,
    "entry": 7,
    "railing": 8,
    "storage": 9,
    "garage": 10,
    "room": 11,
}

ICON_LABELS = {
    "background": 0,
    "window": 1,
    "door": 2,
    "closet": 3,
    "appliance": 4,
    "toilet": 5,
    "sink": 6,
    "sauna": 7,
    "fireplace": 8,
    "bathtub": 9,
    "chimney": 10,
}

ROOM_RENDER_COLORS = {
    ROOM_LABELS["background"]: (255, 255, 255),
    ROOM_LABELS["outdoor"]: (244, 249, 239),
    ROOM_LABELS["wall"]: (32, 37, 45),
    ROOM_LABELS["kitchen"]: (241, 231, 214),
    ROOM_LABELS["living"]: (250, 241, 221),
    ROOM_LABELS["bedroom"]: (233, 242, 255),
    ROOM_LABELS["bath"]: (226, 241, 245),
    ROOM_LABELS["entry"]: (240, 240, 240),
    ROOM_LABELS["railing"]: (226, 226, 226),
    ROOM_LABELS["storage"]: (237, 230, 239),
    ROOM_LABELS["garage"]: (231, 233, 236),
    ROOM_LABELS["room"]: (248, 248, 248),
}

ICON_RENDER_COLORS = {
    ICON_LABELS["window"]: (69, 142, 255),
    ICON_LABELS["door"]: (214, 116, 47),
    ICON_LABELS["closet"]: (158, 101, 186),
    ICON_LABELS["appliance"]: (90, 90, 90),
    ICON_LABELS["toilet"]: (72, 175, 220),
    ICON_LABELS["sink"]: (92, 155, 232),
    ICON_LABELS["sauna"]: (160, 124, 82),
    ICON_LABELS["fireplace"]: (190, 89, 63),
    ICON_LABELS["bathtub"]: (78, 160, 208),
    ICON_LABELS["chimney"]: (130, 130, 130),
}


@dataclass(slots=True)
class ConvertedSample:
    dataset: str
    sample_id: str
    source_id: str
    image: np.ndarray
    label: np.ndarray
    heatmaps: dict[int, list[tuple[int, int]]]
    scale: float
    meta: dict[str, Any]


def empty_heatmaps() -> dict[int, list[tuple[int, int]]]:
    return {channel: [] for channel in range(21)}


def iter_polygons(geometry: Any):
    if geometry is None:
        return
    if hasattr(geometry, "is_empty") and geometry.is_empty:
        return
    if isinstance(geometry, Polygon):
        yield geometry
        return
    if isinstance(geometry, MultiPolygon):
        for polygon in geometry.geoms:
            if not polygon.is_empty:
                yield polygon
        return
    if isinstance(geometry, GeometryCollection):
        for item in geometry.geoms:
            yield from iter_polygons(item)
        return
    if hasattr(geometry, "geom_type") and geometry.geom_type in {"LineString", "LinearRing"}:
        buffered = geometry.buffer(1.0, cap_style=2, join_style=2)
        yield from iter_polygons(buffered)
        return
    if hasattr(geometry, "geom_type") and geometry.geom_type == "MultiLineString":
        for item in geometry.geoms:
            yield from iter_polygons(item)


def _collect_bounds(geometries: dict[str, Any]) -> tuple[float, float, float, float]:
    bounds: list[tuple[float, float, float, float]] = []
    for geometry in geometries.values():
        if geometry is None or getattr(geometry, "is_empty", True):
            continue
        bounds.append(geometry.bounds)
    if not bounds:
        raise ValueError("No non-empty geometries were provided.")

    min_x = min(bound[0] for bound in bounds)
    min_y = min(bound[1] for bound in bounds)
    max_x = max(bound[2] for bound in bounds)
    max_y = max(bound[3] for bound in bounds)
    return min_x, min_y, max_x, max_y


def normalize_geometry_dict(
    geometries: dict[str, Any],
    image_size: int = DEFAULT_IMAGE_SIZE,
    padding: int = DEFAULT_PADDING,
) -> tuple[dict[str, Any], dict[str, float]]:
    min_x, min_y, max_x, max_y = _collect_bounds(geometries)
    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    available = max(image_size - 2 * padding, 1)
    scale = min(available / width, available / height)
    x_offset = padding - min_x * scale
    y_offset = padding - min_y * scale

    normalized: dict[str, Any] = {}
    for key, geometry in geometries.items():
        if geometry is None or getattr(geometry, "is_empty", True):
            normalized[key] = geometry
            continue
        scaled = affinity.scale(geometry, xfact=scale, yfact=scale, origin=(0, 0))
        translated = affinity.translate(scaled, xoff=x_offset, yoff=y_offset)
        normalized[key] = translated

    meta = {
        "source_bounds": [min_x, min_y, max_x, max_y],
        "normalized_scale": scale,
        "normalized_x_offset": x_offset,
        "normalized_y_offset": y_offset,
    }
    return normalized, meta


def draw_geometry(mask: np.ndarray, geometry: Any, value: Any, clear_value: Any = 0) -> None:
    if geometry is None or getattr(geometry, "is_empty", True):
        return

    if mask.ndim == 2:
        fill_value = int(value)
        hole_value = int(clear_value)
    else:
        fill_value = tuple(int(v) for v in value)
        hole_value = tuple(int(v) for v in clear_value)

    height, width = mask.shape[:2]
    for polygon in iter_polygons(geometry):
        exterior = np.rint(np.asarray(polygon.exterior.coords)).astype(np.int32)
        if exterior.shape[0] < 3:
            continue
        exterior[:, 0] = np.clip(exterior[:, 0], 0, width - 1)
        exterior[:, 1] = np.clip(exterior[:, 1], 0, height - 1)
        cv2.fillPoly(mask, [exterior], fill_value)

        for interior in polygon.interiors:
            hole = np.rint(np.asarray(interior.coords)).astype(np.int32)
            if hole.shape[0] < 3:
                continue
            hole[:, 0] = np.clip(hole[:, 0], 0, width - 1)
            hole[:, 1] = np.clip(hole[:, 1], 0, height - 1)
            cv2.fillPoly(mask, [hole], hole_value)


def build_preview(sample: ConvertedSample) -> np.ndarray:
    preview = np.moveaxis(sample.image, 0, -1).copy()
    heatmap_colors = [
        (228, 87, 46),
        (66, 133, 244),
        (52, 168, 83),
        (251, 188, 5),
    ]
    for channel, coords in sample.heatmaps.items():
        color = heatmap_colors[channel % len(heatmap_colors)]
        for x, y in coords[:80]:
            cv2.circle(preview, (int(x), int(y)), 1, color, -1)
    return preview


def save_converted_sample(
    sample: ConvertedSample,
    output_root: Path,
    *,
    write_preview: bool = True,
) -> dict[str, Any]:
    sample_dir = output_root / sample.dataset / sample.sample_id
    sample_dir.mkdir(parents=True, exist_ok=True)

    image_path = sample_dir / "image.png"
    label_path = sample_dir / "label.npy"
    heatmaps_path = sample_dir / "heatmaps.json"
    meta_path = sample_dir / "meta.json"
    preview_path = sample_dir / "preview.png"

    image_hwc = np.moveaxis(sample.image, 0, -1)
    # Convert float32 [0,1] to uint8 [0,255] for cv2.imwrite
    if image_hwc.dtype == np.float32 or image_hwc.dtype == np.float64:
        image_hwc = (image_hwc * 255).clip(0, 255).astype(np.uint8)
    cv2.imwrite(str(image_path), cv2.cvtColor(image_hwc, cv2.COLOR_RGB2BGR))
    np.save(label_path, sample.label)
    heatmaps_payload = {str(channel): coords for channel, coords in sample.heatmaps.items()}
    heatmaps_path.write_text(json.dumps(heatmaps_payload, indent=2), encoding="utf-8")
    meta_path.write_text(json.dumps(sample.meta, indent=2), encoding="utf-8")

    if write_preview:
        preview = build_preview(sample)
        cv2.imwrite(str(preview_path), cv2.cvtColor(preview, cv2.COLOR_RGB2BGR))

    return {
        "dataset": sample.dataset,
        "sample_id": sample.sample_id,
        "source_id": sample.source_id,
        "image_path": str(image_path.relative_to(output_root)),
        "label_path": str(label_path.relative_to(output_root)),
        "heatmaps_path": str(heatmaps_path.relative_to(output_root)),
        "meta_path": str(meta_path.relative_to(output_root)),
        "preview_path": str(preview_path.relative_to(output_root)) if write_preview else None,
        "scale": sample.scale,
        "image_shape": list(sample.image.shape),
        "label_shape": list(sample.label.shape),
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(record, sort_keys=True) for record in records)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")
