from __future__ import annotations

import math
import uuid
from typing import Any

import cv2
import numpy as np
from skimage.morphology import medial_axis

from ..geometry_utils import is_diagonal, snap_endpoint_clusters

_NEIGHBOR_OFFSETS = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)


def build_mask_native_wall_annotations(
    wall_mask: np.ndarray,
    *,
    min_segment_length: float = 4.0,
    endpoint_tolerance: float = 2.5,
) -> list[dict[str, Any]]:
    """Extract image-space wall annotations directly from a wall mask.

    This is the first slice of the mask-native inverse-CAD pipeline:
    - preserve centerline topology via medial axis
    - keep short branches / diagonals instead of collapsing to rectangles
    - estimate local wall width from distance transform
    - snap widths to 4"/6" classes for the DXF writer contract
    """
    binary = (wall_mask > 0).astype(np.uint8)
    if binary.size == 0 or np.count_nonzero(binary) == 0:
        return []

    skeleton, distance = medial_axis(binary.astype(bool), return_distance=True, rng=0)
    segments = _extract_skeleton_segments(skeleton, distance)
    if not segments:
        return []

    wall_coords: list[tuple[float, float, float, float]] = []
    payloads: list[dict[str, Any]] = []
    for segment in segments:
        x1, y1, x2, y2 = _segment_endpoints(segment["points"])
        dx = float(x2 - x1)
        dy = float(y2 - y1)
        length = math.hypot(dx, dy)
        if length < float(min_segment_length):
            continue

        orientation, sx1, sy1, sx2, sy2 = _normalize_segment_orientation(x1, y1, x2, y2)
        wall_coords.append((sx1, sy1, sx2, sy2))
        payloads.append(
            {
                "orientation": orientation,
                "mean_width_px": float(segment["mean_width_px"]),
            }
        )

    if not wall_coords:
        return []

    snapped = snap_endpoint_clusters(wall_coords, tolerance=float(endpoint_tolerance))
    records: list[dict[str, Any]] = []
    for coords, payload in zip(snapped, payloads):
        x1, y1, x2, y2 = coords
        orientation, x1, y1, x2, y2 = _normalize_segment_orientation(x1, y1, x2, y2)
        length = math.hypot(x2 - x1, y2 - y1)
        if length < float(min_segment_length):
            continue
        width_px = float(payload["mean_width_px"])
        if orientation == "diagonal" and length <= max(8.0, width_px * 1.75):
            continue
        records.append(
            {
                "orientation": orientation,
                "x1": float(x1),
                "y1": float(y1),
                "x2": float(x2),
                "y2": float(y2),
                "mean_width_px": width_px,
            }
        )

    condensed = _condense_wall_records(records, binary)
    condensed = _recover_thin_perpendicular_caps(condensed, binary)
    condensed = _recover_endpoint_aligned_isolated_segments(condensed, binary)
    condensed = _collapse_parallel_widening_duplicates(condensed, binary)
    condensed = _prune_centered_stub_artifacts(condensed)
    widths = [record["mean_width_px"] for record in condensed if record["mean_width_px"] > 0.0]
    if widths:
        widths.sort()
        mid = len(widths) // 2
        width_median = widths[mid] if len(widths) % 2 else (widths[mid - 1] + widths[mid]) / 2.0
    else:
        width_median = 0.0

    annotations: list[dict[str, Any]] = []
    dedupe: set[tuple[float, float, float, float]] = set()
    for record in condensed:
        orientation = str(record["orientation"])
        x1 = float(record["x1"])
        y1 = float(record["y1"])
        x2 = float(record["x2"])
        y2 = float(record["y2"])
        width_px = float(record["mean_width_px"])

        key = tuple(round(value, 1) for value in (x1, y1, x2, y2))
        reverse_key = tuple(round(value, 1) for value in (x2, y2, x1, y1))
        if key in dedupe or reverse_key in dedupe:
            continue
        dedupe.add(key)

        thickness = 6 if width_px > width_median else 4
        polygon = _wall_polygon_from_segment(x1, y1, x2, y2, width_px)
        annotations.append(
            {
                "id": f"mask-native-wall-{uuid.uuid4()}",
                "type": "wall",
                "x1": round(float(x1), 1),
                "y1": round(float(y1), 1),
                "x2": round(float(x2), 1),
                "y2": round(float(y2), 1),
                "thickness": thickness,
                "orientation": orientation,
                "_source": "mitunet_mask_native",
                "_mean_width_px": round(width_px, 3),
                "polygon": [
                    {"x": round(float(point[0]), 1), "y": round(float(point[1]), 1)}
                    for point in polygon
                ],
            }
        )

    return annotations


def _condense_wall_records(
    records: list[dict[str, Any]],
    support_mask: np.ndarray,
) -> list[dict[str, Any]]:
    if not records:
        return []

    diagonals = [dict(record) for record in records if record.get("orientation") == "diagonal"]
    condensed: list[dict[str, Any]] = []
    condensed.extend(_condense_axis_records(
        [record for record in records if record.get("orientation") == "horizontal"],
        orientation="horizontal",
        support_mask=support_mask,
    ))
    condensed.extend(_condense_axis_records(
        [record for record in records if record.get("orientation") == "vertical"],
        orientation="vertical",
        support_mask=support_mask,
    ))
    condensed.extend(diagonals)
    return condensed


def _recover_thin_perpendicular_caps(
    records: list[dict[str, Any]],
    support_mask: np.ndarray,
    *,
    cap_extent_max: float = 8.0,
    overlap_tolerance: float = 2.0,
    mirror_span_tolerance: float = 3.0,
) -> list[dict[str, Any]]:
    if not records or support_mask.size == 0:
        return records

    coverage = _records_coverage_mask(records, support_mask.shape)
    residual = np.logical_and(support_mask > 0, coverage == 0).astype(np.uint8)
    if np.count_nonzero(residual) == 0:
        return records

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(residual, connectivity=8)
    if num_labels <= 1:
        return records

    components: list[dict[str, float]] = []
    for label in range(1, num_labels):
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        w = int(stats[label, cv2.CC_STAT_WIDTH])
        h = int(stats[label, cv2.CC_STAT_HEIGHT])
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area <= 0 or w <= 0 or h <= 0:
            continue
        components.append(
            {
                "label": float(label),
                "x1": float(x),
                "y1": float(y),
                "x2": float(x + w - 1),
                "y2": float(y + h - 1),
                "width": float(w),
                "height": float(h),
                "area": float(area),
            }
        )

    if not components:
        return records

    recovered: list[dict[str, Any]] = list(records)
    for parent in records:
        orientation = str(parent.get("orientation"))
        if orientation not in {"horizontal", "vertical"}:
            continue

        parent_width = max(float(parent.get("mean_width_px", 0.0)), 1.0)
        side_components: dict[str, list[dict[str, float]]] = {
            "negative": [],
            "positive": [],
        }
        for component in components:
            side = _component_side_for_parent(
                component,
                parent,
                cap_extent_max=cap_extent_max,
                overlap_tolerance=overlap_tolerance,
            )
            if side is None:
                continue
            component_span = max(
                component["width"] if orientation == "horizontal" else component["height"],
                1.0,
            )
            if component_span > max(parent_width * 1.35, 12.0):
                continue
            side_components[side].append(component)

        if not side_components["negative"] and not side_components["positive"]:
            continue

        mirrored = _mirrored_component_labels(
            parent,
            side_components["negative"],
            side_components["positive"],
            span_tolerance=mirror_span_tolerance,
        )

        for side, components_for_side in side_components.items():
            for component in components_for_side:
                if int(component["label"]) in mirrored:
                    continue
                recovered_record = _recover_cap_record_from_component(component, parent, side=side)
                if recovered_record is not None:
                    recovered.append(recovered_record)

    return recovered


