from __future__ import annotations

from pathlib import Path
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


def generate_mitunet_dxf(infer_result: dict[str, Any], out_path: str,
                         annotations: list[dict] | None = None) -> int:
    """Legacy entrypoint kept as a compatibility wrapper.

    The real MitUNet DXF path is now:
    raw mask -> region_plan -> generate_mitunet_region_dxf
    """
    from .regions import build_mitunet_region_plan

    region_plan = build_mitunet_region_plan(infer_result, annotations=annotations)
    rect_count = generate_mitunet_region_dxf(region_plan, out_path, annotations=annotations)
    return rect_count


def generate_mitunet_region_dxf(
    region_plan: dict[str, Any],
    out_path: str,
    *,
    annotations: list[dict] | None = None,
    skip_regions: bool = False,
) -> int:
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

    # --- Wall Legend ---
    from ..components.wall_legend import add_wall_legend

    # Place legend to the right of the floor plan extents
    try:
        from ezdxf import bbox as ezdxf_bbox
        extents = ezdxf_bbox.extents(msp)
        if extents.has_data:
            legend_x = extents.extmax.x + 20
            legend_y = extents.extmax.y
        else:
            legend_x, legend_y = 0, 0
    except Exception:
        legend_x, legend_y = 0, 0

    add_wall_legend(msp, doc, legend_x, legend_y)

    doc.saveas(out_path)
    return rect_count
