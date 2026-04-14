from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from .model import (
    MAX_MITUNET_REGION_WALL_THICKNESS,
    MITUNET_BACKEND,
    MITUNET_MASK_REGIONS_DXF_MODE,
    _PLAN_X1,
    _PLAN_X2,
    _PLAN_Y1,
    _PLAN_Y2,
    _TEMPLATE_PATH,
)


def _prepare_mitunet_wall_mask_for_regions(
    wall_mask: np.ndarray,
    *,
    image_shape: tuple[int, int],
    annotations: list[dict] | None = None,
) -> np.ndarray:
    h, w = image_shape
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    cleaned = cv2.morphologyEx(wall_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    cleaned = cv2.morphologyEx(
        cleaned,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
    )

    if annotations:
        for ann in annotations:
            if ann.get("type") != "eraser":
                continue
            ex1 = max(0, int(ann["x1"]))
            ey1 = max(0, int(ann["y1"]))
            ex2 = min(w, int(ann["x2"]))
            ey2 = min(h, int(ann["y2"]))
            cleaned[ey1:ey2, ex1:ex2] = 0

    return cleaned


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


def _resolve_mitunet_plan_transform(image_shape: tuple[int, int]) -> dict[str, float]:
    """Compute a transform that fits the floor plan + dimension annotations
    inside the static Pointe Homes title-block frame with margin to spare.

    The ``DIM_MARGIN_PX`` reserves space for dimension lines, extension
    lines, and text that sit outside the wall extents. Without this margin
    the dims overflow the title block.
    """
    h, w = image_shape
    plan_w = _PLAN_X2 - _PLAN_X1
    plan_h = _PLAN_Y2 - _PLAN_Y1

    # Reserve margin in image-pixel space for dimension offsets + text.
    # 100px ≈ the max dim offset (80px) + text overshoot (20px).
    DIM_MARGIN_PX = 100
    effective_w = w + 2 * DIM_MARGIN_PX
    effective_h = h + 2 * DIM_MARGIN_PX
    eff_aspect = effective_w / effective_h
    plan_aspect = plan_w / plan_h

    if eff_aspect > plan_aspect:
        scale = plan_w / effective_w
    else:
        scale = plan_h / effective_h

    # Center the IMAGE (not the effective area) within the plan box.
    # The margins distribute evenly on all sides.
    offset_x = _PLAN_X1 + (plan_w - w * scale) / 2
    offset_y = _PLAN_Y1 + (plan_h - h * scale) / 2

    return {
        "scale": float(scale),
        "offset_x": float(offset_x),
        "offset_y": float(offset_y),
        "plan_x1": float(_PLAN_X1),
        "plan_y1": float(_PLAN_Y1),
        "plan_x2": float(_PLAN_X2),
        "plan_y2": float(_PLAN_Y2),
    }


def _mitunet_region_img_to_dxf(
    ix: float,
    iy: float,
    *,
    image_shape: tuple[int, int],
    transform: dict[str, float],
) -> tuple[float, float]:
    h, _ = image_shape
    dx = ix * transform["scale"] + transform["offset_x"]
    dy = (h - iy) * transform["scale"] + transform["offset_y"]
    return dx, dy


def _mitunet_region_dxf_to_img(
    dx: float,
    dy: float,
    *,
    image_shape: tuple[int, int],
    transform: dict[str, float],
) -> tuple[float, float]:
    h, _ = image_shape
    scale = float(transform.get("scale", 1.0) or 1.0)
    offset_x = float(transform.get("offset_x", 0.0) or 0.0)
    offset_y = float(transform.get("offset_y", 0.0) or 0.0)
    ix = (dx - offset_x) / scale
    iy = h - ((dy - offset_y) / scale)
    return ix, iy


def _collect_mitunet_region_rectangles(
    cleaned: np.ndarray,
    *,
    image_shape: tuple[int, int],
    transform: dict[str, float],
) -> tuple[list[list[float]], list[list[float]], dict[str, Any]]:
    h, w = image_shape
    min_len = max(8, min(h, w) // 40)
    wall_thin = 0.4
    h_rects: list[list[float]] = []
    v_rects: list[list[float]] = []
    h_components: list[dict[str, Any]] = []
    v_components: list[dict[str, Any]] = []

    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (min_len, 1))
    h_mask = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, h_kernel)
    num_h, _, stats_h, _ = cv2.connectedComponentsWithStats(h_mask, connectivity=8)
    for i in range(1, num_h):
        x = stats_h[i, cv2.CC_STAT_LEFT]
        y = stats_h[i, cv2.CC_STAT_TOP]
        cw = stats_h[i, cv2.CC_STAT_WIDTH]
        ch = stats_h[i, cv2.CC_STAT_HEIGHT]
        component_entry = {
            "component_index": int(i),
            "orientation": "horizontal",
            "image_bounds": {
                "x1": int(x),
                "y1": int(y),
                "x2": int(x + cw),
                "y2": int(y + ch),
            },
            "pixel_width": int(cw),
            "pixel_height": int(ch),
            "accepted": False,
        }
        if cw < min_len or ch < 2:
            component_entry["skip_reason"] = "too_short"
            h_components.append(component_entry)
            continue
        if ch > 0 and cw / ch < 2.5:
            component_entry["skip_reason"] = "insufficient_aspect_ratio"
            h_components.append(component_entry)
            continue
        trim = ch * (1 - wall_thin) / 2
        y_s = y + trim
        ch_s = ch - 2 * trim
        x1d, y1d = _mitunet_region_img_to_dxf(x, y_s + ch_s, image_shape=image_shape, transform=transform)
        x2d, y2d = _mitunet_region_img_to_dxf(x + cw, y_s, image_shape=image_shape, transform=transform)
        rect = [min(x1d, x2d), min(y1d, y2d), max(x1d, x2d), max(y1d, y2d)]
        h_rects.append(rect)
        component_entry["accepted"] = True
        component_entry["dxf_bounds"] = _rect_bounds_dict(rect)
        component_entry["dxf_length"] = float(max(rect[2] - rect[0], rect[3] - rect[1]))
        component_entry["dxf_thickness"] = float(min(rect[2] - rect[0], rect[3] - rect[1]))
        h_components.append(component_entry)

    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, min_len))
    v_mask = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, v_kernel)
    num_v, _, stats_v, _ = cv2.connectedComponentsWithStats(v_mask, connectivity=8)
    for i in range(1, num_v):
        x = stats_v[i, cv2.CC_STAT_LEFT]
        y = stats_v[i, cv2.CC_STAT_TOP]
        cw = stats_v[i, cv2.CC_STAT_WIDTH]
        ch = stats_v[i, cv2.CC_STAT_HEIGHT]
        component_entry = {
            "component_index": int(i),
            "orientation": "vertical",
            "image_bounds": {
                "x1": int(x),
                "y1": int(y),
                "x2": int(x + cw),
                "y2": int(y + ch),
            },
            "pixel_width": int(cw),
            "pixel_height": int(ch),
            "accepted": False,
        }
        if ch < min_len or cw < 2:
            component_entry["skip_reason"] = "too_short"
            v_components.append(component_entry)
            continue
        if cw > 0 and ch / cw < 2.5:
            component_entry["skip_reason"] = "insufficient_aspect_ratio"
            v_components.append(component_entry)
            continue
        trim = cw * (1 - wall_thin) / 2
        x_s = x + trim
        cw_s = cw - 2 * trim
        x1d, y1d = _mitunet_region_img_to_dxf(x_s, y + ch, image_shape=image_shape, transform=transform)
        x2d, y2d = _mitunet_region_img_to_dxf(x_s + cw_s, y, image_shape=image_shape, transform=transform)
        rect = [min(x1d, x2d), min(y1d, y2d), max(x1d, x2d), max(y1d, y2d)]
        v_rects.append(rect)
        component_entry["accepted"] = True
        component_entry["dxf_bounds"] = _rect_bounds_dict(rect)
        component_entry["dxf_length"] = float(max(rect[2] - rect[0], rect[3] - rect[1]))
        component_entry["dxf_thickness"] = float(min(rect[2] - rect[0], rect[3] - rect[1]))
        v_components.append(component_entry)

    return h_rects, v_rects, {
        "min_len": float(min_len),
        "wall_thin": float(wall_thin),
        "horizontal_mask": _summarize_binary_mask(h_mask),
        "vertical_mask": _summarize_binary_mask(v_mask),
        "horizontal_components": h_components,
        "vertical_components": v_components,
        "horizontal_candidate_count": len(h_components),
        "vertical_candidate_count": len(v_components),
        "horizontal_accepted_count": sum(1 for component in h_components if component["accepted"]),
        "vertical_accepted_count": sum(1 for component in v_components if component["accepted"]),
    }


