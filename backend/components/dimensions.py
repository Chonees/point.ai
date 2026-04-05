"""
Simplified Pointe Homes dimensions + room label renderer.

Scope:
  - overall length of each exterior wall segment
  - exterior window centerline chains
  - manual room labels from 2D editor annotations
  - optional room size text (L x W) when scale can be calibrated

Intentionally excluded:
  - door-based exterior chains
  - solid-wall chains between openings
  - T-junction dimensions
  - interior dimension entities
  - structural/plumbing note dimensions
"""
from __future__ import annotations

import cv2
import numpy as np
from ezdxf.enums import TextEntityAlignment

from ..observability import log_event


DIM_TEXT_HEIGHT = 3.5
DIM_DOT_SIZE = 3.5
ROOM_NAME_HEIGHT = 7.4
ROOM_DIM_HEIGHT = 3.5
FIRST_CHAIN_OFFSET = 8.0
AUDIT_GEOMETRY_TOLERANCE_PX = 1.0
AUDIT_GENERATED_GAP_TOLERANCE_PX = 1.0


def _fmt_inches(value: float) -> str:
    feet = int(value) // 12
    remaining = round(value - feet * 12)
    if remaining == 12:
        feet += 1
        remaining = 0
    return f"{feet}'-{remaining}\""


def _audit_dim_status(*, geometry_closure_error_px: float, generated_gap_px: float) -> str:
    if geometry_closure_error_px <= AUDIT_GEOMETRY_TOLERANCE_PX:
        if generated_gap_px <= AUDIT_GENERATED_GAP_TOLERANCE_PX:
            return "pass"
        return "warn"
    return "fail"


def _ensure_dot_block(doc):
    if "_DOT" in doc.blocks:
        return
    blk = doc.blocks.new(name="_DOT")
    blk.add_lwpolyline([(-0.5, 0, 1.0), (0.5, 0, 1.0)], format="xyb", close=True)


def setup_dim_style(doc, dimlfac: float, plan_width_dxf: float = 1490.0) -> str:
    """Create a dimension style that matches the Seminole visual ratio."""
    name = "POINTAI_DIMS"
    if name in doc.dimstyles:
        doc.dimstyles.remove(name)
    _ensure_dot_block(doc)
    ds = doc.dimstyles.new(name)

    visual_ratio = 3.5 / 1300.0
    text_h = plan_width_dxf * visual_ratio
    dot_sz = text_h
    gap = text_h * 0.4

    ds.dxf.dimlfac = dimlfac
    ds.dxf.dimtxt = text_h
    ds.dxf.dimasz = dot_sz
    ds.dxf.dimgap = gap
    ds.dxf.dimexo = text_h * 0.15
    ds.dxf.dimexe = text_h * 0.15
    ds.dxf.dimdle = 0
    ds.dxf.dimtad = 1
    ds.dxf.dimjust = 0
    ds.dxf.dimtsz = 0
    ds.dxf.dimblk = "_DOT"
    ds.dxf.dimblk1 = "_DOT"
    ds.dxf.dimblk2 = "_DOT"
    ds.dxf.dimlunit = 4
    ds.dxf.dimdec = 0
    ds.dxf.dimzin = 0
    ds.dxf.dimclrd = 0
    ds.dxf.dimclre = 0
    ds.dxf.dimclrt = 0
    return name


def _ensure_layers(doc):
    for name, color in [("DIMS", 137), ("ROOM LBLS", 253)]:
        if name not in doc.layers:
            doc.layers.add(name, color=color)


class CoordTransform:
    def __init__(self, image_shape: tuple[int, int], transform: dict, scale_ipp: float):
        self.h, self.w = image_shape
        self.t_scale = float(transform.get("scale", 1.0) or 1.0)
        self.t_ox = float(transform.get("offset_x", 0.0) or 0.0)
        self.t_oy = float(transform.get("offset_y", 0.0) or 0.0)
        self.scale_ipp = float(scale_ipp)

    def to_dxf(self, ix: float, iy: float) -> tuple[float, float]:
        dx = ix * self.t_scale + self.t_ox
        dy = (self.h - iy) * self.t_scale + self.t_oy
        return dx, dy

    @property
    def dimlfac(self) -> float:
        if self.t_scale < 0.001:
            return 1.0
        return self.scale_ipp / self.t_scale


