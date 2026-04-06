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
) -> int:
    if not annotations:
        return 0

    if "DOORS" not in doc.layers:
        doc.layers.add("DOORS", color=157)
    if "WINS" not in doc.layers:
        doc.layers.add("WINS", color=121)

    rect_count = 0

    for ann in annotations:
        ann_type = ann.get("type", "wall")
        if ann_type == "eraser":
            continue

        dx1, dy1 = _mitunet_region_img_to_dxf(int(ann["x1"]), int(ann["y1"]), image_shape=image_shape, transform=transform)
        dx2, dy2 = _mitunet_region_img_to_dxf(int(ann["x2"]), int(ann["y2"]), image_shape=image_shape, transform=transform)

        if ann_type == "wall":
            adx = abs(dx2 - dx1)
            ady = abs(dy2 - dy1)
            thickness = wall_thickness  # match model wall thickness (median)
            if adx >= ady:
                y_mid = (dy1 + dy2) / 2
                x_lo, x_hi = min(dx1, dx2), max(dx1, dx2)
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
            from ..components.windows import draw_window_h, draw_window_v  # noqa: E402

            exterior = ann.get("swing")  # reuse swing field for exterior side
            if not exterior:
                continue  # No side set = skip (user must pick exterior direction)

            adx = abs(dx2 - dx1)
            ady = abs(dy2 - dy1)
            # Map user direction to draw_window side parameter
            if adx >= ady:
                # Horizontal window: DXF Y-flip means up→bottom, down→top
                side = "bottom" if exterior == "up" else "top"
                x_lo = min(dx1, dx2)
                y_mid = (dy1 + dy2) / 2
                draw_window_h(msp, x_lo, y_mid, adx, side=side)
            else:
                # Vertical window: left→left, right→right
                side = exterior  # already "left" or "right"
                x_mid = (dx1 + dx2) / 2
                y_lo = min(dy1, dy2)
                draw_window_v(msp, x_mid, y_lo, ady, side=side)

    return rect_count