def _trim_mitunet_region_rectangles(h_rects: list[list[float]], v_rects: list[list[float]]) -> None:
    tol = 2.0
    width_margin = 1.3

    for hr in h_rects:
        hx1, hy1, hx2, hy2 = hr
        h_cy = (hy1 + hy2) / 2
        for vr in v_rects:
            vx1, vy1, vx2, vy2 = vr
            v_w = vx2 - vx1
            if not (vy1 - tol <= h_cy <= vy2 + tol):
                continue
            if not (hx1 < vx2 and hx2 > vx1):
                continue
            if vx1 - tol < hx2 < vx2 + v_w * width_margin:
                hr[2] = vx2
            if vx1 - v_w * width_margin < hx1 < vx2 + tol:
                hr[0] = vx1

    for vr in v_rects:
        vx1, vy1, vx2, vy2 = vr
        v_cx = (vx1 + vx2) / 2
        for hr in h_rects:
            hx1, hy1, hx2, hy2 = hr
            h_h = hy2 - hy1
            if not (hx1 - tol <= v_cx <= hx2 + tol):
                continue
            if not (vy1 < hy2 and vy2 > hy1):
                continue
            if hy1 - tol < vy2 < hy2 + h_h * width_margin:
                vr[3] = hy2
            if hy1 - h_h * width_margin < vy1 < hy2 + tol:
                vr[1] = hy1


