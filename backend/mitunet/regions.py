from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from ..coordinate_space import dxf_point_to_image_space, image_point_to_dxf_space
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
from .region_extraction import (
    _binary_mask_bbox as _shared_binary_mask_bbox,
    _collect_mitunet_region_rectangles as _shared_collect_mitunet_region_rectangles,
    _component_has_perpendicular_support as _shared_component_has_perpendicular_support,
    _component_rect_to_dxf as _shared_component_rect_to_dxf,
    _contiguous_segments as _shared_contiguous_segments,
    _extract_oriented_region_components as _shared_extract_oriented_region_components,
    _extract_short_branch_components as _shared_extract_short_branch_components,
    _rect_bounds_dict as _shared_rect_bounds_dict,
    _rect_stage_entry as _shared_rect_stage_entry,
    _runs_to_branch_groups as _shared_runs_to_branch_groups,
    _summarize_binary_mask as _shared_summarize_binary_mask,
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
    return _shared_binary_mask_bbox(mask)


def _summarize_binary_mask(mask: np.ndarray) -> dict[str, Any]:
    return _shared_summarize_binary_mask(mask)


def _rect_bounds_dict(rect: list[float]) -> dict[str, float]:
    return _shared_rect_bounds_dict(rect)


def _rect_stage_entry(
    rect: list[float],
    *,
    orientation: str,
    rect_id: str,
) -> dict[str, Any]:
    return _shared_rect_stage_entry(rect, orientation=orientation, rect_id=rect_id)


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
    return image_point_to_dxf_space(
        ix,
        iy,
        image_shape=image_shape,
        transform=transform,
    )


def _mitunet_region_dxf_to_img(
    dx: float,
    dy: float,
    *,
    image_shape: tuple[int, int],
    transform: dict[str, float],
) -> tuple[float, float]:
    point = dxf_point_to_image_space(
        dx,
        dy,
        image_shape=image_shape,
        transform=transform,
    )
    return float(point["x"]), float(point["y"])


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
    return _shared_component_rect_to_dxf(
        x=x,
        y=y,
        cw=cw,
        ch=ch,
        orientation=orientation,
        image_shape=image_shape,
        transform=transform,
        wall_thin=wall_thin,
    )


def _component_has_perpendicular_support(
    support_mask: np.ndarray,
    *,
    x: int,
    y: int,
    cw: int,
    ch: int,
    orientation: str,
) -> bool:
    return _shared_component_has_perpendicular_support(
        support_mask,
        x=x,
        y=y,
        cw=cw,
        ch=ch,
        orientation=orientation,
    )


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
    return _shared_extract_oriented_region_components(
        source_mask,
        orientation=orientation,
        min_len=min_len,
        min_thickness=min_thickness,
        min_aspect_ratio=min_aspect_ratio,
        image_shape=image_shape,
        transform=transform,
        wall_thin=wall_thin,
        support_mask=support_mask,
    )


def _contiguous_segments(indices: np.ndarray) -> list[tuple[int, int]]:
    return _shared_contiguous_segments(indices)


def _runs_to_branch_groups(
    runs: list[dict[str, int]],
    *,
    orientation: str,
) -> list[dict[str, int]]:
    return _shared_runs_to_branch_groups(runs, orientation=orientation)


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
    return _shared_extract_short_branch_components(
        source_mask,
        orientation=orientation,
        long_min_len=long_min_len,
        branch_min_len=branch_min_len,
        min_thickness=min_thickness,
        min_aspect_ratio=min_aspect_ratio,
        image_shape=image_shape,
        transform=transform,
        wall_thin=wall_thin,
        support_mask=support_mask,
    )


def _collect_mitunet_region_rectangles(
    cleaned: np.ndarray,
    *,
    image_shape: tuple[int, int],
    transform: dict[str, float],
) -> tuple[list[list[float]], list[list[float]], dict[str, Any]]:
    return _shared_collect_mitunet_region_rectangles(
        cleaned,
        image_shape=image_shape,
        transform=transform,
    )


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
    source_stage: str,
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
        "source_stage": source_stage,
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
                source_stage="long_extraction" if index <= extraction_meta["horizontal_accepted_count"] else "short_branch",
            )
            for index, rect in enumerate(h_rects, start=1)
        ],
        *[
            _mitunet_region_entry(
                f"v-region-{index:04d}",
                "vertical",
                rect,
                max_thickness=max_wall_thickness,
                source_stage="long_extraction" if index <= extraction_meta["vertical_accepted_count"] else "short_branch",
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
            "short_branch_extraction",
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
                for index, rect in enumerate(h_rects_before_trim[: extraction_meta["horizontal_accepted_count"]], start=1)
            ],
        },
        "vertical_extraction": {
            "mask": extraction_meta["vertical_mask"],
            "candidate_count": extraction_meta["vertical_candidate_count"],
            "accepted_count": extraction_meta["vertical_accepted_count"],
            "components": extraction_meta["vertical_components"],
            "rectangles": [
                _rect_stage_entry(rect, orientation="vertical", rect_id=f"v-raw-{index:04d}")
                for index, rect in enumerate(v_rects_before_trim[: extraction_meta["vertical_accepted_count"]], start=1)
            ],
        },
        "short_branch_extraction": {
            "branch_min_len": extraction_meta["branch_min_len"],
            "horizontal_mask": extraction_meta["short_horizontal_mask"],
            "vertical_mask": extraction_meta["short_vertical_mask"],
            "horizontal_candidate_count": extraction_meta["short_horizontal_candidate_count"],
            "vertical_candidate_count": extraction_meta["short_vertical_candidate_count"],
            "horizontal_accepted_count": extraction_meta["short_horizontal_accepted_count"],
            "vertical_accepted_count": extraction_meta["short_vertical_accepted_count"],
            "horizontal_components": extraction_meta["short_horizontal_components"],
            "vertical_components": extraction_meta["short_vertical_components"],
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
                    "source_stage": region["source_stage"],
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
            "branch_min_len": extraction_meta["branch_min_len"],
            "wall_thin": extraction_meta["wall_thin"],
            "provenance": build_mitunet_provenance(),
            "_wall_mask": wall_mask,  # kept in-memory for scale calibration flood fill
        },
        "regions": regions,
        "debug": debug,
    }
