from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from ..coordinate_space import image_point_to_dxf_space


def _binary_mask_bbox(mask: np.ndarray) -> dict[str, int] | None:
    points = cv2.findNonZero(mask)
    if points is None:
        return None
    x, y, w, h = cv2.boundingRect(points)
    return {
        "x1": int(x),
        "y1": int(y),
        "x2": int(x + w),
        "y2": int(y + h),
    }


def _summarize_binary_mask(mask: np.ndarray) -> dict[str, Any]:
    binary = (mask > 0).astype(np.uint8)
    component_count = 0
    largest_component_area = 0
    if binary.size > 0:
        num_components, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        component_count = max(0, int(num_components - 1))
        if component_count > 0:
            largest_component_area = int(stats[1:, cv2.CC_STAT_AREA].max())

    nonzero_pixel_count = int(np.count_nonzero(binary))
    return {
        "shape": {"height": int(binary.shape[0]), "width": int(binary.shape[1])},
        "nonzero_pixel_count": nonzero_pixel_count,
        "coverage_ratio": float(nonzero_pixel_count / float(binary.size)) if binary.size else 0.0,
        "component_count": component_count,
        "largest_component_area": largest_component_area,
        "bbox": _binary_mask_bbox(binary),
    }


def _rect_bounds_dict(rect: list[float]) -> dict[str, float]:
    x1, y1, x2, y2 = [float(value) for value in rect]
    return {
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
    }


def _rect_stage_entry(
    rect: list[float],
    *,
    orientation: str,
    rect_id: str,
) -> dict[str, Any]:
    x1, y1, x2, y2 = [float(value) for value in rect]
    return {
        "id": rect_id,
        "orientation": orientation,
        "bounds": _rect_bounds_dict(rect),
        "length": float(max(abs(x2 - x1), abs(y2 - y1))),
        "thickness": float(min(abs(x2 - x1), abs(y2 - y1))),
    }


def _component_rect_to_dxf(
    *,
    x: int,
    y: int,
    cw: int,
    ch: int,
    orientation: str,
    image_shape: tuple[int, int],
    transform: dict[str, float],
    wall_thin: float,
) -> list[float]:
    if orientation == "horizontal":
        trim = ch * (1 - wall_thin) / 2
        y_s = y + trim
        ch_s = ch - 2 * trim
        x1d, y1d = image_point_to_dxf_space(x, y_s + ch_s, image_shape=image_shape, transform=transform)
        x2d, y2d = image_point_to_dxf_space(x + cw, y_s, image_shape=image_shape, transform=transform)
    else:
        trim = cw * (1 - wall_thin) / 2
        x_s = x + trim
        cw_s = cw - 2 * trim
        x1d, y1d = image_point_to_dxf_space(x_s, y + ch, image_shape=image_shape, transform=transform)
        x2d, y2d = image_point_to_dxf_space(x_s + cw_s, y, image_shape=image_shape, transform=transform)
    return [min(x1d, x2d), min(y1d, y2d), max(x1d, x2d), max(y1d, y2d)]


def _component_has_perpendicular_support(
    support_mask: np.ndarray,
    *,
    x: int,
    y: int,
    cw: int,
    ch: int,
    orientation: str,
) -> bool:
    if support_mask.size == 0:
        return False

    height, width = support_mask.shape
    if orientation == "horizontal":
        pad_x = max(2, int(round(ch * 1.5)))
        pad_y = max(2, int(round(ch * 1.5)))
        left = support_mask[
            max(0, y - pad_y):min(height, y + ch + pad_y),
            max(0, x - pad_x):min(width, x + pad_x),
        ]
        right = support_mask[
            max(0, y - pad_y):min(height, y + ch + pad_y),
            max(0, x + cw - pad_x):min(width, x + cw + pad_x),
        ]
        return bool(np.count_nonzero(left) > 0 or np.count_nonzero(right) > 0)

    pad_x = max(2, int(round(cw * 1.5)))
    pad_y = max(2, int(round(cw * 1.5)))
    top = support_mask[
        max(0, y - pad_y):min(height, y + pad_y),
        max(0, x - pad_x):min(width, x + cw + pad_x),
    ]
    bottom = support_mask[
        max(0, y + ch - pad_y):min(height, y + ch + pad_y),
        max(0, x - pad_x):min(width, x + cw + pad_x),
    ]
    return bool(np.count_nonzero(top) > 0 or np.count_nonzero(bottom) > 0)


def _contiguous_segments(indices: np.ndarray) -> list[tuple[int, int]]:
    if indices.size == 0:
        return []

    segments: list[tuple[int, int]] = []
    start = int(indices[0])
    previous = int(indices[0])
    for raw in indices[1:]:
        current = int(raw)
        if current != previous + 1:
            segments.append((start, previous))
            start = current
        previous = current
    segments.append((start, previous))
    return segments