def _classify_annotations(annotations: list[dict]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {"wall": [], "door": [], "window": [], "label": []}
    for ann in annotations:
        ann_type = ann.get("type", "")
        if ann_type in result:
            result[ann_type].append(ann)
    return result


def _wall_orientation(wall: dict) -> str:
    dx = abs(float(wall["x2"]) - float(wall["x1"]))
    dy = abs(float(wall["y2"]) - float(wall["y1"]))
    return "H" if dx >= dy else "V"


def _wall_extent(wall: dict, orientation: str) -> tuple[float, float, float]:
    x1, y1, x2, y2 = float(wall["x1"]), float(wall["y1"]), float(wall["x2"]), float(wall["y2"])
    if orientation == "H":
        return min(x1, x2), max(x1, x2), (y1 + y2) / 2
    return min(y1, y2), max(y1, y2), (x1 + x2) / 2


def _opening_on_wall(opening: dict, wall: dict, orientation: str, tolerance: float = 8.0) -> bool:
    wall_start, wall_end, wall_coord = _wall_extent(wall, orientation)
    ox1, oy1, ox2, oy2 = float(opening["x1"]), float(opening["y1"]), float(opening["x2"]), float(opening["y2"])
    opening_mid_along = ((ox1 + ox2) / 2) if orientation == "H" else ((oy1 + oy2) / 2)
    opening_coord = ((oy1 + oy2) / 2) if orientation == "H" else ((ox1 + ox2) / 2)
    return (
        wall_start - tolerance <= opening_mid_along <= wall_end + tolerance
        and abs(opening_coord - wall_coord) < tolerance
    )


def _opening_centerline(opening: dict, orientation: str) -> float:
    if orientation == "H":
        return (float(opening["x1"]) + float(opening["x2"])) / 2
    return (float(opening["y1"]) + float(opening["y2"])) / 2


def _opening_cross_coord(opening: dict, orientation: str) -> float:
    if orientation == "H":
        return (float(opening["y1"]) + float(opening["y2"])) / 2
    return (float(opening["x1"]) + float(opening["x2"])) / 2


def _find_exterior_walls(walls: list[dict]) -> list[dict]:
    if not walls:
        return []

    horizontal = [wall for wall in walls if _wall_orientation(wall) == "H"]
    vertical = [wall for wall in walls if _wall_orientation(wall) == "V"]
    exterior: list[dict] = []

    if horizontal:
        coords = [_wall_extent(wall, "H")[2] for wall in horizontal]
        min_y, max_y = min(coords), max(coords)
        threshold = (max_y - min_y) * 0.1 if max_y > min_y else 20
        exterior.extend(wall for wall in horizontal if _wall_extent(wall, "H")[2] <= min_y + threshold)
        exterior.extend(wall for wall in horizontal if _wall_extent(wall, "H")[2] >= max_y - threshold)

    if vertical:
        coords = [_wall_extent(wall, "V")[2] for wall in vertical]
        min_x, max_x = min(coords), max(coords)
        threshold = (max_x - min_x) * 0.1 if max_x > min_x else 20
        exterior.extend(wall for wall in vertical if _wall_extent(wall, "V")[2] <= min_x + threshold)
        exterior.extend(wall for wall in vertical if _wall_extent(wall, "V")[2] >= max_x - threshold)

    return exterior


def _annotation_exterior_segments(walls: list[dict]) -> list[dict[str, float | str]]:
    segments: list[dict[str, float | str]] = []
    for wall in _find_exterior_walls(walls):
        orientation = _wall_orientation(wall)
        start, end, coord = _wall_extent(wall, orientation)
        if abs(end - start) < 3:
            continue
        segments.append(
            {
                "orientation": orientation,
                "start": float(start),
                "end": float(end),
                "coord": float(coord),
                "source": "annotation_extremes",
            }
        )
    return _merge_exterior_segments(segments, coord_tolerance=8.0, gap_tolerance=8.0)


def _merge_exterior_segments(
    segments: list[dict[str, float | str]],
    *,
    coord_tolerance: float = 3.0,
    gap_tolerance: float = 5.0,
) -> list[dict[str, float | str]]:
    merged: list[dict[str, float | str]] = []
    for orientation in ("H", "V"):
        oriented = [segment for segment in segments if segment["orientation"] == orientation]
        oriented.sort(key=lambda segment: (float(segment["coord"]), float(segment["start"])))

        current: dict[str, float | str] | None = None
        for segment in oriented:
            if current is None:
                current = dict(segment)
                continue

            same_line = abs(float(segment["coord"]) - float(current["coord"])) <= coord_tolerance
            touches = float(segment["start"]) <= float(current["end"]) + gap_tolerance
            same_source = segment.get("source") == current.get("source")
            if same_line and touches and same_source:
                current["start"] = min(float(current["start"]), float(segment["start"]))
                current["end"] = max(float(current["end"]), float(segment["end"]))
                current["coord"] = (float(current["coord"]) + float(segment["coord"])) / 2
                continue

            merged.append(current)
            current = dict(segment)

        if current is not None:
            merged.append(current)

    return merged


def _extract_exterior_segments_from_wall_mask(
    annotations: list[dict],
    wall_mask: np.ndarray | None,
    image_shape: tuple[int, int],
) -> list[dict[str, float | str]]:
    if wall_mask is None:
        return []

    from ..scale_calibrator import _build_closed_mask

    closed_mask = _build_closed_mask(annotations, wall_mask, image_shape)
    solid = (closed_mask > 0).astype(np.uint8) * 255
    free = np.where(solid == 0, 255, 0).astype(np.uint8)

    padded = cv2.copyMakeBorder(free, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=255)
    ff_mask = np.zeros((padded.shape[0] + 2, padded.shape[1] + 2), dtype=np.uint8)
    flooded = padded.copy()
    cv2.floodFill(flooded, ff_mask, (0, 0), 128)

    outside = flooded == 128
    enclosed_open = (padded == 255) & ~outside
    footprint = np.zeros_like(padded, dtype=np.uint8)
    footprint[(padded == 0) | enclosed_open] = 255
    footprint = footprint[1:-1, 1:-1]

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    footprint = cv2.morphologyEx(footprint, cv2.MORPH_CLOSE, kernel, iterations=1)

    contours, _ = cv2.findContours(footprint, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return []

    contour = max(contours, key=cv2.contourArea)
    perimeter = cv2.arcLength(contour, True)
    epsilon = max(2.0, perimeter * 0.002)
    approx = cv2.approxPolyDP(contour, epsilon, True)
    if len(approx) < 2:
        return []

    points = [(float(point[0][0]), float(point[0][1])) for point in approx]
    segments: list[dict[str, float | str]] = []
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        dx = x2 - x1
        dy = y2 - y1
        if abs(dx) < 3 and abs(dy) < 3:
            continue
        if abs(dx) >= abs(dy):
            orientation = "H"
            start, end = sorted((x1, x2))
            coord = (y1 + y2) / 2
        else:
            orientation = "V"
            start, end = sorted((y1, y2))
            coord = (x1 + x2) / 2
        if abs(end - start) < 3:
            continue
        segments.append(
            {
                "orientation": orientation,
                "start": float(start),
                "end": float(end),
                "coord": float(coord),
                "source": "wall_mask_footprint",
            }
        )

    return _merge_exterior_segments(segments)


def _building_centroid_from_segments(exterior_segments: list[dict[str, float | str]]) -> tuple[float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for segment in exterior_segments:
        orientation = str(segment["orientation"])
        start = float(segment["start"])
        end = float(segment["end"])
        coord = float(segment["coord"])
        if orientation == "H":
            xs.append((start + end) / 2)
            ys.append(coord)
        else:
            xs.append(coord)
            ys.append((start + end) / 2)
    return (sum(xs) / len(xs), sum(ys) / len(ys)) if xs else (0.0, 0.0)


def _assign_windows_to_segments(
    windows: list[dict],
    exterior_segments: list[dict[str, float | str]],
    *,
    coord_tolerance: float = 20.0,
    range_tolerance: float = 10.0,
) -> dict[int, list[dict]]:
    assigned: dict[int, list[dict]] = {index: [] for index in range(len(exterior_segments))}

    for window in windows:
        best_index = -1
        best_score = float("inf")
        for index, segment in enumerate(exterior_segments):
            orientation = str(segment["orientation"])
            start = float(segment["start"])
            end = float(segment["end"])
            coord = float(segment["coord"])
            center_along = _opening_centerline(window, orientation)
            center_coord = _opening_cross_coord(window, orientation)

            if not (start - range_tolerance <= center_along <= end + range_tolerance):
                continue

            coord_diff = abs(center_coord - coord)
            if coord_diff > coord_tolerance:
                continue

            score = coord_diff
            if _wall_orientation(window) != orientation:
                score += 4.0
            if score < best_score:
                best_index = index
                best_score = score

        if best_index >= 0:
            assigned.setdefault(best_index, []).append(window)

    return assigned


def _building_centroid_px(walls: list[dict]) -> tuple[float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for wall in walls:
        xs.append((float(wall["x1"]) + float(wall["x2"])) / 2)
        ys.append((float(wall["y1"]) + float(wall["y2"])) / 2)
    return (sum(xs) / len(xs), sum(ys) / len(ys)) if xs else (0.0, 0.0)


def _plan_width_dxf(ct: CoordTransform, walls: list[dict]) -> float:
    if not walls:
        return 1490.0
    xs: list[float] = []
    for wall in walls:
        xs.extend([float(wall["x1"]), float(wall["x2"])])
    return (max(xs) - min(xs)) * ct.t_scale


def _label_sizes(plan_width_dxf: float) -> tuple[float, float, float]:
    name_h = plan_width_dxf * (ROOM_NAME_HEIGHT / 1300.0)
    dim_h = plan_width_dxf * (ROOM_DIM_HEIGHT / 1300.0)
    spacing = plan_width_dxf * (5.0 / 1300.0)
    return name_h, dim_h, spacing


def _label_room_metrics(
    annotations: list[dict],
    wall_mask,
    image_shape: tuple[int, int],
    label: dict,
    scale_ipp: float,
    room_context: dict[str, object] | None = None,
) -> str | None:
    from ..scale_calibrator import flood_fill_room_region, inches_to_feet_inches

    if wall_mask is None or scale_ipp <= 0:
        log_event(
            "room_metric_skipped",
            room_name=label.get("roomName"),
            reason="missing_wall_mask_or_scale",
            scale_ipp=scale_ipp,
        )
        return None

    region = room_context["region"] if room_context and room_context.get("region") is not None else flood_fill_room_region(
        annotations,
        wall_mask,
        image_shape,
        int(float(label["x1"])),
        int(float(label["y1"])),
    )
    if not region:
        log_event(
            "room_metric_skipped",
            room_name=label.get("roomName"),
            reason="room_region_not_found",
        )
        return None

    room_mask = region["mask"]
    seed_x, seed_y = region["seed"]
    bbox_x1, bbox_y1, bbox_x2, bbox_y2 = region["bbox"]
    sample_band = max(12, min(30, int(min(bbox_x2 - bbox_x1, bbox_y2 - bbox_y1) * 0.25)))
    horizontal_span = _best_local_seedline_span(
        room_mask,
        seed_x=seed_x,
        seed_y=seed_y,
        axis="H",
        band=sample_band,
    )
    vertical_span = _best_local_seedline_span(
        room_mask,
        seed_x=seed_x,
        seed_y=seed_y,
        axis="V",
        band=sample_band,
    )
    if horizontal_span is None or vertical_span is None:
        log_event(
            "room_metric_skipped",
            room_name=label.get("roomName"),
            reason="seedline_span_not_found",
            seed={"x": seed_x, "y": seed_y},
            sample_band=sample_band,
        )
        return None

    hx1, hx2 = horizontal_span
    vy1, vy2 = vertical_span
    room_w_in = abs(hx2 - hx1) * scale_ipp
    room_h_in = abs(vy2 - vy1) * scale_ipp
    if room_w_in < 1 or room_h_in < 1:
        log_event(
            "room_metric_skipped",
            room_name=label.get("roomName"),
            reason="seedline_span_too_small",
            horizontal_span={"x1": hx1, "x2": hx2},
            vertical_span={"y1": vy1, "y2": vy2},
            room_w_in=round(room_w_in, 4),
            room_h_in=round(room_h_in, 4),
        )
        return None

    length_in = max(room_w_in, room_h_in)
    width_in = min(room_w_in, room_h_in)
    dims_text = f"{inches_to_feet_inches(length_in)} x {inches_to_feet_inches(width_in)}"
    log_event(
        "room_metric_computed",
        room_name=label.get("roomName"),
        measurement_method="seedline_face_to_face",
        seed={"x": seed_x, "y": seed_y},
        sample_band=sample_band,
        horizontal_span={"x1": hx1, "x2": hx2},
        vertical_span={"y1": vy1, "y2": vy2},
        room_w_in=round(room_w_in, 4),
        room_h_in=round(room_h_in, 4),
        dims_text=dims_text,
        scale_ipp=round(scale_ipp, 6),
    )
    return dims_text


def _span_containing_seed(line: np.ndarray, seed_index: int) -> tuple[int, int] | None:
    if seed_index < 0 or seed_index >= len(line) or not bool(line[seed_index]):
        return None

    start = int(seed_index)
    end = int(seed_index)
    while start > 0 and bool(line[start - 1]):
        start -= 1
    while end + 1 < len(line) and bool(line[end + 1]):
        end += 1
    return start, end


def _best_local_seedline_span(
    room_mask: np.ndarray,
    *,
    seed_x: int,
    seed_y: int,
    axis: str,
    band: int,
) -> tuple[int, int] | None:
    best_span: tuple[int, int] | None = None
    best_length = -1
    best_distance = float("inf")

    if axis == "H":
        start = max(0, seed_y - band)
        end = min(room_mask.shape[0] - 1, seed_y + band)
        for y in range(start, end + 1):
            span = _span_containing_seed(room_mask[y, :], seed_x)
            if span is None:
                continue
            length = span[1] - span[0]
            distance = abs(y - seed_y)
            if length > best_length or (length == best_length and distance < best_distance):
                best_span = span
                best_length = length
                best_distance = distance
        return best_span

    start = max(0, seed_x - band)
    end = min(room_mask.shape[1] - 1, seed_x + band)
    for x in range(start, end + 1):
        span = _span_containing_seed(room_mask[:, x], seed_y)
        if span is None:
            continue
        length = span[1] - span[0]
        distance = abs(x - seed_x)
        if length > best_length or (length == best_length and distance < best_distance):
            best_span = span
            best_length = length
            best_distance = distance
    return best_span


def _render_manual_room_labels(
    msp,
    ct: CoordTransform,
    annotations: list[dict],
    labels: list[dict],
    wall_mask,
    image_shape: tuple[int, int],
    plan_width_dxf: float,
    scale_ipp: float,
    measurement_context: dict[str, object] | None = None,
) -> dict[str, int]:
    counts = {"room_labels": 0, "room_size_labels": 0, "sqft_labels": 0}
    if not labels:
        return counts

    name_h, dim_h, label_spacing = _label_sizes(plan_width_dxf)
    room_map = {}
    calibration_mode = None
    if measurement_context:
        calibration_mode = str(measurement_context.get("calibration_mode") or "")
        room_map = measurement_context.get("room_analysis", {}).get("rooms_by_label_id", {}) or {}

    for label in labels:
        room_name = str(label.get("roomName", "ROOM") or "ROOM").upper()
        room_context = room_map.get(id(label))
        sqft_source = "label"
        raw_sqft = label.get("sqft")
        sqft_value = None
        if raw_sqft not in (None, ""):
            sqft_value = float(raw_sqft)
        if calibration_mode == "total_area" and room_context and room_context.get("computed_sqft") is not None:
            sqft_source = "computed_total_area"
            sqft_value = float(room_context["computed_sqft"])
        lx, ly = float(label["x1"]), float(label["y1"])
        dx, dy = ct.to_dxf(lx, ly)

        name_text = msp.add_text(room_name, dxfattribs={"layer": "ROOM LBLS", "height": name_h})
        name_text.set_placement((dx, dy + label_spacing), align=TextEntityAlignment.MIDDLE_CENTER)
        counts["room_labels"] += 1
        log_event(
            "room_label_added",
            room_name=room_name,
            anchor_px={"x": round(lx, 4), "y": round(ly, 4)},
            anchor_dxf={"x": round(dx, 4), "y": round(dy, 4)},
            sqft=round(sqft_value, 4) if sqft_value is not None else None,
            sqft_source=sqft_source if sqft_value is not None else None,
        )

        dims_text = _label_room_metrics(annotations, wall_mask, image_shape, label, scale_ipp, room_context=room_context)
        if dims_text:
            dims_label = msp.add_text(dims_text, dxfattribs={"layer": "ROOM LBLS", "height": dim_h})
            dims_label.set_placement((dx, dy - label_spacing * 0.3), align=TextEntityAlignment.MIDDLE_CENTER)
            counts["room_size_labels"] += 1
            log_event("room_size_label_added", room_name=room_name, dims_text=dims_text)

        if sqft_value is not None:
            sqft_y = dy - (label_spacing * 1.2 if dims_text else label_spacing * 0.3)
            sqft_text = msp.add_text(
                f"{int(round(float(sqft_value)))} SQ FT",
                dxfattribs={"layer": "ROOM LBLS", "height": dim_h},
            )
            sqft_text.set_placement((dx, sqft_y), align=TextEntityAlignment.MIDDLE_CENTER)
            counts["sqft_labels"] += 1
            log_event(
                "room_sqft_label_added",
                room_name=room_name,
                sqft=int(round(float(sqft_value))),
                sqft_source=sqft_source,
                duplicate_of_index=room_context.get("duplicate_of_index") if room_context else None,
                overlap_area_px=room_context.get("overlap_area_px") if room_context else None,
            )

    return counts


def generate_all_dimensions(
    doc,
    msp,
    annotations: list[dict],
    scale_ipp: float,
    image_shape: tuple[int, int],
    transform: dict,
    wall_mask=None,
    render_dimensions: bool = True,
    measurement_context: dict[str, object] | None = None,
) -> dict[str, int]:
    _ensure_layers(doc)
    ct = CoordTransform(image_shape, transform, scale_ipp)
    classified = _classify_annotations(annotations)
    plan_width_dxf = _plan_width_dxf(ct, classified["wall"])
    log_event(
        "dims_generation_start",
        annotation_counts={key: len(value) for key, value in classified.items()},
        render_dimensions=render_dimensions,
        scale_ipp=round(scale_ipp, 6),
        plan_width_dxf=round(plan_width_dxf, 4),
        calibration_mode=measurement_context.get("calibration_mode") if measurement_context else None,
    )

    counts = {
        "window_center_dims": 0,
        "exterior_wall_dims": 0,
        "room_labels": 0,
        "room_size_labels": 0,
        "sqft_labels": 0,
    }
    audit_summary = {
        "window_chain_pass": 0,
        "window_chain_warn": 0,
        "window_chain_fail": 0,
        "windowless_wall_totals": 0,
        "audited_window_chains": 0,
        "max_generated_gap_px": 0.0,
        "max_generated_gap_in": 0.0,
        "max_geometry_closure_error_px": 0.0,
        "max_geometry_closure_error_in": 0.0,
        "overlapping_label_count": 0,
        "duplicated_region_count": 0,
    }
    if measurement_context:
        room_analysis = measurement_context.get("room_analysis", {})
        audit_summary["overlapping_label_count"] = int(room_analysis.get("overlapping_label_count", 0))
        audit_summary["duplicated_region_count"] = int(room_analysis.get("duplicated_region_count", 0))
    counts.update(
        _render_manual_room_labels(
            msp,
            ct,
            annotations,
            classified["label"],
            wall_mask,
            image_shape,
            plan_width_dxf,
            scale_ipp if render_dimensions else 0.0,
            measurement_context=measurement_context,
        )
    )

    if not render_dimensions or not classified["wall"]:
        log_event(
            "dims_generation_done",
            reason="labels_only" if not render_dimensions else "no_walls",
            counts=counts,
        )
        return counts

    dimstyle = setup_dim_style(doc, ct.dimlfac, plan_width_dxf)
    exterior_segments = _extract_exterior_segments_from_wall_mask(annotations, wall_mask, image_shape)
    if not exterior_segments:
        exterior_segments = _annotation_exterior_segments(classified["wall"])
    centroid_px = _building_centroid_from_segments(exterior_segments) or _building_centroid_px(classified["wall"])
    windows_by_segment = _assign_windows_to_segments(classified["window"], exterior_segments)
    window_offset = plan_width_dxf * (FIRST_CHAIN_OFFSET / 1300.0)
    wall_offset = window_offset * 2
    log_event(
        "dims_exterior_setup",
        exterior_wall_count=len(exterior_segments),
        window_offset_dxf=round(window_offset, 4),
        wall_offset_dxf=round(wall_offset, 4),
        centroid_px={"x": round(centroid_px[0], 4), "y": round(centroid_px[1], 4)},
        segment_sources=sorted({str(segment["source"]) for segment in exterior_segments}),
    )

    for index, segment in enumerate(exterior_segments):
        orientation = str(segment["orientation"])
        wall_start = float(segment["start"])
        wall_end = float(segment["end"])
        wall_coord = float(segment["coord"])

        wall_length_px = abs(wall_end - wall_start)
        wall_length_in = wall_length_px * scale_ipp

        if orientation == "H":
            outward = -1 if wall_coord > centroid_px[1] else 1
        else:
            outward = 1 if wall_coord > centroid_px[0] else -1

        _add_dim_along_wall(
            msp,
            ct,
            orientation,
            wall_coord,
            wall_start,
            wall_end,
            outward,
            wall_offset,
            dimstyle,
            _fmt_inches(wall_length_in),
        )
        counts["exterior_wall_dims"] += 1
        log_event(
            "exterior_wall_dim_added",
            source=segment["source"],
            orientation=orientation,
            wall_coord_px=round(wall_coord, 4),
            start_px=round(wall_start, 4),
            end_px=round(wall_end, 4),
            wall_length_px=round(wall_length_px, 4),
            wall_length_in=round(wall_length_in, 4),
            wall_length_arch=_fmt_inches(wall_length_in),
        )

        windows_on_wall = windows_by_segment.get(index, [])
        log_event(
            "exterior_wall_window_scan",
            source=segment["source"],
            orientation=orientation,
            wall_coord_px=round(wall_coord, 4),
            window_count=len(windows_on_wall),
        )
        if not windows_on_wall:
            audit_summary["windowless_wall_totals"] += 1
            continue

        chain_points = [wall_start]
        chain_points.extend(sorted(_opening_centerline(window, orientation) for window in windows_on_wall))
        chain_points.append(wall_end)
        log_event(
            "window_center_chain_points",
            orientation=orientation,
            wall_coord_px=round(wall_coord, 4),
            chain_points=[round(point, 4) for point in chain_points],
        )

        generated_chain_sum_px = 0.0
        generated_chain_sum_in = 0.0
        skipped_chain_gap_px = 0.0
        skipped_chain_gap_in = 0.0
        generated_segment_count = 0
        for i in range(len(chain_points) - 1):
            p1 = chain_points[i]
            p2 = chain_points[i + 1]
            segment_px = abs(p2 - p1)
            segment_in = segment_px * scale_ipp
            if segment_px < 2:
                skipped_chain_gap_px += segment_px
                skipped_chain_gap_in += segment_in
                continue
            generated_chain_sum_px += segment_px
            generated_chain_sum_in += segment_in
            generated_segment_count += 1
            _add_dim_along_wall(
                msp,
                ct,
                orientation,
                wall_coord,
                p1,
                p2,
                outward,
                window_offset,
                dimstyle,
                _fmt_inches(segment_in),
            )
            counts["window_center_dims"] += 1
            log_event(
                "window_center_dim_added",
                orientation=orientation,
                wall_coord_px=round(wall_coord, 4),
                start_px=round(p1, 4),
                end_px=round(p2, 4),
                segment_px=round(segment_px, 4),
                segment_in=round(segment_in, 4),
                segment_arch=_fmt_inches(segment_in),
            )

        geometry_closure_error_px = abs(wall_length_px - (generated_chain_sum_px + skipped_chain_gap_px))
        geometry_closure_error_in = abs(wall_length_in - (generated_chain_sum_in + skipped_chain_gap_in))
        generated_gap_px = abs(wall_length_px - generated_chain_sum_px)
        generated_gap_in = abs(wall_length_in - generated_chain_sum_in)
        audit_status = _audit_dim_status(
            geometry_closure_error_px=geometry_closure_error_px,
            generated_gap_px=generated_gap_px,
        )
        audit_summary["audited_window_chains"] += 1
        audit_summary[f"window_chain_{audit_status}"] += 1
        audit_summary["max_generated_gap_px"] = max(audit_summary["max_generated_gap_px"], generated_gap_px)
        audit_summary["max_generated_gap_in"] = max(audit_summary["max_generated_gap_in"], generated_gap_in)
        audit_summary["max_geometry_closure_error_px"] = max(
            audit_summary["max_geometry_closure_error_px"],
            geometry_closure_error_px,
        )
        audit_summary["max_geometry_closure_error_in"] = max(
            audit_summary["max_geometry_closure_error_in"],
            geometry_closure_error_in,
        )
        log_event(
            "window_chain_audit",
            source=segment["source"],
            orientation=orientation,
            wall_coord_px=round(wall_coord, 4),
            wall_length_arch=_fmt_inches(wall_length_in),
            generated_segment_count=generated_segment_count,
            generated_chain_sum_arch=_fmt_inches(generated_chain_sum_in),
            skipped_gap_arch=_fmt_inches(skipped_chain_gap_in),
            generated_gap_arch=_fmt_inches(generated_gap_in),
            generated_gap_px=round(generated_gap_px, 4),
            geometry_closure_error_px=round(geometry_closure_error_px, 4),
            geometry_closure_error_in=round(geometry_closure_error_in, 4),
            status=audit_status,
        )

    log_event(
        "dims_audit_summary",
        audited_window_chains=audit_summary["audited_window_chains"],
        window_chain_pass=audit_summary["window_chain_pass"],
        window_chain_warn=audit_summary["window_chain_warn"],
        window_chain_fail=audit_summary["window_chain_fail"],
        windowless_wall_totals=audit_summary["windowless_wall_totals"],
        max_generated_gap_px=round(audit_summary["max_generated_gap_px"], 4),
        max_generated_gap_in=round(audit_summary["max_generated_gap_in"], 4),
        max_geometry_closure_error_px=round(audit_summary["max_geometry_closure_error_px"], 4),
        max_geometry_closure_error_in=round(audit_summary["max_geometry_closure_error_in"], 4),
        overlapping_label_count=audit_summary["overlapping_label_count"],
        duplicated_region_count=audit_summary["duplicated_region_count"],
        calibration_mode=measurement_context.get("calibration_mode") if measurement_context else None,
    )
    log_event("dims_generation_done", reason="full", counts=counts)
    return counts


def _add_dim_along_wall(
    msp,
    ct: CoordTransform,
    orientation: str,
    wall_coord_px: float,
    p1_px: float,
    p2_px: float,
    outward: int,
    offset_dxf: float,
    dimstyle: str,
    dim_text: str,
):
    if orientation == "H":
        dp1 = ct.to_dxf(p1_px, wall_coord_px)
        dp2 = ct.to_dxf(p2_px, wall_coord_px)
        wall_dxf_y = ct.to_dxf(0, wall_coord_px)[1]
        dim_line_y = wall_dxf_y + outward * offset_dxf
        try:
            dim = msp.add_linear_dim(
                base=(0, dim_line_y),
                p1=dp1,
                p2=dp2,
                text=dim_text,
                angle=0,
                dimstyle=dimstyle,
                dxfattribs={"layer": "DIMS"},
            )
            dim.render()
        except Exception:
            pass
    else:
        dp1 = ct.to_dxf(wall_coord_px, p1_px)
        dp2 = ct.to_dxf(wall_coord_px, p2_px)
        wall_dxf_x = ct.to_dxf(wall_coord_px, 0)[0]
        dim_line_x = wall_dxf_x + outward * offset_dxf
        try:
            dim = msp.add_linear_dim(
                base=(dim_line_x, 0),
                p1=dp1,
                p2=dp2,
                text=dim_text,
                angle=90,
                dimstyle=dimstyle,
                dxfattribs={"layer": "DIMS"},
            )
            dim.render()
        except Exception:
            pass