def _recover_endpoint_aligned_isolated_segments(
    records: list[dict[str, Any]],
    support_mask: np.ndarray,
    *,
    min_area: float = 24.0,
    min_major_span: float = 18.0,
    aspect_ratio_min: float = 2.8,
    max_minor_span: float = 10.0,
    min_face_gap: float = 8.0,
    max_face_gap: float = 24.0,
    overlap_tolerance: float = 2.0,
    endpoint_anchor_tolerance: float = 10.0,
) -> list[dict[str, Any]]:
    if not records or support_mask.size == 0:
        return records

    coverage = _records_coverage_mask(records, support_mask.shape)
    residual = np.logical_and(support_mask > 0, coverage == 0).astype(np.uint8)
    if np.count_nonzero(residual) == 0:
        return records

    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(residual, connectivity=8)
    if num_labels <= 1:
        return records

    recovered: list[dict[str, Any]] = list(records)
    added = False
    for label in range(1, num_labels):
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        w = int(stats[label, cv2.CC_STAT_WIDTH])
        h = int(stats[label, cv2.CC_STAT_HEIGHT])
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area <= 0 or w <= 0 or h <= 0:
            continue

        component = {
            "label": float(label),
            "x1": float(x),
            "y1": float(y),
            "x2": float(x + w - 1),
            "y2": float(y + h - 1),
            "width": float(w),
            "height": float(h),
            "area": float(area),
        }
        component_orientation = _residual_component_orientation(
            component,
            min_area=min_area,
            min_major_span=min_major_span,
            aspect_ratio_min=aspect_ratio_min,
            wide_component_aspect_min=aspect_ratio_min,
            max_minor_span=max_minor_span,
        )
        if component_orientation not in {"horizontal", "vertical"}:
            continue

        match = _match_endpoint_aligned_parent(
            component,
            records,
            component_orientation=component_orientation,
            min_face_gap=min_face_gap,
            max_face_gap=max_face_gap,
            overlap_tolerance=overlap_tolerance,
            endpoint_anchor_tolerance=endpoint_anchor_tolerance,
        )
        if match is None:
            continue

        candidate = _recover_isolated_endpoint_record_from_component(component, match)
        if candidate is None:
            continue
        candidate = _extend_axis_record_to_mask(
            candidate,
            orientation=str(candidate["orientation"]),
            support_mask=support_mask,
        )
        if _has_similar_axis_record(
            recovered,
            candidate,
            orientation=str(candidate["orientation"]),
        ):
            continue
        recovered.append(candidate)
        added = True

    if not added:
        return records
    return recovered


def _recover_axis_aligned_residual_branches(
    records: list[dict[str, Any]],
    support_mask: np.ndarray,
    *,
    min_area: float = 24.0,
    min_major_span: float = 10.0,
    aspect_ratio_min: float = 1.6,
    wide_component_aspect_min: float = 1.4,
    max_coord_gap: float = 14.0,
    max_minor_factor: float = 2.5,
) -> list[dict[str, Any]]:
    if not records or support_mask.size == 0:
        return records

    coverage = _records_coverage_mask(records, support_mask.shape)
    residual = np.logical_and(support_mask > 0, coverage == 0).astype(np.uint8)
    if np.count_nonzero(residual) == 0:
        return records

    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(residual, connectivity=8)
    if num_labels <= 1:
        return records

    components: list[dict[str, float]] = []
    for label in range(1, num_labels):
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        w = int(stats[label, cv2.CC_STAT_WIDTH])
        h = int(stats[label, cv2.CC_STAT_HEIGHT])
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area <= 0 or w <= 0 or h <= 0:
            continue
        components.append(
            {
                "label": float(label),
                "x1": float(x),
                "y1": float(y),
                "x2": float(x + w - 1),
                "y2": float(y + h - 1),
                "width": float(w),
                "height": float(h),
                "area": float(area),
            }
        )

    if not components:
        return records

    widths = [
        max(float(record.get("mean_width_px", 0.0)), 1.0)
        for record in records
        if float(record.get("mean_width_px", 0.0)) > 0.0
    ]
    default_width = float(np.median(widths)) if widths else 6.0
    max_minor_span = max(default_width * max_minor_factor, 20.0)

    recovered: list[dict[str, Any]] = list(records)
    added = False
    for component in sorted(components, key=lambda item: float(item["area"]), reverse=True):
        orientation = _residual_component_orientation(
            component,
            min_area=min_area,
            min_major_span=min_major_span,
            aspect_ratio_min=aspect_ratio_min,
            wide_component_aspect_min=wide_component_aspect_min,
            max_minor_span=max_minor_span,
        )
        if orientation is None:
            continue
        recovered_record = _recover_axis_residual_record(
            component,
            records,
            orientation=orientation,
            support_mask=support_mask,
            default_width=default_width,
            max_coord_gap=max(default_width * 1.75, max_coord_gap),
        )
        if recovered_record is None:
            continue
        recovered.append(recovered_record)
        added = True

    if not added:
        return records
    return _condense_wall_records(recovered, support_mask=support_mask)


def _collapse_parallel_widening_duplicates(
    records: list[dict[str, Any]],
    support_mask: np.ndarray,
) -> list[dict[str, Any]]:
    if len(records) < 2:
        return records

    remaining = [dict(record) for record in records]
    changed = True
    while changed:
        changed = False
        next_records: list[dict[str, Any]] = []
        consumed = [False] * len(remaining)
        for index, record in enumerate(remaining):
            if consumed[index]:
                continue

            merged = dict(record)
            for candidate_index in range(index + 1, len(remaining)):
                if consumed[candidate_index]:
                    continue
                candidate = remaining[candidate_index]
                orientation = str(merged.get("orientation"))
                if orientation not in {"horizontal", "vertical"}:
                    continue
                if not _should_merge_parallel_widening(
                    merged,
                    candidate,
                    orientation=orientation,
                    support_mask=support_mask,
                    coord_tolerance=3.0,
                    support_threshold=0.55,
                ):
                    continue
                merged = _merge_parallel_duplicate_records(
                    merged,
                    candidate,
                    orientation=orientation,
                )
                consumed[candidate_index] = True
                changed = True

            next_records.append(merged)
        remaining = next_records

    return remaining


def _records_coverage_mask(
    records: list[dict[str, Any]],
    shape: tuple[int, int],
) -> np.ndarray:
    coverage = np.zeros(shape, dtype=np.uint8)
    for record in records:
        polygon = _wall_polygon_from_segment(
            float(record["x1"]),
            float(record["y1"]),
            float(record["x2"]),
            float(record["y2"]),
            float(record.get("mean_width_px", 0.0)),
        )
        pts = np.array(
            [[int(round(point[0])), int(round(point[1]))] for point in polygon],
            dtype=np.int32,
        )
        if pts.size == 0:
            continue
        cv2.fillPoly(coverage, [pts], 1)
    return coverage


