from __future__ import annotations

import math
from pathlib import Path

import ezdxf


APPLY_PLAN_LAYER = "BRIDGE_APPLY_PLAN"
APPLY_FOOTPRINT_LAYER = "BRIDGE_APPLY_FOOTPRINT"
APPLY_OPENING_LAYER = "BRIDGE_APPLY_OPENINGS"
BUILDABLE_DIM_LAYER = "CAD_DIM_BUILDABLE"
FOOTPRINT_DIM_LAYER = "CAD_DIM_FOOTPRINT"


def export_bridge_apply_dxf(snapshot: dict, out_path: Path) -> Path:
    cad_analysis = snapshot.get("cad_analysis") or {}
    apply_payload = snapshot.get("apply") or {}
    plan_payload = (apply_payload.get("applied_plan") or {}).get("plan") or {}
    registration = apply_payload.get("registration_summary") or {}
    transform = registration.get("transform") or {}

    if not plan_payload:
        raise ValueError("Bridge apply export requires apply.applied_plan.plan.")

    doc = ezdxf.new("R2018")
    doc.units = 1  # inch
    msp = doc.modelspace()

    _ensure_layer(doc, APPLY_PLAN_LAYER, color=4)
    _ensure_layer(doc, APPLY_FOOTPRINT_LAYER, color=1)
    _ensure_layer(doc, APPLY_OPENING_LAYER, color=6)
    _ensure_layer(doc, BUILDABLE_DIM_LAYER, color=3)
    _ensure_layer(doc, FOOTPRINT_DIM_LAYER, color=1)

    for entity in (cad_analysis.get("site_plan") or {}).get("entities", []):
        layer = str(entity.get("layer") or "0")
        _ensure_layer(doc, layer, color=3)
        _write_snapshot_entity(msp, entity, layer=layer)

    _write_plan_geometry(msp, plan_payload, transform=transform)
    _add_dimensions(
        msp,
        buildable_bbox=(cad_analysis.get("fit_summary") or {}).get("buildable_bbox"),
        overlay_bbox=_resolve_overlay_bbox(plan_payload, registration=registration, transform=transform),
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(out_path)
    return out_path


def _write_plan_geometry(msp, plan_payload: dict, *, transform: dict) -> None:
    footprint_bbox = _resolve_overlay_bbox(plan_payload, registration=None, transform=transform)
    if footprint_bbox is not None:
        msp.add_lwpolyline(
            [
                (float(footprint_bbox["x1"]), float(footprint_bbox["y1"])),
                (float(footprint_bbox["x2"]), float(footprint_bbox["y1"])),
                (float(footprint_bbox["x2"]), float(footprint_bbox["y2"])),
                (float(footprint_bbox["x1"]), float(footprint_bbox["y2"])),
            ],
            close=True,
            dxfattribs={"layer": APPLY_FOOTPRINT_LAYER},
        )

    for wall in plan_payload.get("walls") or []:
        start = _transform_point(wall.get("start"), transform=transform)
        end = _transform_point(wall.get("end"), transform=transform)
        if start is None or end is None:
            continue
        msp.add_line(
            (float(start["x"]), float(start["y"])),
            (float(end["x"]), float(end["y"])),
            dxfattribs={"layer": APPLY_PLAN_LAYER},
        )

    for opening in plan_payload.get("openings") or []:
        start = _transform_point(opening.get("start"), transform=transform)
        end = _transform_point(opening.get("end"), transform=transform)
        if start is None or end is None:
            continue
        msp.add_line(
            (float(start["x"]), float(start["y"])),
            (float(end["x"]), float(end["y"])),
            dxfattribs={"layer": APPLY_OPENING_LAYER},
        )


def _resolve_overlay_bbox(plan_payload: dict, *, registration: dict | None, transform: dict) -> dict | None:
    registered_bbox = (registration or {}).get("registered_plan_bbox")
    if isinstance(registered_bbox, dict):
        return {
            "x1": float(registered_bbox["x1"]),
            "y1": float(registered_bbox["y1"]),
            "x2": float(registered_bbox["x2"]),
            "y2": float(registered_bbox["y2"]),
            "width": float(registered_bbox["width"]),
            "height": float(registered_bbox["height"]),
        }

    footprint_bbox = plan_payload.get("footprint_bbox")
    if not isinstance(footprint_bbox, dict):
        return None

    corners = [
        _transform_point({"x": footprint_bbox["x1"], "y": footprint_bbox["y1"]}, transform=transform),
        _transform_point({"x": footprint_bbox["x2"], "y": footprint_bbox["y1"]}, transform=transform),
        _transform_point({"x": footprint_bbox["x2"], "y": footprint_bbox["y2"]}, transform=transform),
        _transform_point({"x": footprint_bbox["x1"], "y": footprint_bbox["y2"]}, transform=transform),
    ]
    xs = [float(point["x"]) for point in corners if point is not None]
    ys = [float(point["y"]) for point in corners if point is not None]
    if not xs or not ys:
        return None
    x1 = min(xs)
    y1 = min(ys)
    x2 = max(xs)
    y2 = max(ys)
    return {
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "width": x2 - x1,
        "height": y2 - y1,
    }


def _transform_point(point: dict | None, *, transform: dict) -> dict | None:
    if not isinstance(point, dict):
        return None

    scale = float(transform.get("scale", 1.0) or 1.0)
    rotation = math.radians(float(transform.get("rotation_degrees", 0.0) or 0.0))
    translate_x = float(transform.get("translate_x", 0.0) or 0.0)
    translate_y = float(transform.get("translate_y", 0.0) or 0.0)

    x = float(point.get("x", 0.0)) * scale
    y = float(point.get("y", 0.0)) * scale
    rotated_x = (x * math.cos(rotation)) - (y * math.sin(rotation))
    rotated_y = (x * math.sin(rotation)) + (y * math.cos(rotation))
    return {
        "x": rotated_x + translate_x,
        "y": rotated_y + translate_y,
    }


def _ensure_layer(doc, name: str, *, color: int) -> None:
    if name in doc.layers:
        return
    doc.layers.add(name, color=color)


def _write_snapshot_entity(msp, entity: dict, *, layer: str) -> None:
    entity_type = str(entity.get("type") or "").lower()
    if entity_type == "line":
        start = entity.get("start")
        end = entity.get("end")
        if start is None or end is None:
            return
        msp.add_line(
            (float(start["x"]), float(start["y"])),
            (float(end["x"]), float(end["y"])),
            dxfattribs={"layer": layer},
        )
        return

    if entity_type == "polyline":
        points = entity.get("points") or []
        if len(points) < 2:
            return
        vertices = [(float(point["x"]), float(point["y"])) for point in points]
        closed = vertices[0] == vertices[-1]
        if closed:
            vertices = vertices[:-1]
        msp.add_lwpolyline(vertices, close=closed, dxfattribs={"layer": layer})


def _add_dimensions(msp, *, buildable_bbox: dict | None, overlay_bbox: dict | None) -> None:
    if buildable_bbox is not None:
        buildable_x1 = float(buildable_bbox["x1"])
        buildable_y1 = float(buildable_bbox["y1"])
        buildable_x2 = float(buildable_bbox["x2"])
        buildable_y2 = float(buildable_bbox["y2"])

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

    if overlay_bbox is None:
        return

    overlay_x1 = float(overlay_bbox["x1"])
    overlay_y1 = float(overlay_bbox["y1"])
    overlay_x2 = float(overlay_bbox["x2"])
    overlay_y2 = float(overlay_bbox["y2"])
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
