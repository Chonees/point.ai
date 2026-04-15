from __future__ import annotations

from typing import Any

from ..provenance import build_code_provenance, build_file_provenance, utc_now_iso
from .annotations import _draw_mitunet_annotations_from_region_plan
from .junctions import resolve_wall_junctions
from .model import (
    MITUNET_BACKEND,
    MITUNET_MASK_REGIONS_DXF_MODE,
    MITUNET_MODEL_NAME,
    _TEMPLATE_PATH,
    _WEIGHTS_PATH,
)


def build_mitunet_provenance(*, dxf_mode: str = MITUNET_MASK_REGIONS_DXF_MODE) -> dict[str, Any]:
    return {
        "captured_at_utc": utc_now_iso(),
        "backend": MITUNET_BACKEND,
        "model_variant": "mitunet",
        "model_name": MITUNET_MODEL_NAME,
        "dxf_mode": dxf_mode,
        "region_contract_version": "mitunet_region_plan_v1",
        "max_region_wall_thickness": float(6.0),
        "code": build_code_provenance(),
        "weights": build_file_provenance(_WEIGHTS_PATH),
        "template": build_file_provenance(_TEMPLATE_PATH),
    }


def _load_mitunet_template_doc():
    import ezdxf

    if _TEMPLATE_PATH.exists():
        return ezdxf.readfile(str(_TEMPLATE_PATH))
    return ezdxf.new("R2010")


def _add_dims_and_labels(doc, msp, annotations, wall_mask, image_shape, transform, img_h, *, total_area_sqft: float | None = None) -> dict | None:
    """Render room labels + sqft + dimension annotations into the DXF.

    Dimension rendering is driven by annotations with ``type='dimension'``.
    The service layer (``generate_dxf_service``) computes those upstream from
    walls + windows + scale_ipp and appends them to the annotations list
    before calling us, so here we just export each one as a DIMLINEAR via
    ``render_dimensions_to_dxf``. This is the "dumb exporter" path — what
    you see in the 2D editor is what gets written to the DXF.

    Returns a dict with ``computed_rooms``, ``region_overlay``, and
    ``scale_ipp`` (when calibration succeeded).
    """
    try:
        from ..scale_calibrator import calibrate_scale, generate_region_overlay, encode_overlay_png
        from ..components.dimensions import (
            CoordTransform,
            _classify_annotations,
            _ensure_layers,
            _plan_width_dxf,
            _render_manual_room_labels,
            render_dimensions_to_dxf,
        )
        from ..observability import log_event

        has_labels = any(a.get("type") == "label" for a in annotations)
        has_dimensions = any(a.get("type") == "dimension" for a in annotations)
        if not has_labels and not has_dimensions:
            log_event("dims_pipeline_skipped", reason="no_labels_no_dimensions")
            return None

        has_sqft = any(a.get("type") == "label" and a.get("sqft") for a in annotations)
        has_total_area = total_area_sqft is not None and float(total_area_sqft) > 0
        want_calibration = bool(has_labels and (has_total_area or has_sqft) and wall_mask is not None)

        scale_ipp = 1.0
        measurement_context = None
        if want_calibration:
            measurement_context = calibrate_scale(
                annotations,
                wall_mask,
                image_shape,
                total_area_sqft=float(total_area_sqft) if has_total_area else None,
            )
            if measurement_context is not None:
                scale_ipp = float(measurement_context["scale_ipp"])

        log_event(
            "dims_pipeline_start",
            label_count=sum(1 for a in annotations if a.get("type") == "label"),
            dimension_count=sum(1 for a in annotations if a.get("type") == "dimension"),
            has_sqft=has_sqft,
            has_total_area=has_total_area,
            total_area_sqft=round(float(total_area_sqft), 4) if has_total_area else None,
            wall_mask_present=wall_mask is not None,
            scale_ipp=round(scale_ipp, 6),
            calibration_mode=measurement_context["calibration_mode"] if measurement_context else None,
        )

        _ensure_layers(doc)
        ct = CoordTransform(image_shape, transform, scale_ipp)
        classified = _classify_annotations(annotations)
        plan_width_dxf = _plan_width_dxf(ct, classified["wall"])

        counts: dict[str, int] = {}
        if has_labels:
            counts.update(_render_manual_room_labels(
                msp, ct, annotations, classified["label"], wall_mask, image_shape,
                plan_width_dxf, scale_ipp if want_calibration else 0.0,
                measurement_context=measurement_context,
            ))

        dim_annotations = [a for a in annotations if a.get("type") == "dimension"]
        counts["dimensions"] = render_dimensions_to_dxf(
            doc, msp, dim_annotations, image_shape, transform,
            plan_width_hint=plan_width_dxf,
        )

        total = sum(counts.values())
        log_event("dims_pipeline_done", total=total, counts=counts)
        print(f"[DIMS] Generated {total} elements: {counts}", flush=True)

        # Extract computed rooms + region overlay for the API response
        result: dict = {}
        if measurement_context:
            result["scale_ipp"] = scale_ipp
        if measurement_context and "room_analysis" in measurement_context:
            room_analysis = measurement_context["room_analysis"]
            rooms = room_analysis.get("rooms", [])
            computed = []
            for room in rooms:
                if room.get("computed_sqft") is not None:
                    label = room.get("label", {})
                    computed.append({
                        "roomName": str(room.get("room_name") or label.get("roomName", "ROOM")).upper(),
                        "sqft": round(float(room["computed_sqft"])),
                        "x1": float(label.get("x1", 0)),
                        "y1": float(label.get("y1", 0)),
                    })
            if computed:
                result["computed_rooms"] = computed

            # Generate colored region overlay
            overlay = generate_region_overlay(room_analysis, image_shape)
            overlay_b64 = encode_overlay_png(overlay)
            if overlay_b64:
                result["region_overlay"] = overlay_b64

        return result if result else None

    except Exception:
        import traceback
        traceback.print_exc()
        return None