def _residual_component_orientation(
    component: dict[str, float],
    *,
    min_area: float,
    min_major_span: float,
    aspect_ratio_min: float,
    wide_component_aspect_min: float,
    max_minor_span: float,
) -> str | None:
    width = max(float(component["width"]), 1.0)
    height = max(float(component["height"]), 1.0)
    area = float(component["area"])
    major = max(width, height)
    minor = min(width, height)
    if area < min_area or major < min_major_span or minor > max_minor_span:
        return None

    aspect = major / max(minor, 1.0)
    if height >= width * aspect_ratio_min:
        return "vertical"
    if width >= height * aspect_ratio_min:
        return "horizontal"
    if area >= max(min_area * 4.0, 96.0) and aspect >= wide_component_aspect_min:
        return "vertical" if height >= width else "horizontal"
    return None


def _recover_axis_residual_record(
    component: dict[str, float],
    records: list[dict[str, Any]],
    *,
    orientation: str,
    support_mask: np.ndarray,
    default_width: float,
    max_coord_gap: float,
) -> dict[str, Any] | None:
    reference = _nearest_parallel_axis_record(
        component,
        records,
        orientation=orientation,
        max_coord_gap=max_coord_gap,
    )
    if reference is not None and _component_is_parallel_widening(
        component,
        reference,
        orientation=orientation,
    ):
        return None
    if reference is None and not _component_touches_mask_border(component, support_mask.shape):
        return None

    width_px = _residual_component_width(component, reference, default_width=default_width)
    if orientation == "horizontal":
        coord = float(reference["y1"]) if reference is not None else (float(component["y1"]) + float(component["y2"])) / 2.0
        candidate = {
            "orientation": "horizontal",
            "x1": float(component["x1"]),
            "y1": coord,
            "x2": float(component["x2"]),
            "y2": coord,
            "mean_width_px": width_px,
        }
    else:
        coord = float(reference["x1"]) if reference is not None else (float(component["x1"]) + float(component["x2"])) / 2.0
        candidate = {
            "orientation": "vertical",
            "x1": coord,
            "y1": float(component["y1"]),
            "x2": coord,
            "y2": float(component["y2"]),
            "mean_width_px": width_px,
        }

    candidate = _extend_axis_record_to_mask(
        candidate,
        orientation=orientation,
        support_mask=support_mask,
    )
    if _has_similar_axis_record(records, candidate, orientation=orientation):
        return None
    return candidate


