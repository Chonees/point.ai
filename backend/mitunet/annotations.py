from __future__ import annotations

import math
from typing import Any

from .junctions import resolve_wall_junctions
from .regions import _mitunet_region_dxf_to_img, _mitunet_region_img_to_dxf


def regions_to_wall_annotations(
    region_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    """Convert region plan wall regions to image-space wall annotations.

    Each wall annotation includes a ``thickness`` field (4 or 6 inches)
    derived from the region's ``draw_thickness`` using the median as the
    split threshold — same logic the DXF writer uses.
    """
    meta = region_plan.get("meta") or {}
    image_shape_meta = meta.get("image_shape") or {}
    image_shape = (
        int(image_shape_meta.get("height", 0)),
        int(image_shape_meta.get("width", 0)),
    )
    transform = meta.get("transform") or {}
    if image_shape[0] <= 0 or image_shape[1] <= 0:
        return []

    regions = region_plan.get("regions", [])

    # Compute median draw_thickness for snap threshold (mirrors dxf_writer logic)
    all_dt = [float(r.get("draw_thickness", 0)) for r in regions if float(r.get("draw_thickness", 0)) > 0]
    if all_dt:
        all_dt.sort()
        m = len(all_dt) // 2
        dt_median = all_dt[m] if len(all_dt) % 2 else (all_dt[m - 1] + all_dt[m]) / 2
    else:
        dt_median = 4.0

    annotations: list[dict[str, Any]] = []
    for region in regions:
        bounds = region.get("bounds") or {}
        x1 = float(bounds.get("x1", 0))
        y1 = float(bounds.get("y1", 0))
        x2 = float(bounds.get("x2", 0))
        y2 = float(bounds.get("y2", 0))
        orientation = region.get("orientation", "horizontal")

        # Snap thickness: same median-based classification as DXF writer
        raw_dt = float(region.get("draw_thickness", 0))
        thickness = 6 if raw_dt > dt_median else 4

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
            "thickness": thickness,
            "orientation": orientation,
            "_source": "mitunet_region",
        })

    # Post-process: push endpoints from centerline to wall edge
    _snap_annotations_to_wall_edges(annotations)

    # Remove internal-only fields before returning
    for ann in annotations:
        ann.pop("orientation", None)

    return annotations