def _runs_to_branch_groups(
    runs: list[dict[str, int]],
    *,
    orientation: str,
) -> list[dict[str, int]]:
    if not runs:
        return []

    if orientation == "horizontal":
        ordered = sorted(runs, key=lambda run: (run["y1"], run["x1"]))
    else:
        ordered = sorted(runs, key=lambda run: (run["x1"], run["y1"]))

    groups: list[dict[str, int]] = []
    for run in ordered:
        if not groups:
            groups.append(dict(run))
            continue

        last = groups[-1]
        if orientation == "horizontal":
            last_span = max(1, last["x2"] - last["x1"])
            run_span = max(1, run["x2"] - run["x1"])
            width_ratio = max(last_span, run_span) / min(last_span, run_span)
            same_cluster = (
                run["y1"] <= last["y2"]
                and run["x1"] <= last["x2"] + 2
                and run["x2"] >= last["x1"] - 2
                and width_ratio <= 1.6
            )
        else:
            last_span = max(1, last["y2"] - last["y1"])
            run_span = max(1, run["y2"] - run["y1"])
            height_ratio = max(last_span, run_span) / min(last_span, run_span)
            same_cluster = (
                run["x1"] <= last["x2"]
                and run["y1"] <= last["y2"] + 2
                and run["y2"] >= last["y1"] - 2
                and height_ratio <= 1.6
            )

        if not same_cluster:
            groups.append(dict(run))
            continue

        last["x1"] = min(last["x1"], run["x1"])
        last["y1"] = min(last["y1"], run["y1"])
        last["x2"] = max(last["x2"], run["x2"])
        last["y2"] = max(last["y2"], run["y2"])

    return groups


def _extract_oriented_region_components(
    source_mask: np.ndarray,
    *,
    orientation: str,
    min_len: int,
    min_thickness: int,
    min_aspect_ratio: float,
    image_shape: tuple[int, int],
    transform: dict[str, float],
    wall_thin: float,
    support_mask: np.ndarray | None = None,
) -> tuple[np.ndarray, list[list[float]], list[dict[str, Any]]]:
    if orientation == "horizontal":
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(1, int(min_len)), 1))
    else:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(1, int(min_len))))

    oriented_mask = cv2.morphologyEx(source_mask, cv2.MORPH_OPEN, kernel)
    rects: list[list[float]] = []
    components: list[dict[str, Any]] = []

    runs: list[dict[str, int]] = []
    if orientation == "horizontal":
        for row in range(oriented_mask.shape[0]):
            for seg_start, seg_end in _contiguous_segments(np.flatnonzero(oriented_mask[row] > 0)):
                run_len = seg_end - seg_start + 1
                if run_len < min_len:
                    continue
                runs.append({"x1": int(seg_start), "y1": int(row), "x2": int(seg_end + 1), "y2": int(row + 1)})
    else:
        for col in range(oriented_mask.shape[1]):
            for seg_start, seg_end in _contiguous_segments(np.flatnonzero(oriented_mask[:, col] > 0)):
                run_len = seg_end - seg_start + 1
                if run_len < min_len:
                    continue
                runs.append({"x1": int(col), "y1": int(seg_start), "x2": int(col + 1), "y2": int(seg_end + 1)})

    for index, group in enumerate(_runs_to_branch_groups(runs, orientation=orientation), start=1):
        x = int(group["x1"])
        y = int(group["y1"])
        cw = int(group["x2"] - group["x1"])
        ch = int(group["y2"] - group["y1"])
        length = cw if orientation == "horizontal" else ch
        thickness = ch if orientation == "horizontal" else cw
        component_entry = {
            "component_index": int(index),
            "orientation": orientation,
            "image_bounds": {"x1": x, "y1": y, "x2": x + cw, "y2": y + ch},
            "pixel_width": cw,
            "pixel_height": ch,
            "accepted": False,
        }

        if length < min_len or thickness < min_thickness:
            component_entry["skip_reason"] = "too_short"
            components.append(component_entry)
            continue

        if thickness > 0 and (length / thickness) < min_aspect_ratio:
            component_entry["skip_reason"] = "insufficient_aspect_ratio"
            components.append(component_entry)
            continue

        if support_mask is not None and not _component_has_perpendicular_support(
            support_mask,
            x=x,
            y=y,
            cw=cw,
            ch=ch,
            orientation=orientation,
        ):
            component_entry["skip_reason"] = "missing_perpendicular_support"
            components.append(component_entry)
            continue

        rect = _component_rect_to_dxf(
            x=x,
            y=y,
            cw=cw,
            ch=ch,
            orientation=orientation,
            image_shape=image_shape,
            transform=transform,
            wall_thin=wall_thin,
        )
        rects.append(rect)
        component_entry["accepted"] = True
        component_entry["dxf_bounds"] = _rect_bounds_dict(rect)
        component_entry["dxf_length"] = float(max(rect[2] - rect[0], rect[3] - rect[1]))
        component_entry["dxf_thickness"] = float(min(rect[2] - rect[0], rect[3] - rect[1]))
        components.append(component_entry)

    return oriented_mask, rects, components


