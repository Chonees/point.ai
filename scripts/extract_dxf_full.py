#!/usr/bin/env python3
"""
extract_dxf_full.py — Extractor COMPLETO de DXF/DWG.

Extrae TODAS las entidades de TODAS las layers con TODOS sus atributos
geométricos: puntos, ángulos, radios, tipos de dimensión, hatches, textos, etc.

Uso:
    python scripts/extract_dxf_full.py "building Plans/SEMINOLE 2000/FARMHOUSE/floorplan.dxf"
    python scripts/extract_dxf_full.py archivo.dxf --output salida.json
    python scripts/extract_dxf_full.py archivo.dxf --layer DIMS --layer WALLS
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import ezdxf
from ezdxf.entities import (
    Arc, Circle, DXFGraphic, Dimension, Ellipse, Hatch, Insert,
    LWPolyline, Leader, Line, MText, Point, Polyline, Solid, Spline, Text,
)

# Mapeo de dim_type flags → nombre legible
DIM_TYPE_NAMES = {
    0: "LINEAR",        # Rotated, horizontal, or vertical
    1: "ALIGNED",       # Aligned
    2: "ANGULAR",       # Angular (2 lines)
    3: "DIAMETER",      # Diameter
    4: "RADIUS",        # Radius
    5: "ANGULAR_3PT",   # Angular (3 points)
    6: "ORDINATE",      # Ordinate
}


def _pt(vec) -> list[float]:
    """Convert any ezdxf vector/tuple to [x, y]."""
    return [round(float(vec[0]), 4), round(float(vec[1]), 4)]


def _pt3(vec) -> list[float]:
    """Convert to [x, y, z]."""
    return [round(float(vec[0]), 4), round(float(vec[1]), 4), round(float(vec[2]), 4)]


def _angle(deg: float) -> float:
    return round(float(deg) % 360, 4)


def _safe_float(val, default=0.0) -> float:
    try:
        return round(float(val), 4)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Entity extractors — uno por tipo
# ---------------------------------------------------------------------------

def _extract_line(e: Line) -> dict:
    s, end = e.dxf.start, e.dxf.end
    dx, dy = float(end.x - s.x), float(end.y - s.y)
    length = math.hypot(dx, dy)
    angle = math.degrees(math.atan2(dy, dx)) % 360
    return {
        "start": _pt(s),
        "end": _pt(end),
        "length": round(length, 4),
        "angle": round(angle, 4),
    }


def _extract_circle(e: Circle) -> dict:
    return {
        "center": _pt(e.dxf.center),
        "radius": _safe_float(e.dxf.radius),
        "circumference": round(2 * math.pi * float(e.dxf.radius), 4),
        "area": round(math.pi * float(e.dxf.radius) ** 2, 4),
    }


def _extract_arc(e: Arc) -> dict:
    sa = _angle(e.dxf.start_angle)
    ea = _angle(e.dxf.end_angle)
    span = (ea - sa) % 360
    r = float(e.dxf.radius)
    arc_length = round(math.radians(span) * r, 4)
    # Start/end points
    sa_rad = math.radians(sa)
    ea_rad = math.radians(ea)
    cx, cy = float(e.dxf.center.x), float(e.dxf.center.y)
    return {
        "center": _pt(e.dxf.center),
        "radius": _safe_float(r),
        "start_angle": sa,
        "end_angle": ea,
        "span_angle": round(span, 4),
        "arc_length": arc_length,
        "start_point": [round(cx + r * math.cos(sa_rad), 4),
                        round(cy + r * math.sin(sa_rad), 4)],
        "end_point": [round(cx + r * math.cos(ea_rad), 4),
                      round(cy + r * math.sin(ea_rad), 4)],
    }


def _extract_ellipse(e: Ellipse) -> dict:
    return {
        "center": _pt(e.dxf.center),
        "major_axis": _pt3(e.dxf.major_axis),
        "ratio": _safe_float(e.dxf.ratio),
        "start_param": _safe_float(e.dxf.start_param),
        "end_param": _safe_float(e.dxf.end_param),
    }


def _extract_lwpolyline(e: LWPolyline) -> dict:
    # get_points("xyseb") → x, y, start_width, end_width, bulge
    raw_points = list(e.get_points("xyseb"))
    points = []
    for p in raw_points:
        entry: dict = {"x": round(float(p[0]), 4), "y": round(float(p[1]), 4)}
        if len(p) > 4 and float(p[4]) != 0:
            entry["bulge"] = round(float(p[4]), 4)
            # bulge → included angle: angle = 4 * atan(bulge)
            entry["bulge_angle"] = round(math.degrees(4 * math.atan(float(p[4]))), 4)
        points.append(entry)

    # Segment lengths + total
    coords = [(p["x"], p["y"]) for p in points]
    total_length = 0.0
    segments = []
    n = len(coords)
    limit = n if e.closed else n - 1
    for i in range(limit):
        x1, y1 = coords[i]
        x2, y2 = coords[(i + 1) % n]
        seg_len = math.hypot(x2 - x1, y2 - y1)
        seg_angle = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 360
        total_length += seg_len
        segments.append({
            "from": [x1, y1],
            "to": [x2, y2],
            "length": round(seg_len, 4),
            "angle": round(seg_angle, 4),
        })

    return {
        "points": points,
        "closed": e.closed,
        "num_vertices": len(points),
        "segments": segments,
        "total_length": round(total_length, 4),
    }


def _extract_polyline(e: Polyline) -> dict:
    points = []
    for v in e.vertices:
        points.append(_pt(v.dxf.location))
    return {
        "points": points,
        "closed": e.is_closed,
        "num_vertices": len(points),
    }


def _extract_spline(e: Spline) -> dict:
    ctrl_pts = [_pt(p) for p in e.control_points]
    fit_pts = [_pt(p) for p in e.fit_points]
    return {
        "degree": int(e.dxf.degree) if e.dxf.hasattr("degree") else None,
        "control_points": ctrl_pts,
        "fit_points": fit_pts,
        "num_control_points": len(ctrl_pts),
        "num_fit_points": len(fit_pts),
        "closed": e.closed,
        "knots": [round(float(k), 6) for k in e.knots] if e.knots else [],
    }


def _extract_text(e: Text) -> dict:
    result: dict = {
        "text": e.dxf.text if e.dxf.hasattr("text") else "",
        "position": _pt(e.dxf.insert) if e.dxf.hasattr("insert") else None,
        "height": _safe_float(e.dxf.height) if e.dxf.hasattr("height") else None,
        "rotation": _safe_float(e.dxf.rotation) if e.dxf.hasattr("rotation") else None,
    }
    if e.dxf.hasattr("style"):
        result["style"] = e.dxf.style
    return result


def _extract_mtext(e: MText) -> dict:
    return {
        "text": e.text if hasattr(e, "text") else str(e.dxf.text) if e.dxf.hasattr("text") else "",
        "position": _pt(e.dxf.insert) if e.dxf.hasattr("insert") else None,
        "height": _safe_float(e.dxf.char_height) if e.dxf.hasattr("char_height") else None,
        "rotation": _safe_float(e.dxf.rotation) if e.dxf.hasattr("rotation") else None,
        "width": _safe_float(e.dxf.width) if e.dxf.hasattr("width") else None,
        "attachment_point": int(e.dxf.attachment_point) if e.dxf.hasattr("attachment_point") else None,
    }


def _extract_dimension(e: Dimension) -> dict:
    # dim_type: bits 0-3 = tipo, bit 5 = ordinate type, bit 6 = user text, bit 7 = X-type
    raw_type = int(e.dxf.dimtype) if e.dxf.hasattr("dimtype") else -1
    base_type = raw_type & 0x0F  # bits 0-3
    type_name = DIM_TYPE_NAMES.get(base_type, f"UNKNOWN({base_type})")

    result: dict = {
        "dim_type_raw": raw_type,
        "dim_type": base_type,
        "dim_type_name": type_name,
    }

    # Texto override
    if e.dxf.hasattr("text"):
        result["text_override"] = e.dxf.text

    # Measurement value
    try:
        result["measurement"] = round(float(e.measurement), 4)
    except Exception:
        pass

    # Definition points (varían según tipo de dimensión)
    if e.dxf.hasattr("defpoint"):
        result["defpoint"] = _pt(e.dxf.defpoint)
    if e.dxf.hasattr("defpoint2"):
        result["defpoint2"] = _pt(e.dxf.defpoint2)
    if e.dxf.hasattr("defpoint3"):
        result["defpoint3"] = _pt(e.dxf.defpoint3)
    if e.dxf.hasattr("defpoint4"):
        result["defpoint4"] = _pt(e.dxf.defpoint4)
    if e.dxf.hasattr("defpoint5"):
        result["defpoint5"] = _pt(e.dxf.defpoint5)

    # Text position
    if e.dxf.hasattr("text_midpoint"):
        result["text_midpoint"] = _pt(e.dxf.text_midpoint)

    # Angle (for rotated linear dims)
    if e.dxf.hasattr("angle"):
        result["angle"] = _angle(e.dxf.angle)

    # Oblique angle
    if e.dxf.hasattr("oblique_angle"):
        result["oblique_angle"] = _safe_float(e.dxf.oblique_angle)

    # Text rotation
    if e.dxf.hasattr("text_rotation"):
        result["text_rotation"] = _safe_float(e.dxf.text_rotation)

    # Dim style
    if e.dxf.hasattr("dimstyle"):
        result["dimstyle"] = e.dxf.dimstyle

    return result


def _extract_leader(e: Leader) -> dict:
    vertices = []
    try:
        vertices = [_pt(v) for v in e.vertices]
    except Exception:
        pass
    return {
        "vertices": vertices,
        "num_vertices": len(vertices),
        "has_arrowhead": bool(e.dxf.flag) if e.dxf.hasattr("flag") else None,
    }


def _extract_hatch(e: Hatch) -> dict:
    result: dict = {
        "pattern_name": e.dxf.pattern_name if e.dxf.hasattr("pattern_name") else None,
        "solid_fill": bool(e.dxf.solid_fill) if e.dxf.hasattr("solid_fill") else None,
        "pattern_scale": _safe_float(e.dxf.pattern_scale) if e.dxf.hasattr("pattern_scale") else None,
        "pattern_angle": _safe_float(e.dxf.pattern_angle) if e.dxf.hasattr("pattern_angle") else None,
        "num_paths": len(e.paths),
    }

    # Extract boundary paths
    boundaries = []
    for path in e.paths:
        path_data: dict = {"type": path.type}
        if hasattr(path, "edges"):
            edges = []
            for edge in path.edges:
                edge_type = type(edge).__name__
                edge_data: dict = {"edge_type": edge_type}
                if hasattr(edge, "start") and hasattr(edge, "end"):
                    edge_data["start"] = _pt(edge.start)
                    edge_data["end"] = _pt(edge.end)
                if hasattr(edge, "center"):
                    edge_data["center"] = _pt(edge.center)
                if hasattr(edge, "radius"):
                    edge_data["radius"] = _safe_float(edge.radius)
                if hasattr(edge, "start_angle"):
                    edge_data["start_angle"] = _safe_float(edge.start_angle)
                if hasattr(edge, "end_angle"):
                    edge_data["end_angle"] = _safe_float(edge.end_angle)
                if hasattr(edge, "ccw"):
                    edge_data["ccw"] = bool(edge.ccw)
                edges.append(edge_data)
            path_data["edges"] = edges
        if hasattr(path, "vertices"):
            path_data["vertices"] = [_pt(v) for v in path.vertices]
        boundaries.append(path_data)
    result["boundaries"] = boundaries

    return result


def _extract_insert(e: Insert) -> dict:
    result: dict = {
        "block_name": e.dxf.name if e.dxf.hasattr("name") else "",
        "position": _pt(e.dxf.insert) if e.dxf.hasattr("insert") else None,
        "rotation": _safe_float(e.dxf.rotation) if e.dxf.hasattr("rotation") else None,
        "x_scale": _safe_float(e.dxf.xscale) if e.dxf.hasattr("xscale") else 1.0,
        "y_scale": _safe_float(e.dxf.yscale) if e.dxf.hasattr("yscale") else 1.0,
        "row_count": int(e.dxf.row_count) if e.dxf.hasattr("row_count") else 1,
        "col_count": int(e.dxf.column_count) if e.dxf.hasattr("column_count") else 1,
    }
    # Extract attributes
    attribs = []
    try:
        for att in e.attribs:
            attribs.append({
                "tag": att.dxf.tag if att.dxf.hasattr("tag") else "",
                "text": att.dxf.text if att.dxf.hasattr("text") else "",
            })
    except Exception:
        pass
    if attribs:
        result["attributes"] = attribs
    return result


def _extract_solid(e: Solid) -> dict:
    points = []
    for attr in ("vtx0", "vtx1", "vtx2", "vtx3"):
        if e.dxf.hasattr(attr):
            points.append(_pt(getattr(e.dxf, attr)))
    return {"vertices": points}


def _extract_point(e: Point) -> dict:
    return {"location": _pt(e.dxf.location)}


def _extract_3dface(e: DXFGraphic) -> dict:
    points = []
    for attr in ("vtx0", "vtx1", "vtx2", "vtx3"):
        if e.dxf.hasattr(attr):
            points.append(_pt3(getattr(e.dxf, attr)))
    return {"vertices": points}


def _extract_generic(e: DXFGraphic) -> dict:
    """Fallback: extract whatever DXF attribs are available."""
    result: dict = {}
    for attr in ("insert", "start", "end", "center", "location"):
        if e.dxf.hasattr(attr):
            result[attr] = _pt(getattr(e.dxf, attr))
    for attr in ("radius", "height", "width", "rotation", "angle",
                 "start_angle", "end_angle", "thickness"):
        if e.dxf.hasattr(attr):
            result[attr] = _safe_float(getattr(e.dxf, attr))
    for attr in ("text", "style", "name", "tag"):
        if e.dxf.hasattr(attr):
            result[attr] = str(getattr(e.dxf, attr))
    return result


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

EXTRACTORS = {
    "LINE": _extract_line,
    "CIRCLE": _extract_circle,
    "ARC": _extract_arc,
    "ELLIPSE": _extract_ellipse,
    "LWPOLYLINE": _extract_lwpolyline,
    "POLYLINE": _extract_polyline,
    "SPLINE": _extract_spline,
    "TEXT": _extract_text,
    "MTEXT": _extract_mtext,
    "DIMENSION": _extract_dimension,
    "LEADER": _extract_leader,
    "HATCH": _extract_hatch,
    "INSERT": _extract_insert,
    "SOLID": _extract_solid,
    "POINT": _extract_point,
    "3DFACE": _extract_3dface,
}


def extract_entity(e: DXFGraphic) -> dict:
    """Extract full data from a single entity."""
    etype = e.dxftype()
    extractor = EXTRACTORS.get(etype, _extract_generic)

    base: dict = {
        "type": etype,
        "layer": e.dxf.layer if e.dxf.hasattr("layer") else "0",
        "color": int(e.dxf.color) if e.dxf.hasattr("color") else None,
        "lineweight": int(e.dxf.lineweight) if e.dxf.hasattr("lineweight") else None,
        "handle": e.dxf.handle if e.dxf.hasattr("handle") else None,
    }

    try:
        data = extractor(e)
        base.update(data)
    except Exception as exc:
        base["_extraction_error"] = str(exc)

    return base


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------

def extract_dxf(
    dxf_path: str | Path,
    *,
    layers: list[str] | None = None,
) -> dict:
    """Extract all entities from a DXF file.

    Args:
        dxf_path: Path to DXF file.
        layers: Optional list of layer names to filter. None = all layers.

    Returns:
        Complete extraction dict.
    """
    path = Path(dxf_path)
    doc = ezdxf.readfile(str(path))
    msp = doc.modelspace()

    # Gather layer properties
    layer_props: dict = {}
    for layer in doc.layers:
        layer_props[layer.dxf.name] = {
            "color": int(layer.dxf.color) if layer.dxf.hasattr("color") else None,
            "lineweight": int(layer.dxf.lineweight) if layer.dxf.hasattr("lineweight") else None,
            "on": layer.is_on(),
            "frozen": layer.is_frozen(),
            "locked": layer.is_locked(),
            "linetype": layer.dxf.linetype if layer.dxf.hasattr("linetype") else None,
        }

    # Extract all entities
    entities_by_layer: dict[str, list[dict]] = {}
    layer_summary: dict[str, dict] = {}
    total = 0
    skipped = 0

    # Bounds tracking
    all_x: list[float] = []
    all_y: list[float] = []

    for e in msp:
        elayer = e.dxf.layer if e.dxf.hasattr("layer") else "0"
        if layers and elayer not in layers:
            continue

        data = extract_entity(e)
        total += 1

        # Track bounds from extracted points
        for key in ("start", "end", "center", "position", "location",
                     "defpoint", "defpoint2", "defpoint3", "text_midpoint",
                     "start_point", "end_point"):
            val = data.get(key)
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                all_x.append(val[0])
                all_y.append(val[1])

        # Track points arrays
        for pt in data.get("points", []):
            if isinstance(pt, dict):
                all_x.append(pt.get("x", 0))
                all_y.append(pt.get("y", 0))
            elif isinstance(pt, (list, tuple)):
                all_x.append(pt[0])
                all_y.append(pt[1])

        entities_by_layer.setdefault(elayer, []).append(data)

        # Summary
        etype = data["type"]
        if elayer not in layer_summary:
            layer_summary[elayer] = {"count": 0, "types": {}}
        layer_summary[elayer]["count"] += 1
        layer_summary[elayer]["types"][etype] = layer_summary[elayer]["types"].get(etype, 0) + 1

    # Dimension type breakdown
    dim_breakdown: dict[str, int] = {}
    for layer_entities in entities_by_layer.values():
        for ent in layer_entities:
            if ent["type"] == "DIMENSION":
                name = ent.get("dim_type_name", "UNKNOWN")
                dim_breakdown[name] = dim_breakdown.get(name, 0) + 1

    # Extents
    extents = {}
    if all_x and all_y:
        extents = {
            "min_x": round(min(all_x), 4),
            "max_x": round(max(all_x), 4),
            "min_y": round(min(all_y), 4),
            "max_y": round(max(all_y), 4),
            "width": round(max(all_x) - min(all_x), 4),
            "height": round(max(all_y) - min(all_y), 4),
        }

    return {
        "source": str(path.resolve()),
        "total_entities": total,
        "skipped": skipped,
        "extents": extents,
        "layer_properties": layer_props,
        "layer_summary": layer_summary,
        "dimension_type_breakdown": dim_breakdown,
        "entities_by_layer": entities_by_layer,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Extract ALL entities from a DXF file")
    parser.add_argument("dxf_path", help="Path to .dxf file")
    parser.add_argument("-o", "--output", help="Output JSON path (default: auto)")
    parser.add_argument("-l", "--layer", action="append", dest="layers",
                        help="Filter to specific layer(s). Can repeat: -l DIMS -l WALLS")
    parser.add_argument("--compact", action="store_true",
                        help="Compact JSON (no indentation)")
    args = parser.parse_args()

    path = Path(args.dxf_path)
    if not path.exists():
        print(f"ERROR: File not found: {path}", file=sys.stderr)
        sys.exit(1)

    print(f"Extracting from: {path}")
    if args.layers:
        print(f"Filtering layers: {args.layers}")

    result = extract_dxf(path, layers=args.layers)

    # Output path
    if args.output:
        out_path = Path(args.output)
    else:
        suffix = "_full_extract" if not args.layers else f"_{'_'.join(args.layers)}"
        out_path = Path("backend/data") / f"{path.stem}{suffix}.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    indent = None if args.compact else 2
    out_path.write_text(json.dumps(result, indent=indent, ensure_ascii=False), encoding="utf-8")

    # Print summary
    print(f"\nTotal entities: {result['total_entities']}")
    print(f"Layers: {len(result['layer_summary'])}")
    print(f"\nLayer breakdown:")
    for layer, info in sorted(result["layer_summary"].items(), key=lambda x: -x[1]["count"]):
        print(f"  {layer:25s} {info['count']:6d}  {dict(info['types'])}")

    if result["dimension_type_breakdown"]:
        print(f"\nDimension types:")
        for dtype, count in sorted(result["dimension_type_breakdown"].items()):
            print(f"  {dtype:20s} {count:6d}")

    print(f"\nExtents: {result['extents']}")
    print(f"\nSaved to: {out_path}")


if __name__ == "__main__":
    main()
