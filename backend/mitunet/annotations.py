from __future__ import annotations

import math
from typing import Any

from .regions import _mitunet_region_dxf_to_img, _mitunet_region_img_to_dxf


def regions_to_wall_annotations(
    region_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    """Convert region plan wall regions to image-space wall annotations."""
    meta = region_plan.get("meta") or {}
    image_shape_meta = meta.get("image_shape") or {}
    image_shape = (
        int(image_shape_meta.get("height", 0)),
        int(image_shape_meta.get("width", 0)),
    )
    transform = meta.get("transform") or {}
    if image_shape[0] <= 0 or image_shape[1] <= 0:
        return []

    annotations: list[dict[str, Any]] = []
    for region in region_plan.get("regions", []):
        bounds = region.get("bounds") or {}
        x1 = float(bounds.get("x1", 0))
        y1 = float(bounds.get("y1", 0))
        x2 = float(bounds.get("x2", 0))
        y2 = float(bounds.get("y2", 0))
        orientation = region.get("orientation", "horizontal")

        # Region center line in DXF coords
        if orientation == "horizontal":
            mid_y = (y1 + y2) / 2
            dxf_start, dxf_end = (x1, mid_y), (x2, mid_y)
        else:
            mid_x = (x1 + x2) / 2
            dxf_start, dxf_end = (mid_x, y1), (mid_x, y2)

        # Convert to image coords
        ix1, iy1 = _mitunet_region_dxf_to_img(
            dxf_start[0], dxf_start[1],
            image_shape=image_shape, transform=transform,
        )
        ix2, iy2 = _mitunet_region_dxf_to_img(
            dxf_end[0], dxf_end[1],
            image_shape=image_shape, transform=transform,
        )

        annotations.append({
            "type": "wall",
            "x1": round(ix1, 1),
            "y1": round(iy1, 1),
            "x2": round(ix2, 1),
            "y2": round(iy2, 1),
            "_source": "mitunet_region",
        })

    return annotations


def _draw_mitunet_annotations_from_region_plan(
    msp: Any,
    doc: Any,
    annotations: list[dict] | None,
    *,
    image_shape: tuple[int, int],
    transform: dict[str, float],
    wall_thickness: float = 4.0,
    regions: list[dict] | None = None,
) -> int:
    if not annotations:
        return 0

    if "DOORS" not in doc.layers:
        doc.layers.add("DOORS", color=157)
    if "WINS" not in doc.layers:
        doc.layers.add("WINS", color=121)

    rect_count = 0

    # Pre-compute region DXF rects for thickness lookup
    _region_rects: list[tuple[float, float, float, float, float]] = []
    for region in (regions or []):
        bounds = region.get("bounds") or {}
        rx1 = float(bounds.get("x1", 0))
        ry1 = float(bounds.get("y1", 0))
        rx2 = float(bounds.get("x2", 0))
        ry2 = float(bounds.get("y2", 0))
        dt = float(region.get("draw_thickness", 0))
        if dt > 0:
            _region_rects.append((rx1, ry1, rx2, ry2, dt))

    # Compute median for snap threshold
    all_dt = [r[4] for r in _region_rects]
    if all_dt:
        all_dt.sort()
        m = len(all_dt) // 2
        _thickness_median = all_dt[m] if len(all_dt) % 2 else (all_dt[m - 1] + all_dt[m]) / 2
    else:
        _thickness_median = wall_thickness

    def _resolve_wall_thickness(dx1: float, dy1: float, dx2: float, dy2: float) -> float:
        """Find the closest region to this wall annotation and snap its thickness."""
        mid_x = (dx1 + dx2) / 2
        mid_y = (dy1 + dy2) / 2
        best_dt = 0.0
        best_dist = float("inf")
        for rx1, ry1, rx2, ry2, dt in _region_rects:
            rmx = (rx1 + rx2) / 2
            rmy = (ry1 + ry2) / 2
            d = abs(mid_x - rmx) + abs(mid_y - rmy)
            if d < best_dist:
                best_dist = d
                best_dt = dt
        if best_dt > 0:
            return 6.0 if best_dt > _thickness_median else 4.0
        return wall_thickness

    # Pre-compute wall DXF coords for junction detection
    wall_dxf_coords: list[tuple[float, float, float, float]] = []
    for ann in annotations:
        if ann.get("type") != "wall":
            continue
        wx1, wy1 = _mitunet_region_img_to_dxf(int(ann["x1"]), int(ann["y1"]), image_shape=image_shape, transform=transform)
        wx2, wy2 = _mitunet_region_img_to_dxf(int(ann["x2"]), int(ann["y2"]), image_shape=image_shape, transform=transform)
        wall_dxf_coords.append((wx1, wy1, wx2, wy2))

    def _find_parent_wall_edges(
        win_lo: float, win_hi: float, win_mid: float, is_horizontal: bool,
    ) -> tuple[float, float] | None:
        """Find the wall that contains this window and return (edge_minus, edge_plus).

        A wall is the parent if:
        1. Same orientation (horizontal window on horizontal wall)
        2. Its centerline is close to the window centerline (perpendicular axis)
        3. The window span overlaps with the wall span (parallel axis)
        """
        ht = wall_thickness / 2
        tolerance = wall_thickness * 1.5
        best: tuple[float, float] | None = None
        best_overlap = 0.0

        for wx1, wy1, wx2, wy2 in wall_dxf_coords:
            if is_horizontal:
                wall_mid = (wy1 + wy2) / 2
                wall_lo = min(wx1, wx2)
                wall_hi = max(wx1, wx2)
            else:
                wall_mid = (wx1 + wx2) / 2
                wall_lo = min(wy1, wy2)
                wall_hi = max(wy1, wy2)

            # Check centerline proximity (perpendicular axis)
            if abs(wall_mid - win_mid) > tolerance:
                continue

            # Check span overlap (parallel axis)
            overlap_lo = max(win_lo, wall_lo)
            overlap_hi = min(win_hi, wall_hi)
            overlap = overlap_hi - overlap_lo
            if overlap <= 0:
                continue

            if overlap > best_overlap:
                best_overlap = overlap
                best = (wall_mid - ht, wall_mid + ht)

        return best

    def _has_junction(px: float, py: float, skip_idx: int) -> bool:
        """Check if another wall endpoint is near (px, py)."""
        snap = wall_thickness * 1.5
        for i, (wx1, wy1, wx2, wy2) in enumerate(wall_dxf_coords):
            if i == skip_idx:
                continue
            for ex, ey in [(wx1, wy1), (wx2, wy2)]:
                if abs(px - ex) <= snap and abs(py - ey) <= snap:
                    return True
        return False

    wall_idx = 0
    for ann in annotations:
        ann_type = ann.get("type", "wall")
        if ann_type == "eraser":
            continue

        dx1, dy1 = _mitunet_region_img_to_dxf(int(ann["x1"]), int(ann["y1"]), image_shape=image_shape, transform=transform)
        dx2, dy2 = _mitunet_region_img_to_dxf(int(ann["x2"]), int(ann["y2"]), image_shape=image_shape, transform=transform)

        if ann_type == "wall":
            adx = abs(dx2 - dx1)
            ady = abs(dy2 - dy1)
            thickness = _resolve_wall_thickness(dx1, dy1, dx2, dy2)
            ext = thickness / 2  # extension for junctions

            if adx >= ady:
                y_mid = (dy1 + dy2) / 2
                x_lo, x_hi = min(dx1, dx2), max(dx1, dx2)
                # Extend horizontally at junctions
                if _has_junction(x_lo, y_mid, wall_idx):
                    x_lo -= ext
                if _has_junction(x_hi, y_mid, wall_idx):
                    x_hi += ext
                pts = [
                    (x_lo, y_mid - thickness / 2),
                    (x_hi, y_mid - thickness / 2),
                    (x_hi, y_mid + thickness / 2),
                    (x_lo, y_mid + thickness / 2),
                    (x_lo, y_mid - thickness / 2),
                ]
            else:
                x_mid = (dx1 + dx2) / 2
                y_lo, y_hi = min(dy1, dy2), max(dy1, dy2)
                # Extend vertically at junctions
                if _has_junction(x_mid, y_lo, wall_idx):
                    y_lo -= ext
                if _has_junction(x_mid, y_hi, wall_idx):
                    y_hi += ext
                pts = [
                    (x_mid - thickness / 2, y_lo),
                    (x_mid + thickness / 2, y_lo),
                    (x_mid + thickness / 2, y_hi),
                    (x_mid - thickness / 2, y_hi),
                    (x_mid - thickness / 2, y_lo),
                ]
            poly = msp.add_lwpolyline(pts, dxfattribs={"layer": "WALLS", "color": 7})
            poly.close()
            hatch = msp.add_hatch(color=7, dxfattribs={"layer": "WALLS"})
            hatch.paths.add_polyline_path(pts, is_closed=True)
            rect_count += 1
            wall_idx += 1
            continue

        if ann_type == "door":
            adx = abs(dx2 - dx1)
            ady = abs(dy2 - dy1)
            door_width = adx if adx >= ady else ady

            if door_width < 2:
                continue

            swing = ann.get("swing")
            if not swing:
                continue  # No swing = skip (user must set direction first)

            dxf_swing = swing

            # First point = hinge. Determine if hinge is mirrored
            # (on the right/top end instead of the normal left/bottom).
            hx, hy = dx1, dy1
            is_horiz = adx >= ady
            mirrored = (dx1 > dx2) if is_horiz else (dy1 > dy2)

            DS = 1.5
            attribs = {"layer": "DOORS", "color": 157}

            if dxf_swing == "up":
                ds_sign = -1 if mirrored else 1
                msp.add_line((hx, hy), (hx, hy + door_width), dxfattribs=attribs)
                msp.add_line((hx + ds_sign * DS, hy), (hx + ds_sign * DS, hy + door_width), dxfattribs=attribs)
                if mirrored:
                    msp.add_arc((hx, hy), door_width, 90, 180, dxfattribs=attribs)
                else:
                    msp.add_arc((hx, hy), door_width, 0, 90, dxfattribs=attribs)
            elif dxf_swing == "down":
                ds_sign = -1 if mirrored else 1
                msp.add_line((hx, hy), (hx, hy - door_width), dxfattribs=attribs)
                msp.add_line((hx + ds_sign * DS, hy), (hx + ds_sign * DS, hy - door_width), dxfattribs=attribs)
                if mirrored:
                    msp.add_arc((hx, hy), door_width, 180, 270, dxfattribs=attribs)
                else:
                    msp.add_arc((hx, hy), door_width, 270, 360, dxfattribs=attribs)
            elif dxf_swing == "right":
                ds_sign = -1 if mirrored else 1
                msp.add_line((hx, hy), (hx + door_width, hy), dxfattribs=attribs)
                msp.add_line((hx, hy + ds_sign * DS), (hx + door_width, hy + ds_sign * DS), dxfattribs=attribs)
                if mirrored:
                    msp.add_arc((hx, hy), door_width, 270, 360, dxfattribs=attribs)
                else:
                    msp.add_arc((hx, hy), door_width, 0, 90, dxfattribs=attribs)
            elif dxf_swing == "left":
                ds_sign = -1 if mirrored else 1
                msp.add_line((hx, hy), (hx - door_width, hy), dxfattribs=attribs)
                msp.add_line((hx, hy + ds_sign * DS), (hx - door_width, hy + ds_sign * DS), dxfattribs=attribs)
                if mirrored:
                    msp.add_arc((hx, hy), door_width, 180, 270, dxfattribs=attribs)
                else:
                    msp.add_arc((hx, hy), door_width, 90, 180, dxfattribs=attribs)
            continue

        if ann_type == "window":
            from ..components.windows import draw_window_h, draw_window_v, H_SILL_OFFSET, V_SILL_OUT

            exterior = ann.get("swing")
            if not exterior:
                continue

            adx = abs(dx2 - dx1)
            ady = abs(dy2 - dy1)

            if adx >= ady:
                side = "bottom" if exterior == "up" else "top"
                x_lo, x_hi = min(dx1, dx2), max(dx1, dx2)
                y_mid = (dy1 + dy2) / 2
                edges = _find_parent_wall_edges(x_lo, x_hi, y_mid, is_horizontal=True)
                if edges:
                    sill_target = edges[0] if side == "bottom" else edges[1]
                    y_param = sill_target + H_SILL_OFFSET if side == "bottom" else sill_target - H_SILL_OFFSET
                else:
                    y_param = y_mid
                draw_window_h(msp, x_lo, y_param, adx, side=side)
            else:
                side = exterior
                x_mid = (dx1 + dx2) / 2
                y_lo, y_hi = min(dy1, dy2), max(dy1, dy2)
                edges = _find_parent_wall_edges(y_lo, y_hi, x_mid, is_horizontal=False)
                if edges:
                    if side == "left":
                        sill_target = edges[0]
                        x_param = sill_target + V_SILL_OUT
                    else:
                        sill_target = edges[1]
                        x_param = sill_target - V_SILL_OUT - wall_thickness
                    draw_window_v(msp, x_param, y_lo, ady, side=side, thickness=wall_thickness)
                else:
                    draw_window_v(msp, x_mid, y_lo, ady, side=side, thickness=wall_thickness)

    return rect_count