def generate_mitunet_region_dxf(
    region_plan: dict[str, Any],
    out_path: str,
    *,
    annotations: list[dict] | None = None,
    skip_regions: bool = False,
    total_area_sqft: float | None = None,
) -> tuple[int, dict | None]:
    doc = _load_mitunet_template_doc()
    msp = doc.modelspace()

    if "WALLS" not in doc.layers:
        doc.layers.add("WALLS", color=7, dxfattribs={"lineweight": 100})
    else:
        doc.layers.get("WALLS").dxf.lineweight = 60

    rect_count = 0
    region_thicknesses: list[float] = []

    def _snap_thickness(raw: float) -> float:
        """Snap detected thickness to standard: 4" (interior) or 6" (exterior)."""
        return 6.0 if raw >= 5.0 else 4.0

    if not skip_regions:
        # --- Phase 1: collect snapped regions ---
        snapped: list[dict] = []
        for region in region_plan.get("regions", []):
            bounds = region.get("bounds") or {}
            x1 = float(bounds.get("x1", 0.0))
            y1 = float(bounds.get("y1", 0.0))
            x2 = float(bounds.get("x2", 0.0))
            y2 = float(bounds.get("y2", 0.0))
            if abs(x2 - x1) < 1 or abs(y2 - y1) < 1:
                continue

            dt = float(region.get("draw_thickness", 4.0))
            std = _snap_thickness(dt)
            orientation = region.get("orientation", "horizontal")
            if orientation == "horizontal":
                cy = (y1 + y2) / 2
                y1, y2 = cy - std / 2, cy + std / 2
            else:
                cx = (x1 + x2) / 2
                x1, x2 = cx - std / 2, cx + std / 2

            snapped.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2,
                            "orientation": orientation, "std": std})

        # --- Phase 2: resolve junctions (L-corners + T-junctions) ---
        junction_input = []
        for reg in snapped:
            ori = reg["orientation"]
            if ori == "horizontal":
                junction_input.append({
                    "orientation": "horizontal",
                    "mid": (reg["y1"] + reg["y2"]) / 2,
                    "span_lo": reg["x1"],
                    "span_hi": reg["x2"],
                    "half_lw": reg["std"] / 2,
                })
            else:
                junction_input.append({
                    "orientation": "vertical",
                    "mid": (reg["x1"] + reg["x2"]) / 2,
                    "span_lo": reg["y1"],
                    "span_hi": reg["y2"],
                    "half_lw": reg["std"] / 2,
                })

        resolved = resolve_wall_junctions(junction_input, mode="dxf")

        for reg, adj in zip(snapped, resolved):
            if reg["orientation"] == "horizontal":
                reg["x1"] = adj["span_lo"]
                reg["x2"] = adj["span_hi"]
            else:
                reg["y1"] = adj["span_lo"]
                reg["y2"] = adj["span_hi"]

        # --- Phase 3: draw regions ---
        from ..components.hatch import add_wall_hatch

        for reg in snapped:
            x1, y1, x2, y2 = reg["x1"], reg["y1"], reg["x2"], reg["y2"]
            if x2 - x1 < 0.5 or y2 - y1 < 0.5:
                continue  # degenerate after L-corner trim
            std = reg["std"]
            pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]
            poly = msp.add_lwpolyline(pts, dxfattribs={"layer": "WALLS", "color": 7, "lineweight": 100})
            poly.close()
            add_wall_hatch(msp, doc, pts, std)
            rect_count += 1
            region_thicknesses.append(std)

    # Median standard thickness for manual wall annotations
    if region_thicknesses:
        region_thicknesses.sort()
        mid = len(region_thicknesses) // 2
        median_thickness = region_thicknesses[mid] if len(region_thicknesses) % 2 else (region_thicknesses[mid - 1] + region_thicknesses[mid]) / 2
    else:
        median_thickness = 4.0

    meta = region_plan.get("meta", {})
    image_shape_meta = meta.get("image_shape", {})
    image_shape = (
        int(image_shape_meta.get("height", 0)),
        int(image_shape_meta.get("width", 0)),
    )
    rect_count += _draw_mitunet_annotations_from_region_plan(
        msp,
        doc,
        annotations,
        image_shape=image_shape,
        transform=meta.get("transform", {}),
        wall_thickness=median_thickness,
        regions=region_plan.get("regions", []),
    )

    # --- Dimensions + room labels from label annotations ---
    dims_result = None
    if annotations:
        wall_mask = region_plan.get("meta", {}).get("_wall_mask")
        transform = meta.get("transform", {})
        img_h = image_shape[0]

        dims_result = _add_dims_and_labels(
            doc,
            msp,
            annotations,
            wall_mask,
            image_shape,
            transform,
            img_h,
            total_area_sqft=total_area_sqft,
        )

    # --- Wall Legend ---
    from ..components.wall_legend import add_wall_legend

    # Place legend inside the title-block frame (top-right corner, inset)
    plan_x2 = float(meta.get("transform", {}).get("plan_x2", 1530))
    plan_y2 = float(meta.get("transform", {}).get("plan_y2", 1080))
    legend_x = plan_x2 - 180
    legend_y = plan_y2 - 30

    add_wall_legend(msp, doc, legend_x, legend_y)

    doc.saveas(out_path)
    return rect_count, dims_result