def _extract_short_branch_components(
    source_mask: np.ndarray,
    *,
    orientation: str,
    long_min_len: int,
    branch_min_len: int,
    min_thickness: int,
    min_aspect_ratio: float,
    image_shape: tuple[int, int],
    transform: dict[str, float],
    wall_thin: float,
    support_mask: np.ndarray | None = None,
) -> tuple[np.ndarray, list[list[float]], list[dict[str, Any]]]:
    if orientation == "horizontal":
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(1, int(branch_min_len)), 1))
    else:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(1, int(branch_min_len))))

    oriented_mask = cv2.morphologyEx(source_mask, cv2.MORPH_OPEN, kernel)
    num_components, labels, stats, _ = cv2.connectedComponentsWithStats(oriented_mask, connectivity=8)
    rects: list[list[float]] = []
    components: list[dict[str, Any]] = []
    min_protrusion = max(2, int(np.ceil(branch_min_len / 2.0)))

    for i in range(1, num_components):
        x = int(stats[i, cv2.CC_STAT_LEFT])
        y = int(stats[i, cv2.CC_STAT_TOP])
        cw = int(stats[i, cv2.CC_STAT_WIDTH])
        ch = int(stats[i, cv2.CC_STAT_HEIGHT])
        component_mask = labels[y:y + ch, x:x + cw] == i
        support_slice = None if support_mask is None else support_mask[y:y + ch, x:x + cw]
        runs: list[dict[str, int]] = []

        if orientation == "horizontal":
            for row in range(component_mask.shape[0]):
                segments = _contiguous_segments(np.flatnonzero(component_mask[row]))
                if not segments:
                    continue
                support_row = None if support_slice is None else (support_slice[row] > 0)
                for seg_start, seg_end in segments:
                    run_len = seg_end - seg_start + 1
                    if run_len < branch_min_len or run_len >= long_min_len or support_row is None:
                        continue
                    support_indices = np.flatnonzero(support_row[seg_start:seg_end + 1])
                    if support_indices.size == 0:
                        continue
                    left_protrusion = int(support_indices[0])
                    right_protrusion = int(run_len - (support_indices[-1] + 1))
                    if max(left_protrusion, right_protrusion) < min_protrusion:
                        continue
                    runs.append({"x1": x + seg_start, "y1": y + row, "x2": x + seg_end + 1, "y2": y + row + 1})
        else:
            for col in range(component_mask.shape[1]):
                segments = _contiguous_segments(np.flatnonzero(component_mask[:, col]))
                if not segments:
                    continue
                support_col = None if support_slice is None else (support_slice[:, col] > 0)
                for seg_start, seg_end in segments:
                    run_len = seg_end - seg_start + 1
                    if run_len < branch_min_len or run_len >= long_min_len or support_col is None:
                        continue
                    support_indices = np.flatnonzero(support_col[seg_start:seg_end + 1])
                    if support_indices.size == 0:
                        continue
                    top_protrusion = int(support_indices[0])
                    bottom_protrusion = int(run_len - (support_indices[-1] + 1))
                    if max(top_protrusion, bottom_protrusion) < min_protrusion:
                        continue
                    runs.append({"x1": x + col, "y1": y + seg_start, "x2": x + col + 1, "y2": y + seg_end + 1})

        component_entry = {
            "component_index": int(i),
            "orientation": orientation,
            "image_bounds": {"x1": x, "y1": y, "x2": x + cw, "y2": y + ch},
            "pixel_width": cw,
            "pixel_height": ch,
            "accepted": False,
            "candidate_run_count": len(runs),
        }
        if not runs:
            component_entry["skip_reason"] = "no_branch_runs"
            components.append(component_entry)
            continue

        groups = _runs_to_branch_groups(runs, orientation=orientation)
        component_entry["candidate_group_count"] = len(groups)
        accepted_groups: list[dict[str, Any]] = []

        for group in groups:
            gx1 = int(group["x1"])
            gy1 = int(group["y1"])
            gx2 = int(group["x2"])
            gy2 = int(group["y2"])
            length = (gx2 - gx1) if orientation == "horizontal" else (gy2 - gy1)
            thickness = (gy2 - gy1) if orientation == "horizontal" else (gx2 - gx1)
            if length < branch_min_len or thickness < min_thickness:
                continue
            if thickness > 0 and (length / thickness) < min_aspect_ratio:
                continue
            if support_mask is not None and not _component_has_perpendicular_support(
                support_mask,
                x=gx1,
                y=gy1,
                cw=max(1, gx2 - gx1),
                ch=max(1, gy2 - gy1),
                orientation=orientation,
            ):
                continue

            rect = _component_rect_to_dxf(
                x=gx1,
                y=gy1,
                cw=max(1, gx2 - gx1),
                ch=max(1, gy2 - gy1),
                orientation=orientation,
                image_shape=image_shape,
                transform=transform,
                wall_thin=wall_thin,
            )
            rects.append(rect)
            accepted_groups.append(
                {
                    "image_bounds": {"x1": gx1, "y1": gy1, "x2": gx2, "y2": gy2},
                    "dxf_bounds": _rect_bounds_dict(rect),
                    "length": float(length),
                    "thickness": float(thickness),
                }
            )

        if not accepted_groups:
            component_entry["skip_reason"] = "no_group_passed_filters"
            components.append(component_entry)
            continue

        component_entry["accepted"] = True
        component_entry["accepted_groups"] = accepted_groups
        components.append(component_entry)

    return oriented_mask, rects, components


