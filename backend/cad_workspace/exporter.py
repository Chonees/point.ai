from __future__ import annotations

from pathlib import Path

import ezdxf


FLOOR_OVERLAY_LAYER = "FLOOR_OVERLAY"


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

    for entity in (result.get("site_plan") or {}).get("entities", []):
        _ensure_layer(doc, str(entity.get("layer") or "0"), color=3)
        _write_entity(msp, entity, dx=0.0, dy=0.0, layer=str(entity.get("layer") or "0"))

    for entity in (result.get("floor_plan") or {}).get("entities", []):
        _write_entity(msp, entity, dx=floor_translate_x, dy=floor_translate_y, layer=FLOOR_OVERLAY_LAYER)

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
