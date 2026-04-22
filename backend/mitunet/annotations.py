from __future__ import annotations

from collections import defaultdict
import math
import uuid
from typing import Any

from ..geometry_utils import is_diagonal as _is_diagonal, snap_endpoint_clusters
from ..wall_geometry import wall_annotation_to_structure_wall as build_structure_wall_from_annotation
from .mask_native import _wall_polygon_from_segment, build_mask_native_wall_annotations
from .junctions import resolve_wall_junctions
from .regions import _mitunet_region_dxf_to_img, _mitunet_region_img_to_dxf


def regions_to_wall_annotations(
    region_plan: dict[str, Any],
    *,
    annotations: list[dict[str, Any]] | None = None,
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

    wall_mask = meta.get("_wall_mask")
    if wall_mask is not None:
        native_annotations = build_mask_native_wall_annotations(wall_mask)
        if native_annotations:
            _snap_annotations_to_wall_edges(native_annotations)
            for ann in native_annotations:
                ann.pop("orientation", None)
            return native_annotations

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
            "id": str(uuid.uuid4()),
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


def align_opening_annotations_to_walls(
    wall_annotations: list[dict[str, Any]],
    annotations: list[dict[str, Any]] | None,
    *,
    image_shape: tuple[int, int] | None = None,
) -> list[dict[str, Any]]:
    """Re-anchor door/window annotations to the current wall annotation ids.

    This keeps the frontend payload and DXF export consistent after swapping
    from region-centerline walls to mask-native walls.
    """
    if not annotations:
        return []

    from ..structure_postprocess import anchor_openings_to_walls

    structure_walls = [_wall_annotation_to_structure_wall(annotation) for annotation in wall_annotations if annotation.get("type") == "wall"]
    if not structure_walls:
        return [dict(annotation) for annotation in annotations]

    height = int(image_shape[0]) if image_shape else int(_infer_annotation_bounds(annotations, axis="y"))
    width = int(image_shape[1]) if image_shape else int(_infer_annotation_bounds(annotations, axis="x"))
    anchored_inputs: list[dict[str, Any]] = []
    passthrough: dict[str, dict[str, Any]] = {}
    ordered_ids: list[tuple[str, str]] = []

    for annotation in annotations:
        ann_type = annotation.get("type")
        ann_id = str(annotation.get("id") or uuid.uuid4())
        if ann_type in {"door", "window"}:
            anchored_inputs.append(_opening_annotation_to_structure_opening(annotation, ann_id=ann_id))
            ordered_ids.append((ann_id, "opening"))
            continue
        passthrough[ann_id] = {**annotation, "id": ann_id}
        ordered_ids.append((ann_id, "passthrough"))

    anchored_openings, _metrics = anchor_openings_to_walls(
        anchored_inputs,
        structure_walls,
        structure_meta={
            "image_size": {"width": width, "height": height},
            "unit": "pixel",
            "scale_status": "unverified",
        },
    )
    anchored_map = {
        str(opening["id"]): _structure_opening_to_annotation(opening)
        for opening in anchored_openings
    }

    aligned: list[dict[str, Any]] = []
    for ann_id, kind in ordered_ids:
        if kind == "passthrough":
            aligned.append(passthrough[ann_id])
            continue
        if ann_id in anchored_map:
            aligned.append(anchored_map[ann_id])
    return aligned


def _snap_annotations_to_wall_edges(annotations: list[dict[str, Any]]) -> None:
    """Adjust wall annotation endpoints using the shared junction resolver.

    Converts image-space annotations to the normalized format expected by
    resolve_wall_junctions(), applies junction logic, then writes back.
    Visual line widths (px): 4" wall → 4px, 6" wall → 8px.
    Diagonal walls are excluded from junction resolution.
    """
    wall_anns = [a for a in annotations if a["type"] == "wall"]
    if len(wall_anns) < 2:
        return

    # Separate H/V walls from diagonals
    hv_anns = [a for a in wall_anns if a.get("orientation") in ("horizontal", "vertical")]
    if len(hv_anns) < 2:
        return

    # Convert to junction resolver format
    junction_walls = []
    for a in hv_anns:
        ori = a["orientation"]
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

    # Write adjusted spans back to H/V annotations
    for a, orig, adj in zip(hv_anns, junction_walls, resolved):
        ori = a["orientation"]
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

        mean_width_px = float(a.get("_mean_width_px", 0.0) or 0.0)
        if mean_width_px > 0.0 and a.get("polygon"):
            polygon = _wall_polygon_from_segment(
                float(a["x1"]),
                float(a["y1"]),
                float(a["x2"]),
                float(a["y2"]),
                mean_width_px,
            )
            a["polygon"] = [
                {"x": round(float(point[0]), 1), "y": round(float(point[1]), 1)}
                for point in polygon
            ]


def _wall_annotation_to_structure_wall(annotation: dict[str, Any]) -> dict[str, Any]:
    wall = build_structure_wall_from_annotation(annotation)
    if not annotation.get("polygon") and wall.get("orientation") == "diagonal":
        wall.pop("polygon", None)
    return wall


def _opening_annotation_to_structure_opening(annotation: dict[str, Any], *, ann_id: str) -> dict[str, Any]:
    x1 = float(annotation["x1"])
    y1 = float(annotation["y1"])
    x2 = float(annotation["x2"])
    y2 = float(annotation["y2"])
    dx = x2 - x1
    dy = y2 - y1
    orientation = "horizontal" if abs(dx) >= abs(dy) else "vertical"
    span = max(abs(dx), abs(dy))
    return {
        "id": ann_id,
        "kind": "door" if annotation.get("type") == "door" else "window",
        "wall_id": annotation.get("wall_id"),
        "position": {"x": (x1 + x2) / 2.0, "y": (y1 + y2) / 2.0},
        "span": float(span),
        "orientation": orientation,
        "side": annotation.get("side"),
        "confidence": float(annotation.get("confidence", 1.0)),
        "swing": annotation.get("swing"),
        "door_type": annotation.get("door_type"),
    }


def _structure_opening_to_annotation(opening: dict[str, Any]) -> dict[str, Any]:
    position = opening.get("position") or {}
    cx = float(position.get("x", 0.0))
    cy = float(position.get("y", 0.0))
    span = float(opening.get("span", 0.0))
    half = span / 2.0
    orientation = opening.get("orientation", "horizontal")
    if orientation == "horizontal":
        x1, y1 = cx - half, cy
        x2, y2 = cx + half, cy
    else:
        x1, y1 = cx, cy - half
        x2, y2 = cx, cy + half

    annotation: dict[str, Any] = {
        "id": str(opening["id"]),
        "type": "door" if opening.get("kind") == "door" else "window",
        "x1": round(x1, 1),
        "y1": round(y1, 1),
        "x2": round(x2, 1),
        "y2": round(y2, 1),
        "wall_id": opening.get("wall_id"),
        "side": opening.get("side"),
    }
    if opening.get("kind") == "door":
        if opening.get("swing"):
            annotation["swing"] = opening["swing"]
        if opening.get("door_type"):
            annotation["door_type"] = opening["door_type"]
    return annotation


def _infer_annotation_bounds(annotations: list[dict[str, Any]], *, axis: str) -> float:
    key1 = "x1" if axis == "x" else "y1"
    key2 = "x2" if axis == "x" else "y2"
    bound = 0.0
    for annotation in annotations:
        bound = max(bound, float(annotation.get(key1, 0.0)), float(annotation.get(key2, 0.0)))
    return max(bound + 1.0, 1.0)


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
        wx1, wy1 = _mitunet_region_img_to_dxf(float(ann["x1"]), float(ann["y1"]), image_shape=image_shape, transform=transform)
        wx2, wy2 = _mitunet_region_img_to_dxf(float(ann["x2"]), float(ann["y2"]), image_shape=image_shape, transform=transform)
        wall_dxf_coords.append((wx1, wy1, wx2, wy2))

    # Snap nearby wall endpoints together (freehand drawing tolerance),
    # but do not let chaining clusters collapse short bridge returns.
    original_wall_dxf_coords = list(wall_dxf_coords)
    endpoint_snap_tolerance = 12.0
    wall_dxf_coords = snap_endpoint_clusters(wall_dxf_coords, tolerance=endpoint_snap_tolerance)
    wall_dxf_coords = _restore_overcollapsed_snapped_walls(
        original_wall_dxf_coords,
        wall_dxf_coords,
        tolerance=endpoint_snap_tolerance,
    )

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
    # Diagonal walls are excluded from the junction resolver (H/V only)
    _junction_input = []
    _wall_ann_indices = []
    _wall_resolver_widths = []
    _wall_draw_widths = []
    _wall_original_spans: list[tuple[str, float, float, float]] = []
    _wall_is_diagonal: list[bool] = []
    _junction_to_wall_idx: list[int] = []  # maps junction idx → wall idx
    wall_count = 0
    for i, ann in enumerate(annotations):
        if ann.get("type") != "wall":
            continue
        wx1, wy1, wx2, wy2 = wall_dxf_coords[wall_count]
        adx, ady = abs(wx2 - wx1), abs(wy2 - wy1)
        semantic_thickness = (
            float(ann["thickness"])
            if ann.get("thickness")
            else _resolve_wall_thickness(wx1, wy1, wx2, wy2)
        )
        draw_width = _resolve_wall_draw_width_dxf(
            ann,
            transform=transform,
            fallback_width=semantic_thickness,
        )
        ht = semantic_thickness / 2
        _wall_ann_indices.append(i)
        _wall_resolver_widths.append(semantic_thickness)
        _wall_draw_widths.append(draw_width)

        is_diag = _is_diagonal(wx2 - wx1, wy2 - wy1)
        _wall_is_diagonal.append(is_diag)

        if not is_diag:
            is_h = adx >= ady
            _wall_original_spans.append(
                (
                    "horizontal" if is_h else "vertical",
                    (wy1 + wy2) / 2 if is_h else (wx1 + wx2) / 2,
                    min(wx1, wx2) if is_h else min(wy1, wy2),
                    max(wx1, wx2) if is_h else max(wy1, wy2),
                )
            )
            _junction_input.append({
                "orientation": "horizontal" if is_h else "vertical",
                "mid": (wy1 + wy2) / 2 if is_h else (wx1 + wx2) / 2,
                "span_lo": min(wx1, wx2) if is_h else min(wy1, wy2),
                "span_hi": max(wx1, wx2) if is_h else max(wy1, wy2),
                "half_lw": ht,
            })
            _junction_to_wall_idx.append(wall_count)
        else:
            _wall_original_spans.append(("diagonal", 0.0, 0.0, 0.0))
        wall_count += 1

    _resolved_junctions = resolve_wall_junctions(_junction_input, mode="dxf")
    # Build resolved lookup: wall_idx → resolved junction data (only for H/V walls)
    _resolved_walls: dict[int, dict] = {}
    for ji, rw in enumerate(_resolved_junctions):
        _resolved_walls[_junction_to_wall_idx[ji]] = rw

    _wall_opening_gaps = _collect_wall_opening_gaps(
        annotations,
        wall_dxf_coords=wall_dxf_coords,
        resolved_walls=_resolved_walls,
        wall_thicknesses=_wall_resolver_widths,
        image_shape=image_shape,
        transform=transform,
        fallback_wall_thickness=wall_thickness,
    )

    # Debug: log junction adjustments
    diag_count = sum(1 for d in _wall_is_diagonal if d)
    if diag_count:
        print(f"[DXF-Junction] {diag_count} diagonal wall(s) skipped from junction resolver", flush=True)
    for i, (orig, adj) in enumerate(zip(_junction_input, _resolved_junctions)):
        if orig["span_lo"] != adj["span_lo"] or orig["span_hi"] != adj["span_hi"]:
            print(f"[DXF-Junction] wall {_junction_to_wall_idx[i]} {orig['orientation']}: "
                  f"span {orig['span_lo']:.1f}..{orig['span_hi']:.1f} -> "
                  f"{adj['span_lo']:.1f}..{adj['span_hi']:.1f}", flush=True)
    if not any(o["span_lo"] != a["span_lo"] or o["span_hi"] != a["span_hi"]
               for o, a in zip(_junction_input, _resolved_junctions)):
        print(f"[DXF-Junction] NO adjustments made! {len(_junction_input)} H/V walls, "
              f"H={len([w for w in _junction_input if w['orientation']=='horizontal'])}, "
              f"V={len([w for w in _junction_input if w['orientation']=='vertical'])}", flush=True)
        for w in _junction_input[:6]:
            print(f"  {w['orientation']} mid={w['mid']:.1f} span={w['span_lo']:.1f}..{w['span_hi']:.1f} hlw={w['half_lw']:.1f}", flush=True)

    wall_idx = 0
    for ann in annotations:
        ann_type = ann.get("type", "wall")
        if ann_type == "eraser":
            continue

        dx1, dy1 = _mitunet_region_img_to_dxf(float(ann["x1"]), float(ann["y1"]), image_shape=image_shape, transform=transform)
        dx2, dy2 = _mitunet_region_img_to_dxf(float(ann["x2"]), float(ann["y2"]), image_shape=image_shape, transform=transform)

        if ann_type == "wall":
            draw_width = _wall_draw_widths[wall_idx]
            is_diag = _wall_is_diagonal[wall_idx]
            gap_segments_for_wall = _wall_opening_gaps.get(wall_idx, [])

            if not is_diag and wall_idx in _resolved_walls:
                rw = _resolved_walls[wall_idx]
                is_horiz = rw["orientation"] == "horizontal"
                original_orientation, original_mid, original_lo, original_hi = _wall_original_spans[wall_idx]
                original_len = max(0.0, float(original_hi) - float(original_lo))
                resolved_len = max(0.0, float(rw["span_hi"]) - float(rw["span_lo"]))
                preserve_original_short_span = (
                    not gap_segments_for_wall
                    and original_orientation == rw["orientation"]
                    and original_len > 0.0
                    and original_len <= float(draw_width) * 4.0
                    and resolved_len < original_len
                )
                active_mid = float(original_mid) if preserve_original_short_span else float(rw["mid"])
                active_lo = float(original_lo) if preserve_original_short_span else float(rw["span_lo"])
                active_hi = float(original_hi) if preserve_original_short_span else float(rw["span_hi"])
                gap_segments = _split_span_by_gaps(
                    active_lo,
                    active_hi,
                    gap_segments_for_wall,
                )
                for seg_lo, seg_hi in gap_segments:
                    if is_horiz:
                        _add_wall_centerline_dxf(
                            msp,
                            x1=seg_lo,
                            y1=active_mid,
                            x2=seg_hi,
                            y2=active_mid,
                            width=draw_width,
                        )
                    else:
                        _add_wall_centerline_dxf(
                            msp,
                            x1=active_mid,
                            y1=seg_lo,
                            x2=active_mid,
                            y2=seg_hi,
                            width=draw_width,
                        )
                    rect_count += 1
                wall_idx += 1
                continue

            total_len = max(abs(dx2 - dx1), abs(dy2 - dy1))
            if total_len < 0.5:
                wall_idx += 1
                continue
            ux = (dx2 - dx1) / total_len
            uy = (dy2 - dy1) / total_len
            for seg_lo, seg_hi in _split_span_by_gaps(0.0, total_len, gap_segments_for_wall):
                _add_wall_centerline_dxf(
                    msp,
                    x1=dx1 + ux * seg_lo,
                    y1=dy1 + uy * seg_lo,
                    x2=dx1 + ux * seg_hi,
                    y2=dy1 + uy * seg_hi,
                    width=draw_width,
                )
                rect_count += 1
            wall_idx += 1
            continue

        if ann_type == "door":
            adx = abs(dx2 - dx1)
            ady = abs(dy2 - dy1)
            door_width = adx if adx >= ady else ady

            if door_width < 2:
                continue

            swing = ann.get("swing") or _default_door_swing(ann.get("side"))
            if not swing:
                attribs = {"layer": "DOORS", "color": 157}
                msp.add_line((dx1, dy1), (dx2, dy2), dxfattribs=attribs)
                continue

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

            side = ann.get("side") or _window_side_from_annotation(ann)

            adx = abs(dx2 - dx1)
            ady = abs(dy2 - dy1)

            if adx >= ady:
                x_lo, x_hi = min(dx1, dx2), max(dx1, dx2)
                y_mid = (dy1 + dy2) / 2
                if side in {"bottom", "top"}:
                    edges = _find_parent_wall_edges(x_lo, x_hi, y_mid, is_horizontal=True)
                    if edges:
                        sill_target = edges[0] if side == "bottom" else edges[1]
                        y_param = sill_target + H_SILL_OFFSET if side == "bottom" else sill_target - H_SILL_OFFSET
                    else:
                        y_param = y_mid
                    draw_window_h(msp, x_lo, y_param, adx, side=side)
                else:
                    msp.add_line((x_lo, y_mid), (x_hi, y_mid), dxfattribs={"layer": "WINS", "color": 121})
            else:
                x_mid = (dx1 + dx2) / 2
                y_lo, y_hi = min(dy1, dy2), max(dy1, dy2)
                if side in {"left", "right"}:
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
                else:
                    msp.add_line((x_mid, y_lo), (x_mid, y_hi), dxfattribs={"layer": "WINS", "color": 121})

    return rect_count


def _resolve_wall_draw_width_dxf(
    annotation: dict[str, Any],
    *,
    transform: dict[str, float],
    fallback_width: float,
) -> float:
    detected_width_px = float(annotation.get("_mean_width_px", 0.0) or 0.0)
    if detected_width_px <= 0.0:
        detected_width_px = _polygon_short_edge_width(annotation.get("polygon"))
    scale = float(transform.get("scale", 1.0) or 1.0)
    if detected_width_px > 0.0:
        return max(detected_width_px * scale, 1.0)
    return max(float(fallback_width), 1.0)


def _add_wall_centerline_dxf(
    msp: Any,
    *,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    width: float,
) -> None:
    if math.hypot(float(x2) - float(x1), float(y2) - float(y1)) <= 1e-6:
        return
    msp.add_lwpolyline(
        [(float(x1), float(y1)), (float(x2), float(y2))],
        dxfattribs={"layer": "WALLS", "color": 7, "const_width": max(float(width), 1.0)},
    )


def _restore_overcollapsed_snapped_walls(
    original_coords: list[tuple[float, float, float, float]],
    snapped_coords: list[tuple[float, float, float, float]],
    *,
    tolerance: float,
) -> list[tuple[float, float, float, float]]:
    if not original_coords or len(original_coords) != len(snapped_coords):
        return list(snapped_coords)

    restored: list[tuple[float, float, float, float]] = []
    restored_count = 0
    max_guarded_len = max(float(tolerance), 1.0) * 2.0
    for original, snapped in zip(original_coords, snapped_coords):
        orig_len = max(abs(float(original[2]) - float(original[0])), abs(float(original[3]) - float(original[1])))
        snap_len = max(abs(float(snapped[2]) - float(snapped[0])), abs(float(snapped[3]) - float(snapped[1])))
        preserve_original = (
            orig_len > 0.5
            and orig_len <= max_guarded_len
            and snap_len < max(0.5, orig_len * 0.5)
        )
        if preserve_original:
            restored.append(original)
            restored_count += 1
            continue
        restored.append(snapped)

    if restored_count:
        print(f"[DXF-Snap] Restored {restored_count} short wall(s) after over-collapsed endpoint clustering", flush=True)

    return restored


def _polygon_short_edge_width(polygon: Any) -> float:
    if not isinstance(polygon, list) or len(polygon) < 4:
        return 0.0
    points: list[tuple[float, float]] = []
    for raw_point in polygon:
        if not isinstance(raw_point, dict):
            return 0.0
        try:
            points.append((float(raw_point["x"]), float(raw_point["y"])))
        except (KeyError, TypeError, ValueError):
            return 0.0
    edges: list[float] = []
    for index, start in enumerate(points):
        end = points[(index + 1) % len(points)]
        length = math.hypot(end[0] - start[0], end[1] - start[1])
        if length > 0.0:
            edges.append(length)
    if not edges:
        return 0.0
    return min(edges)


def _collect_wall_opening_gaps(
    annotations: list[dict[str, Any]],
    *,
    wall_dxf_coords: list[tuple[float, float, float, float]],
    resolved_walls: dict[int, dict[str, Any]],
    wall_thicknesses: list[float],
    image_shape: tuple[int, int],
    transform: dict[str, float],
    fallback_wall_thickness: float,
) -> dict[int, list[tuple[float, float]]]:
    gaps_by_wall: dict[int, list[tuple[float, float]]] = defaultdict(list)

    for ann in annotations:
        if ann.get("type") not in {"door", "window"}:
            continue

        dx1, dy1 = _mitunet_region_img_to_dxf(float(ann["x1"]), float(ann["y1"]), image_shape=image_shape, transform=transform)
        dx2, dy2 = _mitunet_region_img_to_dxf(float(ann["x2"]), float(ann["y2"]), image_shape=image_shape, transform=transform)
        adx = abs(dx2 - dx1)
        ady = abs(dy2 - dy1)
        orientation = "horizontal" if adx >= ady else "vertical"
        opening_lo = min(dx1, dx2) if orientation == "horizontal" else min(dy1, dy2)
        opening_hi = max(dx1, dx2) if orientation == "horizontal" else max(dy1, dy2)
        opening_mid = (dy1 + dy2) / 2 if orientation == "horizontal" else (dx1 + dx2) / 2

        best_wall_idx = None
        best_score = -1.0
        for wall_idx, coords in enumerate(wall_dxf_coords):
            if wall_idx not in resolved_walls:
                continue
            wall = resolved_walls[wall_idx]
            if wall.get("orientation") != orientation:
                continue

            thickness = wall_thicknesses[wall_idx] if wall_idx < len(wall_thicknesses) else fallback_wall_thickness
            tolerance = max(float(thickness), float(fallback_wall_thickness)) * 1.5
            wall_lo = float(wall["span_lo"])
            wall_hi = float(wall["span_hi"])
            wall_mid = float(wall["mid"])
            if abs(wall_mid - opening_mid) > tolerance:
                continue

            overlap_lo = max(opening_lo, wall_lo)
            overlap_hi = min(opening_hi, wall_hi)
            overlap = overlap_hi - overlap_lo
            if overlap <= 0:
                continue

            opening_span = max(1.0, opening_hi - opening_lo)
            score = overlap / opening_span
            if score > best_score:
                best_score = score
                best_wall_idx = wall_idx

        if best_wall_idx is None:
            continue

        wall = resolved_walls[best_wall_idx]
        gap_lo = max(opening_lo, float(wall["span_lo"]))
        gap_hi = min(opening_hi, float(wall["span_hi"]))
        if gap_hi - gap_lo >= 1.0:
            gaps_by_wall[best_wall_idx].append((gap_lo, gap_hi))

    return {
        wall_idx: _merge_gap_intervals(intervals)
        for wall_idx, intervals in gaps_by_wall.items()
    }


def _merge_gap_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not intervals:
        return []
    ordered = sorted((float(lo), float(hi)) for lo, hi in intervals if hi - lo > 0.0)
    merged: list[tuple[float, float]] = []
    current_lo, current_hi = ordered[0]
    for lo, hi in ordered[1:]:
        if lo <= current_hi + 0.5:
            current_hi = max(current_hi, hi)
            continue
        merged.append((current_lo, current_hi))
        current_lo, current_hi = lo, hi
    merged.append((current_lo, current_hi))
    return merged


def _split_span_by_gaps(
    span_lo: float,
    span_hi: float,
    gaps: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    if not gaps:
        return [(span_lo, span_hi)]

    segments: list[tuple[float, float]] = []
    cursor = float(span_lo)
    for gap_lo, gap_hi in gaps:
        clipped_lo = max(float(span_lo), float(gap_lo))
        clipped_hi = min(float(span_hi), float(gap_hi))
        if clipped_hi - clipped_lo <= 0.0:
            continue
        if clipped_lo - cursor >= 0.5:
            segments.append((cursor, clipped_lo))
        cursor = max(cursor, clipped_hi)
    if float(span_hi) - cursor >= 0.5:
        segments.append((cursor, float(span_hi)))
    return segments or [(span_lo, span_hi)]


def _default_door_swing(side: str | None) -> str | None:
    return {
        "bottom": "up",
        "top": "down",
        "left": "right",
        "right": "left",
    }.get(side)


def _window_side_from_annotation(annotation: dict[str, Any]) -> str | None:
    side = annotation.get("side")
    if side in {"bottom", "top", "left", "right"}:
        return side
    swing = annotation.get("swing")
    return {
        "up": "bottom",
        "down": "top",
        "left": "left",
        "right": "right",
    }.get(swing)


