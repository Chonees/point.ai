from __future__ import annotations

from pathlib import Path

import ezdxf


FLOOR_OVERLAY_LAYER = "FLOOR_OVERLAY"
BUILDABLE_DIM_LAYER = "CAD_DIM_BUILDABLE"
FOOTPRINT_DIM_LAYER = "CAD_DIM_FOOTPRINT"


def resolve_overlay_bbox(result: dict) -> dict | None:
    fit_summary = result.get("fit_summary") or {}
    floor_bbox = fit_summary.get("footprint_bbox") or (result.get("floor_plan") or {}).get("bbox")
    buildable_bbox = fit_summary.get("buildable_bbox")
    if floor_bbox is None or buildable_bbox is None:
        return None

    x1 = float(buildable_bbox["x1"]) + ((float(buildable_bbox["width"]) - float(floor_bbox["width"])) / 2.0)
    y1 = float(buildable_bbox["y1"]) + ((float(buildable_bbox["height"]) - float(floor_bbox["height"])) / 2.0)
    return {
        "x1": x1,
        "y1": y1,
        "x2": x1 + float(floor_bbox["width"]),
        "y2": y1 + float(floor_bbox["height"]),
        "width": float(floor_bbox["width"]),
        "height": float(floor_bbox["height"]),
    }