def _nearest_parallel_axis_record(
    component: dict[str, float],
    records: list[dict[str, Any]],
    *,
    orientation: str,
    max_coord_gap: float,
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_score: float | None = None
    for record in records:
        if str(record.get("orientation")) != orientation:
            continue

        if orientation == "horizontal":
            record_coord = float(record["y1"])
            record_lo = min(float(record["x1"]), float(record["x2"]))
            record_hi = max(float(record["x1"]), float(record["x2"]))
            component_coord = (float(component["y1"]) + float(component["y2"])) / 2.0
            component_lo = float(component["x1"])
            component_hi = float(component["x2"])
        else:
            record_coord = float(record["x1"])
            record_lo = min(float(record["y1"]), float(record["y2"]))
            record_hi = max(float(record["y1"]), float(record["y2"]))
            component_coord = (float(component["x1"]) + float(component["x2"])) / 2.0
            component_lo = float(component["y1"])
            component_hi = float(component["y2"])

        coord_gap = abs(component_coord - record_coord)
        if coord_gap > max_coord_gap:
            continue

        span_gap = max(0.0, max(component_lo, record_lo) - min(component_hi, record_hi))
        score = coord_gap + (span_gap * 0.15)
        if best_score is None or score < best_score:
            best = record
            best_score = score

    return best


def _residual_component_width(
    component: dict[str, float],
    reference: dict[str, Any] | None,
    *,
    default_width: float,
) -> float:
    if reference is not None:
        return max(float(reference.get("mean_width_px", default_width)), 1.0)

    minor = min(float(component["width"]), float(component["height"]))
    return max(1.0, min(minor, max(default_width * 1.5, 10.0)))


def _component_is_parallel_widening(
    component: dict[str, float],
    reference: dict[str, Any],
    *,
    orientation: str,
    overlap_ratio_min: float = 0.65,
    max_face_gap: float = 2.5,
) -> bool:
    ref_width = max(float(reference.get("mean_width_px", 0.0)), 1.0)
    minor = min(float(component["width"]), float(component["height"]))
    if minor > max(ref_width * 1.35, 8.0):
        return False

    if orientation == "horizontal":
        component_lo = float(component["x1"])
        component_hi = float(component["x2"])
        component_band_lo = float(component["y1"])
        component_band_hi = float(component["y2"])
        reference_coord = float(reference["y1"])
        reference_lo = min(float(reference["x1"]), float(reference["x2"]))
        reference_hi = max(float(reference["x1"]), float(reference["x2"]))
    else:
        component_lo = float(component["y1"])
        component_hi = float(component["y2"])
        component_band_lo = float(component["x1"])
        component_band_hi = float(component["x2"])
        reference_coord = float(reference["x1"])
        reference_lo = min(float(reference["y1"]), float(reference["y2"]))
        reference_hi = max(float(reference["y1"]), float(reference["y2"]))

    overlap = min(component_hi, reference_hi) - max(component_lo, reference_lo)
    component_span = max(component_hi - component_lo, 1.0)
    overlap_ratio = overlap / component_span
    if overlap_ratio < overlap_ratio_min:
        return False

    face_half = max(ref_width / 2.0, 1.0)
    face_min = reference_coord - face_half
    face_max = reference_coord + face_half
    if component_band_hi < face_min:
        face_gap = face_min - component_band_hi
    elif component_band_lo > face_max:
        face_gap = component_band_lo - face_max
    else:
        face_gap = 0.0
    return face_gap <= max_face_gap


def _component_touches_mask_border(
    component: dict[str, float],
    shape: tuple[int, int],
    *,
    border_tolerance: float = 1.0,
) -> bool:
    max_y = float(shape[0] - 1)
    max_x = float(shape[1] - 1)
    return (
        float(component["x1"]) <= border_tolerance
        or float(component["y1"]) <= border_tolerance
        or float(component["x2"]) >= (max_x - border_tolerance)
        or float(component["y2"]) >= (max_y - border_tolerance)
    )


def _has_similar_axis_record(
    records: list[dict[str, Any]],
    candidate: dict[str, Any],
    *,
    orientation: str,
    coord_tolerance: float = 1.5,
    span_overlap_tolerance: float = 2.0,
) -> bool:
    if orientation == "horizontal":
        candidate_coord = float(candidate["y1"])
        candidate_lo = min(float(candidate["x1"]), float(candidate["x2"]))
        candidate_hi = max(float(candidate["x1"]), float(candidate["x2"]))
    else:
        candidate_coord = float(candidate["x1"])
        candidate_lo = min(float(candidate["y1"]), float(candidate["y2"]))
        candidate_hi = max(float(candidate["y1"]), float(candidate["y2"]))

    for record in records:
        if str(record.get("orientation")) != orientation:
            continue
        if orientation == "horizontal":
            record_coord = float(record["y1"])
            record_lo = min(float(record["x1"]), float(record["x2"]))
            record_hi = max(float(record["x1"]), float(record["x2"]))
        else:
            record_coord = float(record["x1"])
            record_lo = min(float(record["y1"]), float(record["y2"]))
            record_hi = max(float(record["y1"]), float(record["y2"]))

        if abs(candidate_coord - record_coord) > coord_tolerance:
            continue
        overlap = min(candidate_hi, record_hi) - max(candidate_lo, record_lo)
        if overlap >= min(candidate_hi - candidate_lo, record_hi - record_lo) - span_overlap_tolerance:
            return True
    return False


def _component_side_for_parent(
    component: dict[str, float],
    parent: dict[str, Any],
    *,
    cap_extent_max: float,
    overlap_tolerance: float,
) -> str | None:
    orientation = str(parent.get("orientation"))
    parent_width = max(float(parent.get("mean_width_px", 0.0)), 1.0)
    half = max((parent_width - 1.0) / 2.0, 1.0)

    if orientation == "horizontal":
        span_lo = min(float(parent["x1"]), float(parent["x2"]))
        span_hi = max(float(parent["x1"]), float(parent["x2"]))
        overlap = min(component["x2"], span_hi) - max(component["x1"], span_lo)
        if overlap < -overlap_tolerance:
            return None

        coord = float(parent["y1"])
        face_min = coord - half
        face_max = coord + half
        if component["y2"] <= face_min + overlap_tolerance and (face_min - component["y2"]) <= cap_extent_max:
            return "negative"
        if component["y1"] >= face_max - overlap_tolerance and (component["y1"] - face_max) <= cap_extent_max:
            return "positive"
        return None

    span_lo = min(float(parent["y1"]), float(parent["y2"]))
    span_hi = max(float(parent["y1"]), float(parent["y2"]))
    overlap = min(component["y2"], span_hi) - max(component["y1"], span_lo)
    if overlap < -overlap_tolerance:
        return None

    coord = float(parent["x1"])
    face_min = coord - half
    face_max = coord + half
    if component["x2"] <= face_min + overlap_tolerance and (face_min - component["x2"]) <= cap_extent_max:
        return "negative"
    if component["x1"] >= face_max - overlap_tolerance and (component["x1"] - face_max) <= cap_extent_max:
        return "positive"
    return None


def _mirrored_component_labels(
    parent: dict[str, Any],
    negative: list[dict[str, float]],
    positive: list[dict[str, float]],
    *,
    span_tolerance: float,
) -> set[int]:
    mirrored: set[int] = set()
    if not negative or not positive:
        return mirrored

    orientation = str(parent.get("orientation"))
    for left in negative:
        for right in positive:
            if orientation == "horizontal":
                overlap = min(left["x2"], right["x2"]) - max(left["x1"], right["x1"])
                if overlap < -span_tolerance:
                    continue
                if abs(left["width"] - right["width"]) > span_tolerance + 1.0:
                    continue
            else:
                overlap = min(left["y2"], right["y2"]) - max(left["y1"], right["y1"])
                if overlap < -span_tolerance:
                    continue
                if abs(left["height"] - right["height"]) > span_tolerance + 1.0:
                    continue
            mirrored.add(int(left["label"]))
            mirrored.add(int(right["label"]))
    return mirrored


def _recover_cap_record_from_component(
    component: dict[str, float],
    parent: dict[str, Any],
    *,
    side: str,
) -> dict[str, Any] | None:
    orientation = str(parent.get("orientation"))
    parent_width = max(float(parent.get("mean_width_px", 0.0)), 1.0)

    if orientation == "horizontal":
        x_center = max(
            min((component["x1"] + component["x2"]) / 2.0, max(float(parent["x1"]), float(parent["x2"]))),
            min(float(parent["x1"]), float(parent["x2"])),
        )
        y_parent = float(parent["y1"])
        if side == "negative":
            y1, y2 = component["y1"], y_parent
        else:
            y1, y2 = y_parent, component["y2"]
        if abs(y2 - y1) < 2.0:
            return None
        return {
            "orientation": "vertical",
            "x1": x_center,
            "y1": y1,
            "x2": x_center,
            "y2": y2,
            "mean_width_px": parent_width,
        }

    y_center = max(
        min((component["y1"] + component["y2"]) / 2.0, max(float(parent["y1"]), float(parent["y2"]))),
        min(float(parent["y1"]), float(parent["y2"])),
    )
    x_parent = float(parent["x1"])
    if side == "negative":
        x1, x2 = component["x1"], x_parent
    else:
        x1, x2 = x_parent, component["x2"]
    if abs(x2 - x1) < 2.0:
        return None
    return {
        "orientation": "horizontal",
        "x1": x1,
        "y1": y_center,
        "x2": x2,
        "y2": y_center,
        "mean_width_px": parent_width,
    }


def _match_endpoint_aligned_parent(
    component: dict[str, float],
    records: list[dict[str, Any]],
    *,
    component_orientation: str,
    min_face_gap: float,
    max_face_gap: float,
    overlap_tolerance: float,
    endpoint_anchor_tolerance: float,
) -> dict[str, Any] | None:
    best_parent: dict[str, Any] | None = None
    best_gap: float | None = None
    expected_parent_orientation = "horizontal" if component_orientation == "vertical" else "vertical"

    for record in records:
        if str(record.get("orientation")) != expected_parent_orientation:
            continue
        gap = _endpoint_aligned_face_gap(
            component,
            record,
            overlap_tolerance=overlap_tolerance,
            endpoint_anchor_tolerance=endpoint_anchor_tolerance,
        )
        if gap is None or gap < min_face_gap or gap > max_face_gap:
            continue
        if best_gap is None or gap < best_gap:
            best_parent = record
            best_gap = gap

    return best_parent


def _endpoint_aligned_face_gap(
    component: dict[str, float],
    parent: dict[str, Any],
    *,
    overlap_tolerance: float,
    endpoint_anchor_tolerance: float,
) -> float | None:
    orientation = str(parent.get("orientation"))
    parent_width = max(float(parent.get("mean_width_px", 0.0)), 1.0)
    half = max((parent_width - 1.0) / 2.0, 1.0)

    if orientation == "horizontal":
        span_lo = min(float(parent["x1"]), float(parent["x2"]))
        span_hi = max(float(parent["x1"]), float(parent["x2"]))
        overlap_lo = max(component["x1"], span_lo)
        overlap_hi = min(component["x2"], span_hi)
        if overlap_hi < overlap_lo - overlap_tolerance:
            return None
        anchor_tol = max(endpoint_anchor_tolerance, component["width"] + overlap_tolerance)
        endpoint_anchored = overlap_hi <= span_lo + anchor_tol or overlap_lo >= span_hi - anchor_tol
        if not endpoint_anchored:
            return None

        coord = float(parent["y1"])
        face_min = coord - half
        face_max = coord + half
        if component["y2"] <= face_min + overlap_tolerance:
            return max(0.0, face_min - component["y2"])
        if component["y1"] >= face_max - overlap_tolerance:
            return max(0.0, component["y1"] - face_max)
        return None

    span_lo = min(float(parent["y1"]), float(parent["y2"]))
    span_hi = max(float(parent["y1"]), float(parent["y2"]))
    overlap_lo = max(component["y1"], span_lo)
    overlap_hi = min(component["y2"], span_hi)
    if overlap_hi < overlap_lo - overlap_tolerance:
        return None
    anchor_tol = max(endpoint_anchor_tolerance, component["height"] + overlap_tolerance)
    endpoint_anchored = overlap_hi <= span_lo + anchor_tol or overlap_lo >= span_hi - anchor_tol
    if not endpoint_anchored:
        return None

    coord = float(parent["x1"])
    face_min = coord - half
    face_max = coord + half
    if component["x2"] <= face_min + overlap_tolerance:
        return max(0.0, face_min - component["x2"])
    if component["x1"] >= face_max - overlap_tolerance:
        return max(0.0, component["x1"] - face_max)
    return None


def _recover_isolated_endpoint_record_from_component(
    component: dict[str, float],
    parent: dict[str, Any],
) -> dict[str, Any] | None:
    orientation = str(parent.get("orientation"))
    parent_width = max(float(parent.get("mean_width_px", 0.0)), 1.0)

    if orientation == "horizontal":
        x_center = max(
            min((component["x1"] + component["x2"]) / 2.0, max(float(parent["x1"]), float(parent["x2"]))),
            min(float(parent["x1"]), float(parent["x2"])),
        )
        if abs(component["y2"] - component["y1"]) < 2.0:
            return None
        return {
            "orientation": "vertical",
            "x1": x_center,
            "y1": float(component["y1"]),
            "x2": x_center,
            "y2": float(component["y2"]),
            "mean_width_px": parent_width,
        }

    y_center = max(
        min((component["y1"] + component["y2"]) / 2.0, max(float(parent["y1"]), float(parent["y2"]))),
        min(float(parent["y1"]), float(parent["y2"])),
    )
    if abs(component["x2"] - component["x1"]) < 2.0:
        return None
    return {
        "orientation": "horizontal",
        "x1": float(component["x1"]),
        "y1": y_center,
        "x2": float(component["x2"]),
        "y2": y_center,
        "mean_width_px": parent_width,
    }


def _prune_centered_stub_artifacts(
    records: list[dict[str, Any]],
    *,
    short_length_max: float = 24.0,
) -> list[dict[str, Any]]:
    if len(records) < 2:
        return records

    kept: list[dict[str, Any]] = []
    for record in records:
        orientation = str(record.get("orientation"))
        if orientation not in {"horizontal", "vertical"}:
            kept.append(record)
            continue

        length = math.hypot(
            float(record["x2"]) - float(record["x1"]),
            float(record["y2"]) - float(record["y1"]),
        )
        width_px = max(float(record.get("mean_width_px", 0.0)), 1.0)
        if length > max(short_length_max, width_px * 2.25):
            kept.append(record)
            continue

        if _is_centered_stub_artifact(record, records):
            continue
        kept.append(record)
    return kept


def _is_centered_stub_artifact(
    record: dict[str, Any],
    records: list[dict[str, Any]],
) -> bool:
    orientation = str(record.get("orientation"))
    perp_orientation = "vertical" if orientation == "horizontal" else "horizontal"
    width_px = max(float(record.get("mean_width_px", 0.0)), 1.0)

    if orientation == "horizontal":
        stub_lo = min(float(record["x1"]), float(record["x2"]))
        stub_hi = max(float(record["x1"]), float(record["x2"]))
        stub_mid = (stub_lo + stub_hi) / 2.0
        stub_cross = float(record["y1"])
    else:
        stub_lo = min(float(record["y1"]), float(record["y2"]))
        stub_hi = max(float(record["y1"]), float(record["y2"]))
        stub_mid = (stub_lo + stub_hi) / 2.0
        stub_cross = float(record["x1"])

    for candidate in records:
        if candidate is record or candidate.get("orientation") != perp_orientation:
            continue

        cand_width = max(float(candidate.get("mean_width_px", 0.0)), 1.0)
        cand_length = math.hypot(
            float(candidate["x2"]) - float(candidate["x1"]),
            float(candidate["y2"]) - float(candidate["y1"]),
        )
        if cand_length <= max(28.0, width_px * 2.5):
            continue

        if orientation == "horizontal":
            cand_coord = float(candidate["x1"])
            cand_lo = min(float(candidate["y1"]), float(candidate["y2"]))
            cand_hi = max(float(candidate["y1"]), float(candidate["y2"]))
            if not (cand_lo - 2.0 <= stub_cross <= cand_hi + 2.0):
                continue
        else:
            cand_coord = float(candidate["y1"])
            cand_lo = min(float(candidate["x1"]), float(candidate["x2"]))
            cand_hi = max(float(candidate["x1"]), float(candidate["x2"]))
            if not (cand_lo - 2.0 <= stub_cross <= cand_hi + 2.0):
                continue

        face_half = max(cand_width / 2.0, width_px / 2.0, 1.0)
        face_lo = cand_coord - face_half
        face_hi = cand_coord + face_half
        outside_lo = max(0.0, face_lo - stub_lo)
        outside_hi = max(0.0, stub_hi - face_hi)
        escape_threshold = max(4.0, width_px * 0.6, cand_width * 0.45)
        if outside_lo > 0.0 and outside_hi > 0.0 and outside_lo <= escape_threshold and outside_hi <= escape_threshold:
            return True

    return False


def _condense_axis_records(
    records: list[dict[str, Any]],
    *,
    orientation: str,
    support_mask: np.ndarray,
    coord_tolerance: float = 3.0,
    gap_tolerance: float = 12.0,
    support_threshold: float = 0.35,
) -> list[dict[str, Any]]:
    if not records:
        return []

    if orientation == "horizontal":
        ordered = sorted(records, key=lambda record: (float(record["y1"]), min(float(record["x1"]), float(record["x2"]))))
    else:
        ordered = sorted(records, key=lambda record: (float(record["x1"]), min(float(record["y1"]), float(record["y2"]))))

    groups: list[list[dict[str, Any]]] = []
    for record in ordered:
        coord = float(record["y1"] if orientation == "horizontal" else record["x1"])
        placed = False
        for group in groups:
            ref_coord = float(group[0]["y1"] if orientation == "horizontal" else group[0]["x1"])
            if abs(coord - ref_coord) <= coord_tolerance or _should_merge_parallel_widening(
                group[0],
                record,
                orientation=orientation,
                support_mask=support_mask,
                coord_tolerance=coord_tolerance,
            ):
                group.append(record)
                placed = True
                break
        if not placed:
            groups.append([record])

    condensed: list[dict[str, Any]] = []
    for group in groups:
        group = sorted(
            group,
            key=lambda record: min(
                float(record["x1"]) if orientation == "horizontal" else float(record["y1"]),
                float(record["x2"]) if orientation == "horizontal" else float(record["y2"]),
            ),
        )
        current = dict(group[0])
        for record in group[1:]:
            if _can_merge_axis_records(
                current,
                record,
                orientation=orientation,
                support_mask=support_mask,
                gap_tolerance=gap_tolerance,
                coord_tolerance=coord_tolerance,
                support_threshold=support_threshold,
            ):
                current = _merge_axis_records(current, record, orientation=orientation)
            else:
                condensed.append(_extend_axis_record_to_mask(current, orientation=orientation, support_mask=support_mask))
                current = dict(record)
        condensed.append(_extend_axis_record_to_mask(current, orientation=orientation, support_mask=support_mask))

    if len(condensed) <= 1:
        return condensed

    merged_again: list[dict[str, Any]] = []
    current = dict(condensed[0])
    for record in condensed[1:]:
        if _can_merge_axis_records(
            current,
            record,
            orientation=orientation,
            support_mask=support_mask,
            gap_tolerance=gap_tolerance,
            coord_tolerance=coord_tolerance,
            support_threshold=support_threshold,
        ):
            current = _merge_axis_records(current, record, orientation=orientation)
        else:
            merged_again.append(current)
            current = dict(record)
    merged_again.append(current)
    return merged_again


def _can_merge_axis_records(
    current: dict[str, Any],
    candidate: dict[str, Any],
    *,
    orientation: str,
    support_mask: np.ndarray,
    gap_tolerance: float,
    coord_tolerance: float,
    support_threshold: float,
) -> bool:
    if current.get("orientation") != orientation or candidate.get("orientation") != orientation:
        return False

    if orientation == "horizontal":
        current_coord = float(current["y1"])
        candidate_coord = float(candidate["y1"])
        current_start = min(float(current["x1"]), float(current["x2"]))
        current_end = max(float(current["x1"]), float(current["x2"]))
        candidate_start = min(float(candidate["x1"]), float(candidate["x2"]))
        candidate_end = max(float(candidate["x1"]), float(candidate["x2"]))
    else:
        current_coord = float(current["x1"])
        candidate_coord = float(candidate["x1"])
        current_start = min(float(current["y1"]), float(current["y2"]))
        current_end = max(float(current["y1"]), float(current["y2"]))
        candidate_start = min(float(candidate["y1"]), float(candidate["y2"]))
        candidate_end = max(float(candidate["y1"]), float(candidate["y2"]))

    if abs(current_coord - candidate_coord) > coord_tolerance and not _should_merge_parallel_widening(
        current,
        candidate,
        orientation=orientation,
        support_mask=support_mask,
        coord_tolerance=coord_tolerance,
    ):
        return False

    gap = candidate_start - current_end
    if gap <= gap_tolerance:
        return True

    if gap > gap_tolerance * 2.0:
        return False

    return _axis_gap_support_ratio(
        support_mask,
        orientation=orientation,
        start=current_end,
        end=candidate_start,
        coord=(current_coord + candidate_coord) / 2.0,
        half_width=max(float(current.get("mean_width_px", 0.0)), float(candidate.get("mean_width_px", 0.0))) / 2.0,
    ) >= support_threshold


def _should_merge_parallel_widening(
    current: dict[str, Any],
    candidate: dict[str, Any],
    *,
    orientation: str,
    support_mask: np.ndarray,
    coord_tolerance: float,
    min_overlap_ratio: float = 0.65,
    support_threshold: float = 0.7,
    min_relative_span_ratio: float = 0.75,
) -> bool:
    if current.get("orientation") != orientation or candidate.get("orientation") != orientation:
        return False

    if orientation == "horizontal":
        current_coord = float(current["y1"])
        candidate_coord = float(candidate["y1"])
        current_lo = min(float(current["x1"]), float(current["x2"]))
        current_hi = max(float(current["x1"]), float(current["x2"]))
        candidate_lo = min(float(candidate["x1"]), float(candidate["x2"]))
        candidate_hi = max(float(candidate["x1"]), float(candidate["x2"]))
    else:
        current_coord = float(current["x1"])
        candidate_coord = float(candidate["x1"])
        current_lo = min(float(current["y1"]), float(current["y2"]))
        current_hi = max(float(current["y1"]), float(current["y2"]))
        candidate_lo = min(float(candidate["y1"]), float(candidate["y2"]))
        candidate_hi = max(float(candidate["y1"]), float(candidate["y2"]))

    coord_gap = abs(current_coord - candidate_coord)
    max_width = max(
        float(current.get("mean_width_px", 0.0)),
        float(candidate.get("mean_width_px", 0.0)),
        1.0,
    )
    if coord_gap > max(coord_tolerance + 1.5, max_width * 0.45):
        return False

    overlap = min(current_hi, candidate_hi) - max(current_lo, candidate_lo)
    current_span = max(current_hi - current_lo, 1.0)
    candidate_span = max(candidate_hi - candidate_lo, 1.0)
    if overlap < candidate_span * min_overlap_ratio:
        return False
    if min(current_span, candidate_span) / max(current_span, candidate_span) < min_relative_span_ratio:
        return False

    band_support = _parallel_band_support_ratio(
        support_mask,
        orientation=orientation,
        span_start=max(current_lo, candidate_lo),
        span_end=min(current_hi, candidate_hi),
        coord_a=current_coord,
        coord_b=candidate_coord,
        half_width=max_width / 2.0,
    )
    return band_support >= support_threshold


def _parallel_band_support_ratio(
    support_mask: np.ndarray,
    *,
    orientation: str,
    span_start: float,
    span_end: float,
    coord_a: float,
    coord_b: float,
    half_width: float,
) -> float:
    if support_mask.size == 0:
        return 0.0

    half = max(int(round(float(half_width))), 1)
    if orientation == "horizontal":
        x1 = max(0, int(math.floor(min(span_start, span_end))))
        x2 = min(support_mask.shape[1], int(math.ceil(max(span_start, span_end))) + 1)
        y1 = max(0, int(math.floor(min(coord_a, coord_b) - half)))
        y2 = min(support_mask.shape[0], int(math.ceil(max(coord_a, coord_b) + half)) + 1)
    else:
        y1 = max(0, int(math.floor(min(span_start, span_end))))
        y2 = min(support_mask.shape[0], int(math.ceil(max(span_start, span_end))) + 1)
        x1 = max(0, int(math.floor(min(coord_a, coord_b) - half)))
        x2 = min(support_mask.shape[1], int(math.ceil(max(coord_a, coord_b) + half)) + 1)

    if x2 <= x1 or y2 <= y1:
        return 0.0
    band = support_mask[y1:y2, x1:x2]
    if band.size == 0:
        return 0.0
    return float(np.count_nonzero(band)) / float(band.size)


def _merge_axis_records(
    current: dict[str, Any],
    candidate: dict[str, Any],
    *,
    orientation: str,
) -> dict[str, Any]:
    current_length = max(1.0, math.hypot(float(current["x2"]) - float(current["x1"]), float(current["y2"]) - float(current["y1"])))
    candidate_length = max(1.0, math.hypot(float(candidate["x2"]) - float(candidate["x1"]), float(candidate["y2"]) - float(candidate["y1"])))
    total_length = current_length + candidate_length
    merged_width = (
        (float(current.get("mean_width_px", 0.0)) * current_length)
        + (float(candidate.get("mean_width_px", 0.0)) * candidate_length)
    ) / total_length

    if orientation == "horizontal":
        start = min(float(current["x1"]), float(current["x2"]), float(candidate["x1"]), float(candidate["x2"]))
        end = max(float(current["x1"]), float(current["x2"]), float(candidate["x1"]), float(candidate["x2"]))
        coord = (
            (float(current["y1"]) * current_length)
            + (float(candidate["y1"]) * candidate_length)
        ) / total_length
        return {
            "orientation": "horizontal",
            "x1": start,
            "y1": coord,
            "x2": end,
            "y2": coord,
            "mean_width_px": merged_width,
        }

    start = min(float(current["y1"]), float(current["y2"]), float(candidate["y1"]), float(candidate["y2"]))
    end = max(float(current["y1"]), float(current["y2"]), float(candidate["y1"]), float(candidate["y2"]))
    coord = (
        (float(current["x1"]) * current_length)
        + (float(candidate["x1"]) * candidate_length)
    ) / total_length
    return {
        "orientation": "vertical",
        "x1": coord,
        "y1": start,
        "x2": coord,
        "y2": end,
        "mean_width_px": merged_width,
    }


def _merge_parallel_duplicate_records(
    current: dict[str, Any],
    candidate: dict[str, Any],
    *,
    orientation: str,
) -> dict[str, Any]:
    current_width = max(float(current.get("mean_width_px", 0.0)), 1.0)
    candidate_width = max(float(candidate.get("mean_width_px", 0.0)), 1.0)
    current_length = max(
        1.0,
        math.hypot(float(current["x2"]) - float(current["x1"]), float(current["y2"]) - float(current["y1"])),
    )
    candidate_length = max(
        1.0,
        math.hypot(float(candidate["x2"]) - float(candidate["x1"]), float(candidate["y2"]) - float(candidate["y1"])),
    )

    if orientation == "horizontal":
        current_lo = min(float(current["x1"]), float(current["x2"]))
        current_hi = max(float(current["x1"]), float(current["x2"]))
        candidate_lo = min(float(candidate["x1"]), float(candidate["x2"]))
        candidate_hi = max(float(candidate["x1"]), float(candidate["x2"]))
    else:
        current_lo = min(float(current["y1"]), float(current["y2"]))
        current_hi = max(float(current["y1"]), float(current["y2"]))
        candidate_lo = min(float(candidate["y1"]), float(candidate["y2"]))
        candidate_hi = max(float(candidate["y1"]), float(candidate["y2"]))

    containment_tolerance = 1.25
    current_contains_candidate = (
        current_lo <= candidate_lo + containment_tolerance
        and current_hi >= candidate_hi - containment_tolerance
    )
    candidate_contains_current = (
        candidate_lo <= current_lo + containment_tolerance
        and candidate_hi >= current_hi - containment_tolerance
    )
    if current_contains_candidate or candidate_contains_current:
        current_score = (current_width, current_length)
        candidate_score = (candidate_width, candidate_length)
        if candidate_score > current_score:
            return dict(candidate)
        return dict(current)

    keep_candidate_coord = candidate_width >= current_width

    if orientation == "horizontal":
        return {
            "orientation": "horizontal",
            "x1": min(float(current["x1"]), float(current["x2"]), float(candidate["x1"]), float(candidate["x2"])),
            "y1": float(candidate["y1"] if keep_candidate_coord else current["y1"]),
            "x2": max(float(current["x1"]), float(current["x2"]), float(candidate["x1"]), float(candidate["x2"])),
            "y2": float(candidate["y1"] if keep_candidate_coord else current["y1"]),
            "mean_width_px": max(current_width, candidate_width),
        }

    return {
        "orientation": "vertical",
        "x1": float(candidate["x1"] if keep_candidate_coord else current["x1"]),
        "y1": min(float(current["y1"]), float(current["y2"]), float(candidate["y1"]), float(candidate["y2"])),
        "x2": float(candidate["x1"] if keep_candidate_coord else current["x1"]),
        "y2": max(float(current["y1"]), float(current["y2"]), float(candidate["y1"]), float(candidate["y2"])),
        "mean_width_px": max(current_width, candidate_width),
    }


def _extend_axis_record_to_mask(
    record: dict[str, Any],
    *,
    orientation: str,
    support_mask: np.ndarray,
    support_threshold: float = 0.35,
) -> dict[str, Any]:
    extended = dict(record)
    half_width = max(float(record.get("mean_width_px", 0.0)) / 2.0, 1.0)

    if orientation == "horizontal":
        coord = float(record["y1"])
        start = int(math.floor(min(float(record["x1"]), float(record["x2"]))))
        end = int(math.ceil(max(float(record["x1"]), float(record["x2"]))))
        while start > 0 and _axis_gap_support_ratio(
            support_mask,
            orientation=orientation,
            start=start - 1,
            end=start,
            coord=coord,
            half_width=half_width,
        ) >= support_threshold:
            start -= 1
        max_x = support_mask.shape[1] - 1
        while end < max_x and _axis_gap_support_ratio(
            support_mask,
            orientation=orientation,
            start=end,
            end=end + 1,
            coord=coord,
            half_width=half_width,
        ) >= support_threshold:
            end += 1
        extended["x1"] = float(start)
        extended["x2"] = float(end)
        extended["y1"] = coord
        extended["y2"] = coord
        return extended

    coord = float(record["x1"])
    start = int(math.floor(min(float(record["y1"]), float(record["y2"]))))
    end = int(math.ceil(max(float(record["y1"]), float(record["y2"]))))
    while start > 0 and _axis_gap_support_ratio(
        support_mask,
        orientation=orientation,
        start=start - 1,
        end=start,
        coord=coord,
        half_width=half_width,
    ) >= support_threshold:
        start -= 1
    max_y = support_mask.shape[0] - 1
    while end < max_y and _axis_gap_support_ratio(
        support_mask,
        orientation=orientation,
        start=end,
        end=end + 1,
        coord=coord,
        half_width=half_width,
    ) >= support_threshold:
        end += 1
    extended["x1"] = coord
    extended["x2"] = coord
    extended["y1"] = float(start)
    extended["y2"] = float(end)
    return extended


def _axis_gap_support_ratio(
    support_mask: np.ndarray,
    *,
    orientation: str,
    start: float,
    end: float,
    coord: float,
    half_width: float,
) -> float:
    if support_mask.size == 0:
        return 0.0

    half = max(1, int(round(float(half_width))))
    if orientation == "horizontal":
        x1 = max(0, int(math.floor(min(start, end))))
        x2 = min(support_mask.shape[1], int(math.ceil(max(start, end))) + 1)
        if x2 <= x1:
            x2 = min(support_mask.shape[1], x1 + 1)
        y = int(round(coord))
        y1 = max(0, y - half)
        y2 = min(support_mask.shape[0], y + half + 1)
        band = support_mask[y1:y2, x1:x2]
    else:
        y1 = max(0, int(math.floor(min(start, end))))
        y2 = min(support_mask.shape[0], int(math.ceil(max(start, end))) + 1)
        if y2 <= y1:
            y2 = min(support_mask.shape[0], y1 + 1)
        x = int(round(coord))
        x1 = max(0, x - half)
        x2 = min(support_mask.shape[1], x + half + 1)
        band = support_mask[y1:y2, x1:x2]

    if band.size == 0:
        return 0.0
    return float(np.count_nonzero(band)) / float(band.size)


def _extract_skeleton_segments(
    skeleton: np.ndarray,
    distance: np.ndarray,
) -> list[dict[str, Any]]:
    pixels = [tuple(int(v) for v in point) for point in np.argwhere(skeleton)]
    if not pixels:
        return []

    pixel_set = set(pixels)
    neighbours: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for pixel in pixels:
        py, px = pixel
        adjacent: list[tuple[int, int]] = []
        for dy, dx in _NEIGHBOR_OFFSETS:
            neighbour = (py + dy, px + dx)
            if neighbour in pixel_set:
                adjacent.append(neighbour)
        neighbours[pixel] = adjacent

    nodes = {pixel for pixel in pixels if _is_graph_node(pixel, neighbours[pixel])}
    visited_edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    segments: list[dict[str, Any]] = []

    for node in sorted(nodes):
        for neighbour in neighbours[node]:
            edge_key = _edge_key(node, neighbour)
            if edge_key in visited_edges:
                continue
            path = _trace_path(node, neighbour, neighbours, nodes, visited_edges)
            if len(path) >= 2:
                segments.append(_segment_payload(path, distance))

    # Fallback for pure loops / residual skeleton pieces without explicit nodes.
    for pixel in pixels:
        for neighbour in neighbours[pixel]:
            edge_key = _edge_key(pixel, neighbour)
            if edge_key in visited_edges:
                continue
            loop = _trace_loop(pixel, neighbour, neighbours, visited_edges)
            if len(loop) >= 2:
                segments.extend(_split_loop_into_segments(loop, distance))

    return segments


def _trace_path(
    start: tuple[int, int],
    current: tuple[int, int],
    neighbours: dict[tuple[int, int], list[tuple[int, int]]],
    nodes: set[tuple[int, int]],
    visited_edges: set[tuple[tuple[int, int], tuple[int, int]]],
) -> list[tuple[int, int]]:
    path = [start, current]
    visited_edges.add(_edge_key(start, current))
    previous = start
    cursor = current

    while True:
        if cursor in nodes and cursor != start:
            break
        next_candidates = [candidate for candidate in neighbours[cursor] if candidate != previous]
        if not next_candidates:
            break
        nxt = next_candidates[0]
        edge_key = _edge_key(cursor, nxt)
        if edge_key in visited_edges:
            break
        visited_edges.add(edge_key)
        path.append(nxt)
        previous, cursor = cursor, nxt

    return path


def _trace_loop(
    start: tuple[int, int],
    current: tuple[int, int],
    neighbours: dict[tuple[int, int], list[tuple[int, int]]],
    visited_edges: set[tuple[tuple[int, int], tuple[int, int]]],
) -> list[tuple[int, int]]:
    path = [start, current]
    visited_edges.add(_edge_key(start, current))
    previous = start
    cursor = current

    while True:
        next_candidates = [candidate for candidate in neighbours[cursor] if candidate != previous]
        if not next_candidates:
            break

        nxt = next_candidates[0]
        edge_key = _edge_key(cursor, nxt)
        if edge_key in visited_edges:
            if nxt == start:
                path.append(start)
            break

        visited_edges.add(edge_key)
        path.append(nxt)
        previous, cursor = cursor, nxt

    return path


def _split_loop_into_segments(
    loop: list[tuple[int, int]],
    distance: np.ndarray,
) -> list[dict[str, Any]]:
    if len(loop) < 4:
        return [_segment_payload(loop, distance)]

    breakpoints = [0]
    for index in range(1, len(loop) - 1):
        prev = loop[index - 1]
        point = loop[index]
        nxt = loop[index + 1]
        if not _vectors_are_collinear(_vector(point, prev), _vector(point, nxt)):
            breakpoints.append(index)
    breakpoints.append(len(loop) - 1)

    if len(breakpoints) <= 2:
        return [_segment_payload(loop, distance)]

    segments: list[dict[str, Any]] = []
    for start_index, end_index in zip(breakpoints, breakpoints[1:]):
        path = loop[start_index : end_index + 1]
        if len(path) >= 2:
            segments.append(_segment_payload(path, distance))
    return segments


def _segment_payload(
    path: list[tuple[int, int]],
    distance: np.ndarray,
) -> dict[str, Any]:
    widths = [float(distance[point[0], point[1]] * 2.0) for point in path]
    mean_width_px = float(np.mean(widths)) if widths else 0.0
    return {
        "points": path,
        "mean_width_px": mean_width_px,
    }


def _segment_endpoints(path: list[tuple[int, int]]) -> tuple[float, float, float, float]:
    start = path[0]
    end = path[-1]
    return float(start[1]), float(start[0]), float(end[1]), float(end[0])


def _normalize_segment_orientation(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> tuple[str, float, float, float, float]:
    dx = float(x2 - x1)
    dy = float(y2 - y1)
    if not is_diagonal(dx, dy):
        if abs(dx) >= abs(dy):
            y_mid = (float(y1) + float(y2)) / 2.0
            return "horizontal", float(x1), y_mid, float(x2), y_mid
        x_mid = (float(x1) + float(x2)) / 2.0
        return "vertical", x_mid, float(y1), x_mid, float(y2)
    return "diagonal", float(x1), float(y1), float(x2), float(y2)


def _is_graph_node(pixel: tuple[int, int], neighbours: list[tuple[int, int]]) -> bool:
    if len(neighbours) != 2:
        return True
    v1 = _vector(pixel, neighbours[0])
    v2 = _vector(pixel, neighbours[1])
    return not _vectors_are_collinear(v1, v2)


def _vector(origin: tuple[int, int], target: tuple[int, int]) -> tuple[int, int]:
    return target[0] - origin[0], target[1] - origin[1]


def _vectors_are_collinear(v1: tuple[int, int], v2: tuple[int, int]) -> bool:
    return v1[0] == -v2[0] and v1[1] == -v2[1]


def _edge_key(
    point_a: tuple[int, int],
    point_b: tuple[int, int],
) -> tuple[tuple[int, int], tuple[int, int]]:
    return tuple(sorted((point_a, point_b)))


def _wall_polygon_from_segment(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    width_px: float,
) -> list[tuple[float, float]]:
    half = max((float(width_px) - 1.0) / 2.0, 1.0)
    dx = float(x2 - x1)
    dy = float(y2 - y1)
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return [
            (x1 - half, y1 - half),
            (x1 + half, y1 - half),
            (x1 + half, y1 + half),
            (x1 - half, y1 + half),
        ]

    ux = dx / length
    uy = dy / length
    cap = min(half, 1.5)
    x1 = x1 - (ux * cap)
    y1 = y1 - (uy * cap)
    x2 = x2 + (ux * cap)
    y2 = y2 + (uy * cap)
    px = -uy * half
    py = ux * half
    return [
        (x1 + px, y1 + py),
        (x2 + px, y2 + py),
        (x2 - px, y2 - py),
        (x1 - px, y1 - py),
    ]