def _snap_annotations_to_wall_edges(annotations: list[dict[str, Any]]) -> None:
    """Adjust wall annotation endpoints using the shared junction resolver.

    Converts image-space annotations to the normalized format expected by
    resolve_wall_junctions(), applies junction logic, then writes back.
    Visual line widths (px): 4" wall → 4px, 6" wall → 8px.
    """
    wall_anns = [a for a in annotations if a["type"] == "wall"]
    if len(wall_anns) < 2:
        return

    # Convert to junction resolver format
    junction_walls = []
    for a in wall_anns:
        ori = a.get("orientation", "horizontal")
        hlw = (8 if a["thickness"] == 6 else 4) / 2
        if ori == "horizontal":
            junction_walls.append({
                "orientation": "horizontal",
                "mid": (a["y1"] + a["y2"]) / 2,
                "span_lo": min(a["x1"], a["x2"]),
                "span_hi": max(a["x1"], a["x2"]),
                "half_lw": hlw,
            })
        else:
            junction_walls.append({
                "orientation": "vertical",
                "mid": (a["x1"] + a["x2"]) / 2,
                "span_lo": min(a["y1"], a["y2"]),
                "span_hi": max(a["y1"], a["y2"]),
                "half_lw": hlw,
            })

    resolved = resolve_wall_junctions(junction_walls)

    # Write adjusted spans back to annotations
    for a, orig, adj in zip(wall_anns, junction_walls, resolved):
        ori = a.get("orientation", "horizontal")
        if ori == "horizontal":
            if a["x1"] <= a["x2"]:
                a["x1"] = round(adj["span_lo"], 1)
                a["x2"] = round(adj["span_hi"], 1)
            else:
                a["x1"] = round(adj["span_hi"], 1)
                a["x2"] = round(adj["span_lo"], 1)
        else:
            if a["y1"] <= a["y2"]:
                a["y1"] = round(adj["span_lo"], 1)
                a["y2"] = round(adj["span_hi"], 1)
            else:
                a["y1"] = round(adj["span_hi"], 1)
                a["y2"] = round(adj["span_lo"], 1)


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

    # Pre-resolve all wall junctions using the shared resolver
    _junction_input = []
    _wall_ann_indices = []
    _wall_thicknesses = []
    for i, ann in enumerate(annotations):
        if ann.get("type") != "wall":
            continue
        wx1, wy1, wx2, wy2 = wall_dxf_coords[len(_junction_input)]
        adx, ady = abs(wx2 - wx1), abs(wy2 - wy1)
        thickness = float(ann["thickness"]) if ann.get("thickness") else _resolve_wall_thickness(wx1, wy1, wx2, wy2)
        ht = thickness / 2
        is_h = adx >= ady
        _junction_input.append({
            "orientation": "horizontal" if is_h else "vertical",
            "mid": (wy1 + wy2) / 2 if is_h else (wx1 + wx2) / 2,
            "span_lo": min(wx1, wx2) if is_h else min(wy1, wy2),
            "span_hi": max(wx1, wx2) if is_h else max(wy1, wy2),
            "half_lw": ht,
        })
        _wall_ann_indices.append(i)
        _wall_thicknesses.append(thickness)

    _resolved_walls = resolve_wall_junctions(_junction_input, mode="dxf")

    # Debug: log junction adjustments
    for i, (orig, adj) in enumerate(zip(_junction_input, _resolved_walls)):
        if orig["span_lo"] != adj["span_lo"] or orig["span_hi"] != adj["span_hi"]:
            print(f"[DXF-Junction] wall {i} {orig['orientation']}: "
                  f"span {orig['span_lo']:.1f}..{orig['span_hi']:.1f} → "
                  f"{adj['span_lo']:.1f}..{adj['span_hi']:.1f}", flush=True)
    if not any(o["span_lo"] != a["span_lo"] or o["span_hi"] != a["span_hi"]
               for o, a in zip(_junction_input, _resolved_walls)):
        print(f"[DXF-Junction] NO adjustments made! {len(_junction_input)} walls, "
              f"H={len([w for w in _junction_input if w['orientation']=='horizontal'])}, "
              f"V={len([w for w in _junction_input if w['orientation']=='vertical'])}", flush=True)
        # Dump first few walls for debugging
        for w in _junction_input[:6]:
            print(f"  {w['orientation']} mid={w['mid']:.1f} span={w['span_lo']:.1f}..{w['span_hi']:.1f} hlw={w['half_lw']:.1f}", flush=True)

    wall_idx = 0
    for ann in annotations:
        ann_type = ann.get("type", "wall")
        if ann_type == "eraser":
            continue

        dx1, dy1 = _mitunet_region_img_to_dxf(int(ann["x1"]), int(ann["y1"]), image_shape=image_shape, transform=transform)
        dx2, dy2 = _mitunet_region_img_to_dxf(int(ann["x2"]), int(ann["y2"]), image_shape=image_shape, transform=transform)

        if ann_type == "wall":
            thickness = _wall_thicknesses[wall_idx]
            ht = thickness / 2
            rw = _resolved_walls[wall_idx]
            is_horiz = rw["orientation"] == "horizontal"

            if is_horiz:
                y_mid = rw["mid"]
                hatch_pts = [
                    (rw["span_lo"], y_mid - ht), (rw["span_hi"], y_mid - ht),
                    (rw["span_hi"], y_mid + ht), (rw["span_lo"], y_mid + ht),
                    (rw["span_lo"], y_mid - ht),
                ]
                pts = list(hatch_pts)
            else:
                x_mid = rw["mid"]
                hatch_pts = [
                    (x_mid - ht, rw["span_lo"]), (x_mid + ht, rw["span_lo"]),
                    (x_mid + ht, rw["span_hi"]), (x_mid - ht, rw["span_hi"]),
                    (x_mid - ht, rw["span_lo"]),
                ]
                pts = list(hatch_pts)

            from ..components.hatch import add_wall_hatch

            poly = msp.add_lwpolyline(pts, dxfattribs={"layer": "WALLS", "color": 7, "lineweight": 100})
            poly.close()
            add_wall_hatch(msp, doc, hatch_pts, thickness)
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
