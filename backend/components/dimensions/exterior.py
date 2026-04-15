from __future__ import annotations

import cv2
import numpy as np

from .coord_transform import CoordTransform
from .formatting import _fmt_inches


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

    from ...measurement.flood_fill import _build_closed_mask

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
