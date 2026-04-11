from __future__ import annotations

import numpy as np

import backend.components.dimensions as _dims_pkg


def _span_containing_seed(line: np.ndarray, seed_index: int) -> tuple[int, int] | None:
    if seed_index < 0 or seed_index >= len(line) or not bool(line[seed_index]):
        return None

    start = int(seed_index)
    end = int(seed_index)
    while start > 0 and bool(line[start - 1]):
        start -= 1
    while end + 1 < len(line) and bool(line[end + 1]):
        end += 1
    return start, end


def _best_local_seedline_span(
    room_mask: np.ndarray,
    *,
    seed_x: int,
    seed_y: int,
    axis: str,
    band: int,
) -> tuple[int, int] | None:
    best_span: tuple[int, int] | None = None
    best_length = -1
    best_distance = float("inf")

    if axis == "H":
        start = max(0, seed_y - band)
        end = min(room_mask.shape[0] - 1, seed_y + band)
        for y in range(start, end + 1):
            span = _span_containing_seed(room_mask[y, :], seed_x)
            if span is None:
                continue
            length = span[1] - span[0]
            distance = abs(y - seed_y)
            if length > best_length or (length == best_length and distance < best_distance):
                best_span = span
                best_length = length
                best_distance = distance
        return best_span

    start = max(0, seed_x - band)
    end = min(room_mask.shape[1] - 1, seed_x + band)
    for x in range(start, end + 1):
        span = _span_containing_seed(room_mask[:, x], seed_y)
        if span is None:
            continue
        length = span[1] - span[0]
        distance = abs(x - seed_x)
        if length > best_length or (length == best_length and distance < best_distance):
            best_span = span
            best_length = length
            best_distance = distance
    return best_span


def _label_room_metrics(
    annotations: list[dict],
    wall_mask,
    image_shape: tuple[int, int],
    label: dict,
    scale_ipp: float,
    room_context: dict[str, object] | None = None,
) -> str | None:
    from ...measurement.flood_fill import flood_fill_room_region
    from ...measurement.calibration import inches_to_feet_inches

    if wall_mask is None or scale_ipp <= 0:
        _dims_pkg.log_event(
            "room_metric_skipped",
            room_name=label.get("roomName"),
            reason="missing_wall_mask_or_scale",
            scale_ipp=scale_ipp,
        )
        return None

    region = room_context["region"] if room_context and room_context.get("region") is not None else flood_fill_room_region(
        annotations,
        wall_mask,
        image_shape,
        int(float(label["x1"])),
        int(float(label["y1"])),
    )
    if not region:
        _dims_pkg.log_event(
            "room_metric_skipped",
            room_name=label.get("roomName"),
            reason="room_region_not_found",
        )
        return None

    room_mask = region["mask"]
    seed_x, seed_y = region["seed"]
    bbox_x1, bbox_y1, bbox_x2, bbox_y2 = region["bbox"]
    sample_band = max(12, min(30, int(min(bbox_x2 - bbox_x1, bbox_y2 - bbox_y1) * 0.25)))
    horizontal_span = _best_local_seedline_span(
        room_mask,
        seed_x=seed_x,
        seed_y=seed_y,
        axis="H",
        band=sample_band,
    )
    vertical_span = _best_local_seedline_span(
        room_mask,
        seed_x=seed_x,
        seed_y=seed_y,
        axis="V",
        band=sample_band,
    )
    if horizontal_span is None or vertical_span is None:
        _dims_pkg.log_event(
            "room_metric_skipped",
            room_name=label.get("roomName"),
            reason="seedline_span_not_found",
            seed={"x": seed_x, "y": seed_y},
            sample_band=sample_band,
        )
        return None

    hx1, hx2 = horizontal_span
    vy1, vy2 = vertical_span
    room_w_in = abs(hx2 - hx1) * scale_ipp
    room_h_in = abs(vy2 - vy1) * scale_ipp
    if room_w_in < 1 or room_h_in < 1:
        _dims_pkg.log_event(
            "room_metric_skipped",
            room_name=label.get("roomName"),
            reason="seedline_span_too_small",
            horizontal_span={"x1": hx1, "x2": hx2},
            vertical_span={"y1": vy1, "y2": vy2},
            room_w_in=round(room_w_in, 4),
            room_h_in=round(room_h_in, 4),
        )
        return None

    length_in = max(room_w_in, room_h_in)
    width_in = min(room_w_in, room_h_in)
    dims_text = f"{inches_to_feet_inches(length_in)} x {inches_to_feet_inches(width_in)}"
    _dims_pkg.log_event(
        "room_metric_computed",
        room_name=label.get("roomName"),
        measurement_method="seedline_face_to_face",
        seed={"x": seed_x, "y": seed_y},
        sample_band=sample_band,
        horizontal_span={"x1": hx1, "x2": hx2},
        vertical_span={"y1": vy1, "y2": vy2},
        room_w_in=round(room_w_in, 4),
        room_h_in=round(room_h_in, 4),
        dims_text=dims_text,
        scale_ipp=round(scale_ipp, 6),
    )
    return dims_text
