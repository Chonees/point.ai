from __future__ import annotations

import backend.components.dimensions as _dims_pkg

from ezdxf.enums import TextEntityAlignment

from .coord_transform import CoordTransform, ROOM_NAME_HEIGHT, ROOM_DIM_HEIGHT
from .exterior import _plan_width_dxf
from .room_metrics import _label_room_metrics


def _label_sizes(plan_width_dxf: float) -> tuple[float, float, float]:
    name_h = plan_width_dxf * (ROOM_NAME_HEIGHT / 1300.0)
    dim_h = plan_width_dxf * (ROOM_DIM_HEIGHT / 1300.0)
    spacing = plan_width_dxf * (5.0 / 1300.0)
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
        _dims_pkg.log_event(
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
            _dims_pkg.log_event("room_size_label_added", room_name=room_name, dims_text=dims_text)

        if sqft_value is not None:
            sqft_y = dy - (label_spacing * 1.2 if dims_text else label_spacing * 0.3)
            sqft_text = msp.add_text(
                f"{int(round(float(sqft_value)))} SQ FT",
                dxfattribs={"layer": "ROOM LBLS", "height": dim_h},
            )
            sqft_text.set_placement((dx, sqft_y), align=TextEntityAlignment.MIDDLE_CENTER)
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