def _clamp_region_rect_to_max_thickness(
    rect: list[float],
    *,
    orientation: str,
    max_thickness: float,
) -> tuple[list[float], float, float, bool]:
    x1, y1, x2, y2 = [float(value) for value in rect]
    if orientation == "horizontal":
        raw_thickness = max(0.0, y2 - y1)
        draw_thickness = min(raw_thickness, max_thickness)
        if raw_thickness <= max_thickness:
            return [x1, y1, x2, y2], raw_thickness, draw_thickness, False
        center_y = (y1 + y2) / 2.0
        half = draw_thickness / 2.0
        return [x1, center_y - half, x2, center_y + half], raw_thickness, draw_thickness, True

    raw_thickness = max(0.0, x2 - x1)
    draw_thickness = min(raw_thickness, max_thickness)
    if raw_thickness <= max_thickness:
        return [x1, y1, x2, y2], raw_thickness, draw_thickness, False
    center_x = (x1 + x2) / 2.0
    half = draw_thickness / 2.0
    return [center_x - half, y1, center_x + half, y2], raw_thickness, draw_thickness, True


def _mitunet_region_entry(
    region_id: str,
    orientation: str,
    rect: list[float],
    *,
    max_thickness: float,
) -> dict[str, Any]:
    x1, y1, x2, y2 = rect
    clamped_rect, raw_thickness, draw_thickness, was_clamped = _clamp_region_rect_to_max_thickness(
        rect,
        orientation=orientation,
        max_thickness=max_thickness,
    )
    cx1, cy1, cx2, cy2 = clamped_rect
    return {
        "id": region_id,
        "kind": "wall_region",
        "source": "mitunet_mask",
        "orientation": orientation,
        "raw_thickness": float(raw_thickness),
        "draw_thickness": float(draw_thickness),
        "thickness_clamped": bool(was_clamped),
        "raw_bounds": {
            "x1": float(x1),
            "y1": float(y1),
            "x2": float(x2),
            "y2": float(y2),
        },
        "bounds": {
            "x1": float(cx1),
            "y1": float(cy1),
            "x2": float(cx2),
            "y2": float(cy2),
        },
    }