def export_overlay_dxf(result: dict, out_path: Path) -> Path:
    overlay_bbox = resolve_overlay_bbox(result)
    if overlay_bbox is None:
        raise ValueError("Overlay export requires both a floor footprint and a buildable bbox.")

    floor_bbox = ((result.get("floor_plan") or {}).get("bbox")) or {"x1": 0.0, "y1": 0.0}
    floor_translate_x = float(overlay_bbox["x1"]) - float(floor_bbox["x1"])
    floor_translate_y = float(overlay_bbox["y1"]) - float(floor_bbox["y1"])

    doc = ezdxf.new("R2018")
    doc.units = 1  # inch
    msp = doc.modelspace()

    _ensure_layer(doc, FLOOR_OVERLAY_LAYER, color=4)
    _ensure_layer(doc, BUILDABLE_DIM_LAYER, color=3)
    _ensure_layer(doc, FOOTPRINT_DIM_LAYER, color=4)

    for entity in (result.get("site_plan") or {}).get("entities", []):
        _ensure_layer(doc, str(entity.get("layer") or "0"), color=3)
        _write_entity(msp, entity, dx=0.0, dy=0.0, layer=str(entity.get("layer") or "0"))

    for entity in (result.get("floor_plan") or {}).get("entities", []):
        _write_entity(msp, entity, dx=floor_translate_x, dy=floor_translate_y, layer=FLOOR_OVERLAY_LAYER)

    buildable_bbox = (result.get("fit_summary") or {}).get("buildable_bbox")
    if buildable_bbox is not None:
        _add_overlay_dimensions(
            msp,
            buildable_bbox=buildable_bbox,
            overlay_bbox=overlay_bbox,
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(out_path)
    return out_path


def _ensure_layer(doc, name: str, *, color: int) -> None:
    if name in doc.layers:
        return
    doc.layers.add(name, color=color)


def _write_entity(msp, entity: dict, *, dx: float, dy: float, layer: str) -> None:
    entity_type = str(entity.get("type") or "").lower()
    if entity_type == "line":
        start = entity.get("start")
        end = entity.get("end")
        if start is None or end is None:
            return
        msp.add_line(
            (float(start["x"]) + dx, float(start["y"]) + dy),
            (float(end["x"]) + dx, float(end["y"]) + dy),
            dxfattribs={"layer": layer},
        )
        return

    if entity_type == "polyline":
        points = entity.get("points") or []
        if len(points) < 2:
            return
        vertices = [(float(point["x"]) + dx, float(point["y"]) + dy) for point in points]
        closed = vertices[0] == vertices[-1]
        if closed:
            vertices = vertices[:-1]
        msp.add_lwpolyline(vertices, close=closed, dxfattribs={"layer": layer})


def _add_overlay_dimensions(msp, *, buildable_bbox: dict, overlay_bbox: dict) -> None:
    buildable_x1 = float(buildable_bbox["x1"])
    buildable_y1 = float(buildable_bbox["y1"])
    buildable_x2 = float(buildable_bbox["x2"])
    buildable_y2 = float(buildable_bbox["y2"])
    overlay_x1 = float(overlay_bbox["x1"])
    overlay_y1 = float(overlay_bbox["y1"])
    overlay_x2 = float(overlay_bbox["x2"])
    overlay_y2 = float(overlay_bbox["y2"])

    _add_linear_dimension(
        msp,
        layer=BUILDABLE_DIM_LAYER,
        base=(buildable_x1, buildable_y1 - 44.0),
        p1=(buildable_x1, buildable_y1),
        p2=(buildable_x2, buildable_y1),
        angle=0,
        text=f'Buildable {_format_architectural_measure(float(buildable_bbox["width"]))}',
    )
    _add_linear_dimension(
        msp,
        layer=BUILDABLE_DIM_LAYER,
        base=(buildable_x2 + 28.0, buildable_y1),
        p1=(buildable_x2, buildable_y1),
        p2=(buildable_x2, buildable_y2),
        angle=90,
        text=f'Buildable {_format_architectural_measure(float(buildable_bbox["height"]))}',
    )
    _add_linear_dimension(
        msp,
        layer=FOOTPRINT_DIM_LAYER,
        base=(overlay_x1, overlay_y2 + 28.0),
        p1=(overlay_x1, overlay_y2),
        p2=(overlay_x2, overlay_y2),
        angle=0,
        text=f'Footprint {_format_architectural_measure(float(overlay_bbox["width"]))}',
    )
    _add_linear_dimension(
        msp,
        layer=FOOTPRINT_DIM_LAYER,
        base=(overlay_x1 - 28.0, overlay_y1),
        p1=(overlay_x1, overlay_y1),
        p2=(overlay_x1, overlay_y2),
        angle=90,
        text=f'Footprint {_format_architectural_measure(float(overlay_bbox["height"]))}',
    )


def _add_linear_dimension(msp, *, layer: str, base: tuple[float, float], p1: tuple[float, float], p2: tuple[float, float], angle: float, text: str) -> None:
    dimension = msp.add_linear_dim(
        base=base,
        p1=p1,
        p2=p2,
        angle=angle,
        text=text,
        dxfattribs={"layer": layer},
        override={
            "dimtxt": 14.0,
            "dimasz": 8.0,
            "dimexo": 4.0,
            "dimexe": 4.0,
            "dimclrd": 256,
            "dimclre": 256,
            "dimclrt": 256,
        },
    )
    dimension.render()


def _format_architectural_measure(value: float) -> str:
    return f'{_format_feet_inches(value)} | {_format_inches_value(value)} in'


def _format_inches_value(value: float) -> str:
    rounded = round(float(value), 2)
    if abs(rounded - round(rounded)) < 1e-9:
        return str(int(round(rounded)))
    return f"{rounded:.2f}"


def _format_feet_inches(value: float) -> str:
    sign = "-" if value < 0 else ""
    absolute = abs(float(value))
    feet = int(absolute // 12)
    remainder = absolute - (feet * 12)
    whole_inches = int(remainder // 1)
    fraction = remainder - whole_inches
    eighths = int(round(fraction * 8))

    if eighths == 8:
        whole_inches += 1
        eighths = 0
    if whole_inches == 12:
        feet += 1
        whole_inches = 0

    fractions = {
        1: "1/8",
        2: "1/4",
        3: "3/8",
        4: "1/2",
        5: "5/8",
        6: "3/4",
        7: "7/8",
    }
    fraction_text = fractions.get(eighths)
    if fraction_text:
        return f"{sign}{feet}'-{whole_inches} {fraction_text}\""
    return f"{sign}{feet}'-{whole_inches}\""
