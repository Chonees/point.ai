#!/usr/bin/env python3
"""
visualize_layers_dxf.py — Genera un DXF catálogo visual de cada layer.

Cada layer se escala para llenar su celda (scale-to-fit), con título,
conteo de entidades y desglose de tipos. Las DIMENSION se renderizan
con líneas de extensión, línea de cota y texto de medida.

Uso:
    python scripts/visualize_layers_dxf.py "backend/data/plans/SEMINOLE 2000/FARMHOUSE/floorplan.dxf"
    python scripts/visualize_layers_dxf.py archivo.dxf -o salida.dxf --cols 6
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import ezdxf
from ezdxf.entities import DXFGraphic
from ezdxf.math import Vec3

# Colores ACI para distinguir layers
COLORS = [1, 2, 3, 4, 5, 6, 10, 20, 30, 40, 50, 60, 70, 80, 90,
          100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200,
          210, 220, 230, 240, 250]


# ---------------------------------------------------------------------------
# Bounding box per entity
# ---------------------------------------------------------------------------

def _entity_bounds(e: DXFGraphic, doc=None) -> tuple[float, float, float, float] | None:
    pts: list[tuple[float, float]] = []
    etype = e.dxftype()
    try:
        if etype == "LINE":
            s, end = e.dxf.start, e.dxf.end
            pts = [(s.x, s.y), (end.x, end.y)]
        elif etype == "LWPOLYLINE":
            pts = [(float(p[0]), float(p[1])) for p in e.get_points("xy")]
        elif etype == "POLYLINE":
            pts = [(float(v.dxf.location.x), float(v.dxf.location.y)) for v in e.vertices]
        elif etype == "CIRCLE":
            cx, cy, r = float(e.dxf.center.x), float(e.dxf.center.y), float(e.dxf.radius)
            pts = [(cx - r, cy - r), (cx + r, cy + r)]
        elif etype == "ARC":
            cx, cy, r = float(e.dxf.center.x), float(e.dxf.center.y), float(e.dxf.radius)
            pts = [(cx - r, cy - r), (cx + r, cy + r)]
        elif etype == "ELLIPSE":
            cx, cy = float(e.dxf.center.x), float(e.dxf.center.y)
            mx, my = float(e.dxf.major_axis.x), float(e.dxf.major_axis.y)
            major = math.hypot(mx, my)
            pts = [(cx - major, cy - major), (cx + major, cy + major)]
        elif etype in ("TEXT", "MTEXT"):
            if e.dxf.hasattr("insert"):
                ix, iy = float(e.dxf.insert.x), float(e.dxf.insert.y)
                h = float(e.dxf.height) if e.dxf.hasattr("height") else (
                    float(e.dxf.char_height) if e.dxf.hasattr("char_height") else 50)
                pts = [(ix, iy), (ix + h * 5, iy + h)]
        elif etype == "DIMENSION":
            for attr in ("defpoint", "defpoint2", "defpoint3", "defpoint4", "text_midpoint"):
                if e.dxf.hasattr(attr):
                    v = getattr(e.dxf, attr)
                    pts.append((float(v.x), float(v.y)))
            # Also get bounds from geometry block
            if doc and e.dxf.hasattr("geometry"):
                blk = doc.blocks.get(e.dxf.geometry)
                if blk:
                    for sub in blk:
                        for attr in ("start", "end", "insert", "center", "location"):
                            if sub.dxf.hasattr(attr):
                                v = getattr(sub.dxf, attr)
                                pts.append((float(v.x), float(v.y)))
        elif etype == "INSERT":
            if e.dxf.hasattr("insert"):
                pts = [(float(e.dxf.insert.x), float(e.dxf.insert.y))]
        elif etype == "HATCH":
            for path in e.paths:
                if hasattr(path, "vertices"):
                    for v in path.vertices:
                        pts.append((float(v[0]), float(v[1])))
                if hasattr(path, "edges"):
                    for edge in path.edges:
                        for a in ("start", "end", "center"):
                            if hasattr(edge, a):
                                val = getattr(edge, a)
                                pts.append((float(val[0]), float(val[1])))
        elif etype == "SPLINE":
            pts = [(float(p.x), float(p.y)) for p in e.control_points]
            pts += [(float(p.x), float(p.y)) for p in e.fit_points]
        elif etype in ("SOLID", "3DFACE"):
            for attr in ("vtx0", "vtx1", "vtx2", "vtx3"):
                if e.dxf.hasattr(attr):
                    v = getattr(e.dxf, attr)
                    pts.append((float(v.x), float(v.y)))
        elif etype == "LEADER":
            try:
                pts = [(float(v.x), float(v.y)) for v in e.vertices]
            except Exception:
                pass
        elif etype == "POINT":
            if e.dxf.hasattr("location"):
                pts = [(float(e.dxf.location.x), float(e.dxf.location.y))]
        else:
            for attr in ("insert", "start", "end", "center", "location"):
                if e.dxf.hasattr(attr):
                    v = getattr(e.dxf, attr)
                    pts.append((float(v.x), float(v.y)))
    except Exception:
        return None

    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


# ---------------------------------------------------------------------------
# Transform helper: scale + translate a point
# ---------------------------------------------------------------------------

def _xform(x: float, y: float, *, ox: float, oy: float, sc: float, tx: float, ty: float) -> tuple[float, float]:
    """Transform source point → cell space.
    1. Subtract source origin (ox, oy)
    2. Scale by sc
    3. Add target offset (tx, ty)
    """
    return (x - ox) * sc + tx, (y - oy) * sc + ty


# ---------------------------------------------------------------------------
# Copy entity with full transform (scale + translate)
# ---------------------------------------------------------------------------

def _explode_block_xform(
    msp, doc, block_name: str,
    ins_x: float, ins_y: float, ins_rot: float,
    ins_xsc: float, ins_ysc: float,
    ox: float, oy: float, sc: float, tx: float, ty: float,
    layer: str, color: int,
):
    """Explode a block INSERT, applying block transform + cell transform."""
    blk = doc.blocks.get(block_name)
    if not blk:
        return
    rot_rad = math.radians(ins_rot)
    cos_r, sin_r = math.cos(rot_rad), math.sin(rot_rad)

    def BX(bx, by):
        """Block-local coord -> world coord -> cell coord."""
        # Scale by insert scale
        sx = bx * ins_xsc
        sy = by * ins_ysc
        # Rotate
        wx = sx * cos_r - sy * sin_r + ins_x
        wy = sx * sin_r + sy * cos_r + ins_y
        # Cell transform
        return _xform(wx, wy, ox=ox, oy=oy, sc=sc, tx=tx, ty=ty)

    for sub in blk:
        st = sub.dxftype()
        try:
            if st == "LINE":
                s, e2 = sub.dxf.start, sub.dxf.end
                msp.add_line(BX(s.x, s.y), BX(e2.x, e2.y),
                             dxfattribs={"layer": layer, "color": color})
            elif st == "LWPOLYLINE":
                pts = list(sub.get_points("xyb"))
                if not pts:
                    continue
                # If it has bulge (like _Dot circles), draw as circle
                has_bulge = any(abs(p[2]) > 0.9 for p in pts if len(p) > 2)
                if has_bulge and len(pts) == 2:
                    # Two-point bulge=1 polyline = circle
                    p1 = BX(pts[0][0], pts[0][1])
                    p2 = BX(pts[1][0], pts[1][1])
                    cx = (p1[0] + p2[0]) / 2
                    cy = (p1[1] + p2[1]) / 2
                    r = math.hypot(p2[0] - p1[0], p2[1] - p1[1]) / 2
                    if r > 0.001:
                        msp.add_circle((cx, cy), r,
                                       dxfattribs={"layer": layer, "color": color})
                else:
                    xpts = [BX(p[0], p[1]) for p in pts]
                    if len(xpts) >= 2:
                        poly = msp.add_lwpolyline(
                            xpts, dxfattribs={"layer": layer, "color": color})
                        poly.close(sub.closed)
            elif st == "CIRCLE":
                c = sub.dxf.center
                cp = BX(c.x, c.y)
                msp.add_circle(cp, sub.dxf.radius * ins_xsc * sc,
                               dxfattribs={"layer": layer, "color": color})
            elif st == "ARC":
                c = sub.dxf.center
                cp = BX(c.x, c.y)
                msp.add_arc(cp, sub.dxf.radius * ins_xsc * sc,
                            sub.dxf.start_angle + ins_rot,
                            sub.dxf.end_angle + ins_rot,
                            dxfattribs={"layer": layer, "color": color})
            elif st == "SOLID":
                svtx = []
                for attr in ("vtx0", "vtx1", "vtx2", "vtx3"):
                    if sub.dxf.hasattr(attr):
                        v = getattr(sub.dxf, attr)
                        svtx.append(BX(v.x, v.y))
                if len(svtx) >= 3:
                    msp.add_solid(svtx, dxfattribs={"layer": layer, "color": color})
        except Exception:
            pass


def _copy_entity_xform(
    msp, e: DXFGraphic,
    ox: float, oy: float, sc: float, tx: float, ty: float,
    layer: str, color: int, text_h: float,
    src_doc=None,
):
    """Copy entity into output DXF, applying scale-to-fit transform."""
    etype = e.dxftype()
    X = lambda x, y: _xform(x, y, ox=ox, oy=oy, sc=sc, tx=tx, ty=ty)

    try:
        if etype == "LINE":
            s, end = e.dxf.start, e.dxf.end
            msp.add_line(X(s.x, s.y), X(end.x, end.y),
                         dxfattribs={"layer": layer, "color": color})

        elif etype == "LWPOLYLINE":
            pts = [X(float(p[0]), float(p[1])) for p in e.get_points("xy")]
            if len(pts) >= 2:
                poly = msp.add_lwpolyline(pts, dxfattribs={"layer": layer, "color": color})
                poly.close(e.closed)

        elif etype == "CIRCLE":
            c = e.dxf.center
            msp.add_circle(X(c.x, c.y), e.dxf.radius * sc,
                           dxfattribs={"layer": layer, "color": color})

        elif etype == "ARC":
            c = e.dxf.center
            msp.add_arc(X(c.x, c.y), e.dxf.radius * sc,
                        e.dxf.start_angle, e.dxf.end_angle,
                        dxfattribs={"layer": layer, "color": color})

        elif etype == "ELLIPSE":
            c = e.dxf.center
            # Scale major axis
            mx = float(e.dxf.major_axis.x) * sc
            my = float(e.dxf.major_axis.y) * sc
            msp.add_ellipse(
                X(c.x, c.y), (mx, my, 0),
                e.dxf.ratio, e.dxf.start_param, e.dxf.end_param,
                dxfattribs={"layer": layer, "color": color})

        elif etype == "TEXT":
            txt = e.dxf.text if e.dxf.hasattr("text") else ""
            ins = e.dxf.insert if e.dxf.hasattr("insert") else Vec3(0, 0, 0)
            h = float(e.dxf.height) if e.dxf.hasattr("height") else 50
            rot = float(e.dxf.rotation) if e.dxf.hasattr("rotation") else 0
            msp.add_text(txt, height=h * sc, rotation=rot,
                         dxfattribs={"layer": layer, "color": color,
                                     "insert": X(ins.x, ins.y)})

        elif etype == "MTEXT":
            txt = e.text if hasattr(e, "text") else ""
            ins = e.dxf.insert if e.dxf.hasattr("insert") else Vec3(0, 0, 0)
            h = float(e.dxf.char_height) if e.dxf.hasattr("char_height") else 50
            msp.add_mtext(txt, dxfattribs={
                "layer": layer, "color": color,
                "char_height": h * sc,
                "insert": X(ins.x, ins.y)})

        elif etype == "POINT":
            loc = e.dxf.location
            msp.add_point(X(loc.x, loc.y), dxfattribs={"layer": layer, "color": color})

        elif etype in ("SOLID", "3DFACE"):
            pts = []
            for attr in ("vtx0", "vtx1", "vtx2", "vtx3"):
                if e.dxf.hasattr(attr):
                    v = getattr(e.dxf, attr)
                    pts.append(X(v.x, v.y))
            if len(pts) >= 3:
                if etype == "SOLID":
                    msp.add_solid(pts, dxfattribs={"layer": layer, "color": color})
                else:
                    msp.add_3dface(pts, dxfattribs={"layer": layer, "color": color})

        elif etype == "SPLINE":
            ctrl = [X(float(p.x), float(p.y)) for p in e.control_points]
            if ctrl:
                msp.add_spline(ctrl, dxfattribs={"layer": layer, "color": color})

        elif etype == "LEADER":
            try:
                verts = [(*X(float(v.x), float(v.y)), 0) for v in e.vertices]
                if len(verts) >= 2:
                    msp.add_leader(verts, dxfattribs={"layer": layer, "color": color})
            except Exception:
                pass

        elif etype == "DIMENSION":
            # Explode the geometry block — this draws it EXACTLY as AutoCAD shows it
            if src_doc and e.dxf.hasattr("geometry"):
                blk_name = e.dxf.geometry
                blk = src_doc.blocks.get(blk_name)
                if blk:
                    for sub in blk:
                        st = sub.dxftype()
                        try:
                            if st == "LINE":
                                s2, e2 = sub.dxf.start, sub.dxf.end
                                msp.add_line(X(s2.x, s2.y), X(e2.x, e2.y),
                                             dxfattribs={"layer": layer, "color": color})
                            elif st == "MTEXT":
                                txt = sub.text if hasattr(sub, "text") else ""
                                ins = sub.dxf.insert if sub.dxf.hasattr("insert") else Vec3(0, 0, 0)
                                h = float(sub.dxf.char_height) if sub.dxf.hasattr("char_height") else 3.5
                                rot = float(sub.dxf.rotation) if sub.dxf.hasattr("rotation") else 0
                                msp.add_mtext(txt, dxfattribs={
                                    "layer": layer, "color": color,
                                    "char_height": h * sc,
                                    "insert": X(ins.x, ins.y),
                                    "rotation": rot,
                                })
                            elif st == "TEXT":
                                txt = sub.dxf.text if sub.dxf.hasattr("text") else ""
                                ins = sub.dxf.insert if sub.dxf.hasattr("insert") else Vec3(0, 0, 0)
                                h = float(sub.dxf.height) if sub.dxf.hasattr("height") else 3.5
                                rot = float(sub.dxf.rotation) if sub.dxf.hasattr("rotation") else 0
                                msp.add_text(txt, height=h * sc, rotation=rot,
                                             dxfattribs={"layer": layer, "color": color,
                                                         "insert": X(ins.x, ins.y)})
                            elif st == "POINT":
                                loc = sub.dxf.location
                                # Draw points as small filled circles (visible dots)
                                dot_r = 1.5 * sc
                                msp.add_circle(X(loc.x, loc.y), dot_r,
                                               dxfattribs={"layer": layer, "color": color})
                            elif st == "INSERT":
                                # Explode nested block (arrows/dots)
                                ins = sub.dxf.insert if sub.dxf.hasattr("insert") else Vec3(0, 0, 0)
                                rot = float(sub.dxf.rotation) if sub.dxf.hasattr("rotation") else 0
                                xsc = float(sub.dxf.xscale) if sub.dxf.hasattr("xscale") else 1.0
                                ysc = float(sub.dxf.yscale) if sub.dxf.hasattr("yscale") else 1.0
                                _explode_block_xform(
                                    msp, src_doc, sub.dxf.name,
                                    float(ins.x), float(ins.y), rot, xsc, ysc,
                                    ox, oy, sc, tx, ty, layer, color)
                            elif st == "SOLID":
                                svtx = []
                                for attr in ("vtx0", "vtx1", "vtx2", "vtx3"):
                                    if sub.dxf.hasattr(attr):
                                        v = getattr(sub.dxf, attr)
                                        svtx.append(X(v.x, v.y))
                                if len(svtx) >= 3:
                                    msp.add_solid(svtx, dxfattribs={"layer": layer, "color": color})
                            elif st == "CIRCLE":
                                c = sub.dxf.center
                                msp.add_circle(X(c.x, c.y), sub.dxf.radius * sc,
                                               dxfattribs={"layer": layer, "color": color})
                            elif st == "ARC":
                                c = sub.dxf.center
                                msp.add_arc(X(c.x, c.y), sub.dxf.radius * sc,
                                            sub.dxf.start_angle, sub.dxf.end_angle,
                                            dxfattribs={"layer": layer, "color": color})
                        except Exception:
                            pass

        elif etype == "HATCH":
            for path in e.paths:
                if hasattr(path, "vertices") and path.vertices:
                    pts = [X(float(v[0]), float(v[1])) for v in path.vertices]
                    if len(pts) >= 2:
                        poly = msp.add_lwpolyline(pts, dxfattribs={"layer": layer, "color": color})
                        poly.close(True)
                if hasattr(path, "edges"):
                    for edge in path.edges:
                        if hasattr(edge, "start") and hasattr(edge, "end"):
                            msp.add_line(
                                X(float(edge.start[0]), float(edge.start[1])),
                                X(float(edge.end[0]), float(edge.end[1])),
                                dxfattribs={"layer": layer, "color": color})
                        elif hasattr(edge, "center") and hasattr(edge, "radius"):
                            sa = float(edge.start_angle) if hasattr(edge, "start_angle") else 0
                            ea = float(edge.end_angle) if hasattr(edge, "end_angle") else 360
                            msp.add_arc(
                                X(float(edge.center[0]), float(edge.center[1])),
                                float(edge.radius) * sc, sa, ea,
                                dxfattribs={"layer": layer, "color": color})

        elif etype == "INSERT":
            if e.dxf.hasattr("insert"):
                ix, iy = X(float(e.dxf.insert.x), float(e.dxf.insert.y))
                sz = text_h * 0.5
                msp.add_line((ix - sz, iy), (ix + sz, iy),
                             dxfattribs={"layer": layer, "color": color})
                msp.add_line((ix, iy - sz), (ix, iy + sz),
                             dxfattribs={"layer": layer, "color": color})
                name = e.dxf.name if e.dxf.hasattr("name") else "BLK"
                msp.add_text(name, height=text_h * 0.6,
                             dxfattribs={"layer": layer, "color": color,
                                         "insert": (ix + sz * 1.2, iy + sz * 0.5)})

        # PDFUNDERLAY, MULTILEADER: skip silently

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main catalog builder
# ---------------------------------------------------------------------------

def build_layer_catalog(dxf_path: str | Path, *, cols: int = 5, output: str | None = None):
    path = Path(dxf_path)
    src_doc = ezdxf.readfile(str(path))
    src_msp = src_doc.modelspace()

    # Group entities by layer, compute bounds per layer
    layer_entities: dict[str, list[DXFGraphic]] = {}
    layer_bounds: dict[str, list[float]] = {}

    for e in src_msp:
        lname = e.dxf.layer if e.dxf.hasattr("layer") else "0"
        layer_entities.setdefault(lname, []).append(e)
        bb = _entity_bounds(e, doc=src_doc)
        if bb:
            if lname not in layer_bounds:
                layer_bounds[lname] = [bb[0], bb[1], bb[2], bb[3]]
            else:
                b = layer_bounds[lname]
                b[0] = min(b[0], bb[0])
                b[1] = min(b[1], bb[1])
                b[2] = max(b[2], bb[2])
                b[3] = max(b[3], bb[3])

    sorted_layers = sorted(layer_entities.keys(),
                           key=lambda l: len(layer_entities[l]), reverse=True)

    print(f"Source: {path}")
    print(f"Layers: {len(sorted_layers)}")

    # --- Fixed cell size (all cells same size for clean grid) ---
    CELL_W = 10000.0
    CELL_H = 10000.0
    TITLE_ZONE = 1200.0   # top area for title + subtitle
    PADDING = 400.0
    GAP = 800.0

    # Drawing area inside each cell
    DRAW_W = CELL_W - PADDING * 2
    DRAW_H = CELL_H - TITLE_ZONE - PADDING * 2

    # Create output
    out_doc = ezdxf.new("R2013")
    out_msp = out_doc.modelspace()
    out_doc.layers.add("FRAME", color=8)
    out_doc.layers.add("TITLES", color=7)

    rows = math.ceil(len(sorted_layers) / cols)
    print(f"Grid: {cols}x{rows} cells, each {CELL_W:.0f}x{CELL_H:.0f}")

    for idx, lname in enumerate(sorted_layers):
        col = idx % cols
        row = idx // cols

        # Cell top-left corner
        cx0 = col * (CELL_W + GAP)
        cy0 = -row * (CELL_H + GAP)

        entities = layer_entities[lname]
        count = len(entities)
        color_idx = COLORS[idx % len(COLORS)]

        safe_name = lname.replace(" ", "_") if lname else "LAYER_0"
        try:
            out_doc.layers.add(safe_name, color=color_idx)
        except Exception:
            pass

        # --- Frame ---
        frame_pts = [
            (cx0, cy0), (cx0 + CELL_W, cy0),
            (cx0 + CELL_W, cy0 - CELL_H), (cx0, cy0 - CELL_H),
        ]
        fr = out_msp.add_lwpolyline(frame_pts, dxfattribs={"layer": "FRAME", "color": 9})
        fr.close(True)

        # Title divider line
        out_msp.add_line(
            (cx0, cy0 - TITLE_ZONE), (cx0 + CELL_W, cy0 - TITLE_ZONE),
            dxfattribs={"layer": "FRAME", "color": 9})

        # --- Title text ---
        out_msp.add_text(
            lname, height=350,
            dxfattribs={"layer": "TITLES", "color": color_idx,
                        "insert": (cx0 + 200, cy0 - 450)})

        # Subtitle: count + types
        types_str = ", ".join(
            f"{t}:{sum(1 for ee in entities if ee.dxftype() == t)}"
            for t in sorted(set(ee.dxftype() for ee in entities)))
        out_msp.add_text(
            f"{count} ent | {types_str}", height=140,
            dxfattribs={"layer": "TITLES", "color": 8,
                        "insert": (cx0 + 200, cy0 - 900)})

        # --- Scale & copy entities ---
        if lname not in layer_bounds:
            print(f"  [{idx+1:2d}/{len(sorted_layers)}] {lname:25s} — {count:5d} (no geometry)")
            continue

        b = layer_bounds[lname]
        src_w = b[2] - b[0]
        src_h = b[3] - b[1]

        # Avoid division by zero for degenerate layers
        if src_w < 0.001:
            src_w = 1.0
        if src_h < 0.001:
            src_h = 1.0

        # Scale to fit drawing area (maintain aspect ratio)
        sc = min(DRAW_W / src_w, DRAW_H / src_h)

        # Scaled content size
        scaled_w = src_w * sc
        scaled_h = src_h * sc

        # Target origin: center content in drawing area
        draw_x0 = cx0 + PADDING + (DRAW_W - scaled_w) / 2
        draw_y0 = cy0 - TITLE_ZONE - PADDING - (DRAW_H - scaled_h) / 2 - scaled_h

        # Source origin
        ox, oy = b[0], b[1]

        # Text height proportional to cell (readable)
        text_h = min(200, max(40, DRAW_H * 0.02))

        for e in entities:
            _copy_entity_xform(out_msp, e, ox, oy, sc, draw_x0, draw_y0,
                               safe_name, color_idx, text_h, src_doc=src_doc)

        print(f"  [{idx+1:2d}/{len(sorted_layers)}] {lname:25s} — {count:5d} ent, scale={sc:.4f}")

    # Save
    if output:
        out_path = Path(output)
    else:
        out_path = path.parent / f"{path.stem}_layer_catalog.dxf"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_doc.saveas(str(out_path))

    print(f"\nSaved: {out_path}")
    print("Open in AutoCAD -> ZOOM EXTENTS")


def main():
    parser = argparse.ArgumentParser(description="Generate DXF layer catalog")
    parser.add_argument("dxf_path", help="Source .dxf file")
    parser.add_argument("-o", "--output", help="Output DXF path")
    parser.add_argument("--cols", type=int, default=5, help="Grid columns (default 5)")
    args = parser.parse_args()

    path = Path(args.dxf_path)
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        sys.exit(1)

    build_layer_catalog(path, cols=args.cols, output=args.output)


if __name__ == "__main__":
    main()