def build_mitunet_region_plan(
    infer_result: dict[str, Any],
    *,
    annotations: list[dict] | None = None,
) -> dict[str, Any]:
    from .dxf_writer import build_mitunet_provenance

    wall_mask = infer_result["_wall_mask"]
    h, w = infer_result["_image_shape"]
    image_shape = (h, w)
    raw_mask_debug = _summarize_binary_mask(wall_mask)

    cleaned = _prepare_mitunet_wall_mask_for_regions(
        wall_mask,
        image_shape=image_shape,
        annotations=annotations,
    )
    cleaned_mask_debug = _summarize_binary_mask(cleaned)
    transform = _resolve_mitunet_plan_transform(image_shape)
    h_rects, v_rects, extraction_meta = _collect_mitunet_region_rectangles(
        cleaned,
        image_shape=image_shape,
        transform=transform,
    )
    h_rects_before_trim = [list(rect) for rect in h_rects]
    v_rects_before_trim = [list(rect) for rect in v_rects]
    _trim_mitunet_region_rectangles(h_rects, v_rects)
    max_wall_thickness = float(MAX_MITUNET_REGION_WALL_THICKNESS)

    regions = [
        *[
            _mitunet_region_entry(
                f"h-region-{index:04d}",
                "horizontal",
                rect,
                max_thickness=max_wall_thickness,
            )
            for index, rect in enumerate(h_rects, start=1)
        ],
        *[
            _mitunet_region_entry(
                f"v-region-{index:04d}",
                "vertical",
                rect,
                max_thickness=max_wall_thickness,
            )
            for index, rect in enumerate(v_rects, start=1)
        ],
    ]
    clamped_region_count = sum(1 for region in regions if region.get("thickness_clamped"))
    horizontal_adjusted_count = sum(
        1
        for before, after in zip(h_rects_before_trim, h_rects)
        if any(abs(float(before[index]) - float(after[index])) > 1e-6 for index in range(4))
    )
    vertical_adjusted_count = sum(
        1
        for before, after in zip(v_rects_before_trim, v_rects)
        if any(abs(float(before[index]) - float(after[index])) > 1e-6 for index in range(4))
    )
    debug = {
        "stage_order": [
            "raw_wall_mask",
            "cleaned_wall_mask",
            "horizontal_extraction",
            "vertical_extraction",
            "trimmed_rectangles",
            "clamped_regions",
        ],
        "input": {
            "image_shape": {"height": int(h), "width": int(w)},
            "annotation_count": len(annotations or []),
            "eraser_count": sum(1 for ann in (annotations or []) if ann.get("type") == "eraser"),
        },
        "raw_wall_mask": raw_mask_debug,
        "cleaned_wall_mask": cleaned_mask_debug,
        "horizontal_extraction": {
            "mask": extraction_meta["horizontal_mask"],
            "candidate_count": extraction_meta["horizontal_candidate_count"],
            "accepted_count": extraction_meta["horizontal_accepted_count"],
            "components": extraction_meta["horizontal_components"],
            "rectangles": [
                _rect_stage_entry(rect, orientation="horizontal", rect_id=f"h-raw-{index:04d}")
                for index, rect in enumerate(h_rects_before_trim, start=1)
            ],
        },
        "vertical_extraction": {
            "mask": extraction_meta["vertical_mask"],
            "candidate_count": extraction_meta["vertical_candidate_count"],
            "accepted_count": extraction_meta["vertical_accepted_count"],
            "components": extraction_meta["vertical_components"],
            "rectangles": [
                _rect_stage_entry(rect, orientation="vertical", rect_id=f"v-raw-{index:04d}")
                for index, rect in enumerate(v_rects_before_trim, start=1)
            ],
        },
        "trimmed_rectangles": {
            "horizontal_adjusted_count": horizontal_adjusted_count,
            "vertical_adjusted_count": vertical_adjusted_count,
            "horizontal_before": [
                _rect_stage_entry(rect, orientation="horizontal", rect_id=f"h-before-{index:04d}")
                for index, rect in enumerate(h_rects_before_trim, start=1)
            ],
            "horizontal_after": [
                _rect_stage_entry(rect, orientation="horizontal", rect_id=f"h-after-{index:04d}")
                for index, rect in enumerate(h_rects, start=1)
            ],
            "vertical_before": [
                _rect_stage_entry(rect, orientation="vertical", rect_id=f"v-before-{index:04d}")
                for index, rect in enumerate(v_rects_before_trim, start=1)
            ],
            "vertical_after": [
                _rect_stage_entry(rect, orientation="vertical", rect_id=f"v-after-{index:04d}")
                for index, rect in enumerate(v_rects, start=1)
            ],
        },
        "clamped_regions": {
            "region_count": len(regions),
            "clamped_region_count": clamped_region_count,
            "clamped_region_ids": [region["id"] for region in regions if region.get("thickness_clamped")],
            "regions": [
                {
                    "id": region["id"],
                    "orientation": region["orientation"],
                    "raw_bounds": region["raw_bounds"],
                    "bounds": region["bounds"],
                    "raw_thickness": region["raw_thickness"],
                    "draw_thickness": region["draw_thickness"],
                    "thickness_clamped": region["thickness_clamped"],
                }
                for region in regions
            ],
        },
    }

    return {
        "mode": MITUNET_MASK_REGIONS_DXF_MODE,
        "meta": {
            "backend": MITUNET_BACKEND,
            "image_shape": {"height": int(h), "width": int(w)},
            "transform": transform,
            "template_used": _TEMPLATE_PATH.exists(),
            "template_path": str(_TEMPLATE_PATH),
            "annotation_count": len(annotations or []),
            "region_count": len(regions),
            "clamped_region_count": clamped_region_count,
            "max_wall_thickness": max_wall_thickness,
            "min_len": extraction_meta["min_len"],
            "wall_thin": extraction_meta["wall_thin"],
            "provenance": build_mitunet_provenance(),
            "_wall_mask": wall_mask,  # kept in-memory for scale calibration flood fill
        },
        "regions": regions,
        "debug": debug,
    }