def _collect_mitunet_region_rectangles(
    cleaned: np.ndarray,
    *,
    image_shape: tuple[int, int],
    transform: dict[str, float],
) -> tuple[list[list[float]], list[list[float]], dict[str, Any]]:
    h, w = image_shape
    min_len = max(8, min(h, w) // 40)
    branch_min_len = max(4, min_len // 2)
    wall_thin = 1.0
    h_mask, h_rects, h_components = _extract_oriented_region_components(
        cleaned,
        orientation="horizontal",
        min_len=min_len,
        min_thickness=2,
        min_aspect_ratio=2.5,
        image_shape=image_shape,
        transform=transform,
        wall_thin=wall_thin,
    )
    v_mask, v_rects, v_components = _extract_oriented_region_components(
        cleaned,
        orientation="vertical",
        min_len=min_len,
        min_thickness=2,
        min_aspect_ratio=2.5,
        image_shape=image_shape,
        transform=transform,
        wall_thin=wall_thin,
    )

    horizontal_support_mask = cv2.dilate(
        v_mask,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, max(3, branch_min_len))),
        iterations=1,
    )
    vertical_support_mask = cv2.dilate(
        h_mask,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, branch_min_len), 3)),
        iterations=1,
    )
    short_h_source = cv2.bitwise_and(cleaned, cv2.bitwise_not(h_mask))
    short_v_source = cv2.bitwise_and(cleaned, cv2.bitwise_not(v_mask))
    short_h_mask, short_h_rects, short_h_components = _extract_short_branch_components(
        short_h_source,
        orientation="horizontal",
        long_min_len=min_len,
        branch_min_len=branch_min_len,
        min_thickness=2,
        min_aspect_ratio=1.8,
        image_shape=image_shape,
        transform=transform,
        wall_thin=wall_thin,
        support_mask=horizontal_support_mask,
    )
    short_v_mask, short_v_rects, short_v_components = _extract_short_branch_components(
        short_v_source,
        orientation="vertical",
        long_min_len=min_len,
        branch_min_len=branch_min_len,
        min_thickness=2,
        min_aspect_ratio=1.8,
        image_shape=image_shape,
        transform=transform,
        wall_thin=wall_thin,
        support_mask=vertical_support_mask,
    )
    h_rects.extend(short_h_rects)
    v_rects.extend(short_v_rects)

    return h_rects, v_rects, {
        "min_len": float(min_len),
        "branch_min_len": float(branch_min_len),
        "wall_thin": float(wall_thin),
        "horizontal_mask": _summarize_binary_mask(h_mask),
        "vertical_mask": _summarize_binary_mask(v_mask),
        "horizontal_components": h_components,
        "vertical_components": v_components,
        "short_horizontal_mask": _summarize_binary_mask(short_h_mask),
        "short_vertical_mask": _summarize_binary_mask(short_v_mask),
        "short_horizontal_components": short_h_components,
        "short_vertical_components": short_v_components,
        "horizontal_candidate_count": len(h_components),
        "vertical_candidate_count": len(v_components),
        "horizontal_accepted_count": sum(1 for component in h_components if component["accepted"]),
        "vertical_accepted_count": sum(1 for component in v_components if component["accepted"]),
        "short_horizontal_candidate_count": len(short_h_components),
        "short_vertical_candidate_count": len(short_v_components),
        "short_horizontal_accepted_count": sum(1 for component in short_h_components if component["accepted"]),
        "short_vertical_accepted_count": sum(1 for component in short_v_components if component["accepted"]),
    }
