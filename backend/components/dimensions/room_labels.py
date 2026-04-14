from __future__ import annotations

import math

import backend.components.dimensions as _dims_pkg

from ezdxf.enums import TextEntityAlignment

from .coord_transform import CoordTransform, ROOM_NAME_HEIGHT_PX, ROOM_DIM_HEIGHT_PX
from .exterior import _plan_width_dxf
from .room_metrics import _label_room_metrics


def _rotate_offset(ox: float, oy: float, cos_r: float, sin_r: float) -> tuple[float, float]:
    """Rotate a 2D offset by the precomputed cos/sin of the angle."""
    return (ox * cos_r - oy * sin_r, ox * sin_r + oy * cos_r)


def _label_sizes(plan_width_dxf: float, t_scale: float = 0.0) -> tuple[float, float, float]:
    """Text heights for room labels in DXF units.

    When ``t_scale`` is provided, sizes are computed from the 2D-editor pixel
    sizes × ``t_scale`` for a 1:1 proportional match. Falls back to a
    plan-width ratio otherwise.
    """
    if t_scale > 0.001:
        name_h = ROOM_NAME_HEIGHT_PX * t_scale
        dim_h = ROOM_DIM_HEIGHT_PX * t_scale
        spacing = 5.0 * t_scale
    else:
        name_h = plan_width_dxf * (ROOM_NAME_HEIGHT_PX / 800.0)
        dim_h = plan_width_dxf * (ROOM_DIM_HEIGHT_PX / 800.0)
        spacing = plan_width_dxf * (5.0 / 800.0)
    return name_h, dim_h, spacing


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

    name_h, dim_h, label_spacing = _label_sizes(plan_width_dxf, t_scale=ct.t_scale)
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

        # Per-label transform: scale + rotation set by the user in the 2D editor.
        # Canvas rotation is clockwise (Y-down); DXF rotation is counter-clockwise (Y-up),
        # so we negate the angle when converting.
        label_scale = float(label.get("labelScale") or 1.0)
        canvas_rot = float(label.get("labelRotation") or 0.0)
        dxf_rot_rad = -canvas_rot
        rotation_deg = math.degrees(dxf_rot_rad)
        cos_r = math.cos(dxf_rot_rad)
        sin_r = math.sin(dxf_rot_rad)

        scaled_name_h = name_h * label_scale
        scaled_dim_h = dim_h * label_scale
        scaled_spacing = label_spacing * label_scale

        # Room name — offset (0, spacing) in local space (up), then rotated
        name_ox, name_oy = _rotate_offset(0.0, scaled_spacing, cos_r, sin_r)
        name_text = msp.add_text(
            room_name,
            dxfattribs={"layer": "ROOM LBLS", "height": scaled_name_h, "rotation": rotation_deg},
        )
        name_text.set_placement((dx + name_ox, dy + name_oy), align=TextEntityAlignment.MIDDLE_CENTER)
        counts["room_labels"] += 1
        _dims_pkg.log_event(
            "room_label_added",
            room_name=room_name,
            anchor_px={"x": round(lx, 4), "y": round(ly, 4)},
            anchor_dxf={"x": round(dx, 4), "y": round(dy, 4)},
            sqft=round(sqft_value, 4) if sqft_value is not None else None,
            sqft_source=sqft_source if sqft_value is not None else None,
            label_scale=round(label_scale, 4),
            label_rotation_deg=round(rotation_deg, 2),
        )

        dims_text = _label_room_metrics(annotations, wall_mask, image_shape, label, scale_ipp, room_context=room_context)
        if dims_text:
            dims_ox, dims_oy = _rotate_offset(0.0, -scaled_spacing * 0.3, cos_r, sin_r)
            dims_label = msp.add_text(
                dims_text,
                dxfattribs={"layer": "ROOM LBLS", "height": scaled_dim_h, "rotation": rotation_deg},
            )
            dims_label.set_placement((dx + dims_ox, dy + dims_oy), align=TextEntityAlignment.MIDDLE_CENTER)
            counts["room_size_labels"] += 1
            _dims_pkg.log_event("room_size_label_added", room_name=room_name, dims_text=dims_text)

        if sqft_value is not None:
            sqft_local_y = -(scaled_spacing * 1.2 if dims_text else scaled_spacing * 0.3)
            sqft_ox, sqft_oy = _rotate_offset(0.0, sqft_local_y, cos_r, sin_r)
            sqft_text = msp.add_text(
                f"{int(round(float(sqft_value)))} SQ FT",
                dxfattribs={"layer": "ROOM LBLS", "height": scaled_dim_h, "rotation": rotation_deg},
            )
            sqft_text.set_placement((dx + sqft_ox, dy + sqft_oy), align=TextEntityAlignment.MIDDLE_CENTER)
            counts["sqft_labels"] += 1
            _dims_pkg.log_event(
                "room_sqft_label_added",
                room_name=room_name,
                sqft=int(round(float(sqft_value))),
                sqft_source=sqft_source,
                duplicate_of_index=room_context.get("duplicate_of_index") if room_context else None,
                overlap_area_px=room_context.get("overlap_area_px") if room_context else None,
            )

    return counts
