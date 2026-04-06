from __future__ import annotations

import backend.components.dimensions as _dims_pkg

from .audit import _make_audit_summary, _log_audit_summary
from .coord_transform import CoordTransform, setup_dim_style, _ensure_layers, FIRST_CHAIN_OFFSET
from .exterior import (
    _classify_annotations,
    _plan_width_dxf,
    _extract_exterior_segments_from_wall_mask,
    _annotation_exterior_segments,
    _building_centroid_from_segments,
    _building_centroid_px,
    _assign_windows_to_segments,
    _opening_centerline,
    _add_dim_along_wall,
)
from .formatting import _fmt_inches, _audit_dim_status
from .room_labels import _render_manual_room_labels


def generate_all_dimensions(
    doc,
    msp,
    annotations: list[dict],
    scale_ipp: float,
    image_shape: tuple[int, int],
    transform: dict,
    wall_mask=None,
    render_dimensions: bool = True,
    measurement_context: dict[str, object] | None = None,
) -> dict[str, int]:
    _ensure_layers(doc)
    ct = CoordTransform(image_shape, transform, scale_ipp)
    classified = _classify_annotations(annotations)
    plan_width_dxf = _plan_width_dxf(ct, classified["wall"])
    _dims_pkg.log_event(
        "dims_generation_start",
        annotation_counts={key: len(value) for key, value in classified.items()},
        render_dimensions=render_dimensions,
        scale_ipp=round(scale_ipp, 6),
        plan_width_dxf=round(plan_width_dxf, 4),
        calibration_mode=measurement_context.get("calibration_mode") if measurement_context else None,
    )

    counts = {
        "window_center_dims": 0,
        "exterior_wall_dims": 0,
        "room_labels": 0,
        "room_size_labels": 0,
        "sqft_labels": 0,
    }
    audit_summary = _make_audit_summary()
    if measurement_context:
        room_analysis = measurement_context.get("room_analysis", {})
        audit_summary["overlapping_label_count"] = int(room_analysis.get("overlapping_label_count", 0))
        audit_summary["duplicated_region_count"] = int(room_analysis.get("duplicated_region_count", 0))
    counts.update(
        _render_manual_room_labels(
            msp,
            ct,
            annotations,
            classified["label"],
            wall_mask,
            image_shape,
            plan_width_dxf,
            scale_ipp if render_dimensions else 0.0,
            measurement_context=measurement_context,
        )
    )

    if not render_dimensions or not classified["wall"]:
        _dims_pkg.log_event(
            "dims_generation_done",
            reason="labels_only" if not render_dimensions else "no_walls",
            counts=counts,
        )
        return counts

    dimstyle = setup_dim_style(doc, ct.dimlfac, plan_width_dxf)
    exterior_segments = _extract_exterior_segments_from_wall_mask(annotations, wall_mask, image_shape)
    if not exterior_segments:
        exterior_segments = _annotation_exterior_segments(classified["wall"])
    centroid_px = _building_centroid_from_segments(exterior_segments) or _building_centroid_px(classified["wall"])
    windows_by_segment = _assign_windows_to_segments(classified["window"], exterior_segments)
    window_offset = plan_width_dxf * (FIRST_CHAIN_OFFSET / 1300.0)
    wall_offset = window_offset * 2
    _dims_pkg.log_event(
        "dims_exterior_setup",
        exterior_wall_count=len(exterior_segments),
        window_offset_dxf=round(window_offset, 4),
        wall_offset_dxf=round(wall_offset, 4),
        centroid_px={"x": round(centroid_px[0], 4), "y": round(centroid_px[1], 4)},
        segment_sources=sorted({str(segment["source"]) for segment in exterior_segments}),
    )

    for index, segment in enumerate(exterior_segments):
        orientation = str(segment["orientation"])
        wall_start = float(segment["start"])
        wall_end = float(segment["end"])
        wall_coord = float(segment["coord"])

        wall_length_px = abs(wall_end - wall_start)
        wall_length_in = wall_length_px * scale_ipp

        if orientation == "H":
            outward = -1 if wall_coord > centroid_px[1] else 1
        else:
            outward = 1 if wall_coord > centroid_px[0] else -1

        _add_dim_along_wall(
            msp,
            ct,
            orientation,
            wall_coord,
            wall_start,
            wall_end,
            outward,
            wall_offset,
            dimstyle,
            _fmt_inches(wall_length_in),
        )
        counts["exterior_wall_dims"] += 1
        _dims_pkg.log_event(
            "exterior_wall_dim_added",
            source=segment["source"],
            orientation=orientation,
            wall_coord_px=round(wall_coord, 4),
            start_px=round(wall_start, 4),
            end_px=round(wall_end, 4),
            wall_length_px=round(wall_length_px, 4),
            wall_length_in=round(wall_length_in, 4),
            wall_length_arch=_fmt_inches(wall_length_in),
        )

        windows_on_wall = windows_by_segment.get(index, [])
        _dims_pkg.log_event(
            "exterior_wall_window_scan",
            source=segment["source"],
            orientation=orientation,
            wall_coord_px=round(wall_coord, 4),
            window_count=len(windows_on_wall),
        )
        if not windows_on_wall:
            audit_summary["windowless_wall_totals"] += 1
            continue

        chain_points = [wall_start]
        chain_points.extend(sorted(_opening_centerline(window, orientation) for window in windows_on_wall))
        chain_points.append(wall_end)
        _dims_pkg.log_event(
            "window_center_chain_points",
            orientation=orientation,
            wall_coord_px=round(wall_coord, 4),
            chain_points=[round(point, 4) for point in chain_points],
        )

        generated_chain_sum_px = 0.0
        generated_chain_sum_in = 0.0
        skipped_chain_gap_px = 0.0
        skipped_chain_gap_in = 0.0
        generated_segment_count = 0
        for i in range(len(chain_points) - 1):
            p1 = chain_points[i]
            p2 = chain_points[i + 1]
            segment_px = abs(p2 - p1)
            segment_in = segment_px * scale_ipp
            if segment_px < 2:
                skipped_chain_gap_px += segment_px
                skipped_chain_gap_in += segment_in
                continue
            generated_chain_sum_px += segment_px
            generated_chain_sum_in += segment_in
            generated_segment_count += 1
            _add_dim_along_wall(
                msp,
                ct,
                orientation,
                wall_coord,
                p1,
                p2,
                outward,
                window_offset,
                dimstyle,
                _fmt_inches(segment_in),
            )
            counts["window_center_dims"] += 1
            _dims_pkg.log_event(
                "window_center_dim_added",
                orientation=orientation,
                wall_coord_px=round(wall_coord, 4),
                start_px=round(p1, 4),
                end_px=round(p2, 4),
                segment_px=round(segment_px, 4),
                segment_in=round(segment_in, 4),
                segment_arch=_fmt_inches(segment_in),
            )

        geometry_closure_error_px = abs(wall_length_px - (generated_chain_sum_px + skipped_chain_gap_px))
        geometry_closure_error_in = abs(wall_length_in - (generated_chain_sum_in + skipped_chain_gap_in))
        generated_gap_px = abs(wall_length_px - generated_chain_sum_px)
        generated_gap_in = abs(wall_length_in - generated_chain_sum_in)
        audit_status = _audit_dim_status(
            geometry_closure_error_px=geometry_closure_error_px,
            generated_gap_px=generated_gap_px,
        )
        audit_summary["audited_window_chains"] += 1
        audit_summary[f"window_chain_{audit_status}"] += 1
        audit_summary["max_generated_gap_px"] = max(audit_summary["max_generated_gap_px"], generated_gap_px)
        audit_summary["max_generated_gap_in"] = max(audit_summary["max_generated_gap_in"], generated_gap_in)
        audit_summary["max_geometry_closure_error_px"] = max(
            audit_summary["max_geometry_closure_error_px"],
            geometry_closure_error_px,
        )
        audit_summary["max_geometry_closure_error_in"] = max(
            audit_summary["max_geometry_closure_error_in"],
            geometry_closure_error_in,
        )
        _dims_pkg.log_event(
            "window_chain_audit",
            source=segment["source"],
            orientation=orientation,
            wall_coord_px=round(wall_coord, 4),
            wall_length_arch=_fmt_inches(wall_length_in),
            generated_segment_count=generated_segment_count,
            generated_chain_sum_arch=_fmt_inches(generated_chain_sum_in),
            skipped_gap_arch=_fmt_inches(skipped_chain_gap_in),
            generated_gap_arch=_fmt_inches(generated_gap_in),
            generated_gap_px=round(generated_gap_px, 4),
            geometry_closure_error_px=round(geometry_closure_error_px, 4),
            geometry_closure_error_in=round(geometry_closure_error_in, 4),
            status=audit_status,
        )

    _log_audit_summary(audit_summary, measurement_context)
    _dims_pkg.log_event("dims_generation_done", reason="full", counts=counts)
    return counts
