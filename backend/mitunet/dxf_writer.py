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


def generate_mitunet_region_dxf(
    region_plan: dict[str, Any],
    out_path: str,
    *,
    annotations: list[dict] | None = None,
    skip_regions: bool = False,
    total_area_sqft: float | None = None,
) -> tuple[int, dict | None]:
    del total_area_sqft  # single-centerline-first path no longer emits dims/labels side products

    doc = _load_mitunet_template_doc()
    msp = doc.modelspace()

    if "WALLS" not in doc.layers:
        doc.layers.add("WALLS", color=7, dxfattribs={"lineweight": 100})
    else:
        doc.layers.get("WALLS").dxf.lineweight = 60

    entity_count = 0
    region_thicknesses: list[float] = []

    def _snap_thickness(raw: float) -> float:
        return 6.0 if raw >= 5.0 else 4.0

    if not skip_regions:
        snapped: list[dict[str, float | str]] = []
        for region in region_plan.get("regions", []):
            bounds = region.get("bounds") or {}
            x1 = float(bounds.get("x1", 0.0))
            y1 = float(bounds.get("y1", 0.0))
            x2 = float(bounds.get("x2", 0.0))
            y2 = float(bounds.get("y2", 0.0))
            if abs(x2 - x1) < 1 or abs(y2 - y1) < 1:
                continue

            std = _snap_thickness(float(region.get("draw_thickness", 4.0)))
            orientation = str(region.get("orientation", "horizontal"))
            if orientation == "horizontal":
                cy = (y1 + y2) / 2.0
                snapped.append({"orientation": orientation, "mid": cy, "span_lo": x1, "span_hi": x2, "std": std})
            else:
                cx = (x1 + x2) / 2.0
                snapped.append({"orientation": orientation, "mid": cx, "span_lo": y1, "span_hi": y2, "std": std})

        junction_input = [
            {
                "orientation": str(reg["orientation"]),
                "mid": float(reg["mid"]),
                "span_lo": float(reg["span_lo"]),
                "span_hi": float(reg["span_hi"]),
                "half_lw": float(reg["std"]) / 2.0,
            }
            for reg in snapped
        ]
        resolved = resolve_wall_junctions(junction_input, mode="dxf")

        for reg, adj in zip(snapped, resolved):
            std = float(reg["std"])
            original_len = max(0.0, float(reg["span_hi"]) - float(reg["span_lo"]))
            resolved_len = max(0.0, float(adj["span_hi"]) - float(adj["span_lo"]))
            preserve_original_short_span = (
                original_len > 0.0
                and original_len <= std * 4.0
                and resolved_len < original_len
            )
            active_reg = reg if preserve_original_short_span else adj

            if str(reg["orientation"]) == "horizontal":
                points = [
                    (float(active_reg["span_lo"]), float(active_reg["mid"])),
                    (float(active_reg["span_hi"]), float(active_reg["mid"])),
                ]
            else:
                points = [
                    (float(active_reg["mid"]), float(active_reg["span_lo"])),
                    (float(active_reg["mid"]), float(active_reg["span_hi"])),
                ]
            msp.add_lwpolyline(points, dxfattribs={"layer": "WALLS", "color": 7, "const_width": std})
            entity_count += 1
            region_thicknesses.append(std)

    if region_thicknesses:
        region_thicknesses.sort()
        mid = len(region_thicknesses) // 2
        median_thickness = (
            region_thicknesses[mid]
            if len(region_thicknesses) % 2
            else (region_thicknesses[mid - 1] + region_thicknesses[mid]) / 2.0
        )
    else:
        median_thickness = 4.0

    meta = region_plan.get("meta", {})
    image_shape_meta = meta.get("image_shape", {})
    image_shape = (
        int(image_shape_meta.get("height", 0)),
        int(image_shape_meta.get("width", 0)),
    )
    entity_count += _draw_mitunet_annotations_from_region_plan(
        msp,
        doc,
        annotations,
        image_shape=image_shape,
        transform=meta.get("transform", {}),
        wall_thickness=median_thickness,
        regions=region_plan.get("regions", []),
    )

    doc.saveas(out_path)
    return entity_count, None
