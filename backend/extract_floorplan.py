"""
extract_floorplan.py
Extrae TODO el contenido de floorplan.dwg en JSON estructurado.
Output: data/floorplan_extracted.json
"""
import ezdxf
import json
import math

DWG_PATH = "c:/Users/lucas/OneDrive/Escritorio/Point.ai/building Plans/SEMINOLE 2000/FARMHOUSE/floorplan.dxf"
OUT_PATH = "c:/Users/lucas/OneDrive/Escritorio/Point.ai/data/floorplan_extracted.json"

def r(v, decimals=2):
    """Round float, handle None."""
    if v is None:
        return None
    try:
        return round(float(v), decimals)
    except:
        return v

def extract_entity(e):
    t = e.dxftype()
    layer = e.dxf.layer if e.dxf.hasattr("layer") else "0"
    color = e.dxf.color if e.dxf.hasattr("color") else None
    lw = e.dxf.lineweight if e.dxf.hasattr("lineweight") else None

    base = {"type": t, "layer": layer}
    if color is not None:
        base["color"] = color
    if lw is not None:
        base["lineweight"] = lw

    if t == "LINE":
        s = e.dxf.start
        en = e.dxf.end
        base["start"] = [r(s.x), r(s.y)]
        base["end"]   = [r(en.x), r(en.y)]
        base["length"] = r(math.hypot(en.x - s.x, en.y - s.y))

    elif t == "ARC":
        c = e.dxf.center
        base["center"] = [r(c.x), r(c.y)]
        base["radius"] = r(e.dxf.radius)
        base["start_angle"] = r(e.dxf.start_angle)
        base["end_angle"]   = r(e.dxf.end_angle)

    elif t == "CIRCLE":
        c = e.dxf.center
        base["center"] = [r(c.x), r(c.y)]
        base["radius"] = r(e.dxf.radius)

    elif t in ("TEXT", "MTEXT"):
        try:
            base["text"] = e.dxf.text if t == "TEXT" else e.text
        except:
            base["text"] = ""
        try:
            ins = e.dxf.insert
            base["position"] = [r(ins.x), r(ins.y)]
        except:
            pass
        try:
            base["height"] = r(e.dxf.height)
        except:
            pass

    elif t == "LWPOLYLINE":
        pts = [[r(p[0]), r(p[1])] for p in e.get_points()]
        base["points"] = pts
        base["closed"] = e.closed

    elif t == "POLYLINE":
        try:
            pts = [[r(v.dxf.location.x), r(v.dxf.location.y)] for v in e.vertices]
            base["points"] = pts
        except:
            pass

    elif t == "INSERT":
        base["block_name"] = e.dxf.name
        ins = e.dxf.insert
        base["position"] = [r(ins.x), r(ins.y)]
        try:
            base["rotation"] = r(e.dxf.rotation)
        except:
            pass

    elif t == "DIMENSION":
        try:
            base["text"] = e.dxf.text
        except:
            pass
        try:
            base["measurement"] = r(e.get_measurement())
        except:
            pass

    elif t == "HATCH":
        base["pattern"] = e.dxf.pattern_name if e.dxf.hasattr("pattern_name") else None

    elif t == "SPLINE":
        try:
            pts = [[r(p[0]), r(p[1])] for p in e.control_points]
            base["control_points"] = pts[:10]  # max 10
        except:
            pass

    return base


def main():
    print(f"Opening: {DWG_PATH}")
    doc = ezdxf.readfile(DWG_PATH)
    msp = doc.modelspace()

    # ── LAYERS ────────────────────────────────────────────────────────────────
    layers_data = {}
    for layer in doc.layers:
        lw = layer.dxf.lineweight if layer.dxf.hasattr("lineweight") else -3
        col = layer.dxf.color if layer.dxf.hasattr("color") else 7
        layers_data[layer.dxf.name] = {
            "color": col,
            "lineweight": lw,
            "on": not layer.is_off(),
            "frozen": layer.is_frozen(),
        }

    # ── ENTITIES BY LAYER ─────────────────────────────────────────────────────
    by_layer = {}
    total = 0
    skipped = 0

    for e in msp:
        total += 1
        try:
            extracted = extract_entity(e)
            layer = extracted["layer"]
            if layer not in by_layer:
                by_layer[layer] = []
            by_layer[layer].append(extracted)
        except Exception as ex:
            skipped += 1

    # ── EXTENTS ───────────────────────────────────────────────────────────────
    all_x, all_y = [], []
    for ents in by_layer.values():
        for e in ents:
            if "start" in e:
                all_x.append(e["start"][0]); all_y.append(e["start"][1])
                all_x.append(e["end"][0]);   all_y.append(e["end"][1])
            elif "position" in e:
                all_x.append(e["position"][0]); all_y.append(e["position"][1])
            elif "center" in e:
                all_x.append(e["center"][0]); all_y.append(e["center"][1])

    extents = {}
    if all_x:
        extents = {
            "min_x": r(min(all_x)), "max_x": r(max(all_x)),
            "min_y": r(min(all_y)), "max_y": r(max(all_y)),
            "width":  r(max(all_x) - min(all_x)),
            "height": r(max(all_y) - min(all_y)),
        }

    # ── TEXT SUMMARY ──────────────────────────────────────────────────────────
    all_texts = []
    for ents in by_layer.values():
        for e in ents:
            if e["type"] in ("TEXT", "MTEXT") and e.get("text"):
                all_texts.append({
                    "text": e["text"].strip(),
                    "layer": e["layer"],
                    "position": e.get("position"),
                    "height": e.get("height"),
                })

    # ── LAYER SUMMARY ─────────────────────────────────────────────────────────
    layer_summary = {}
    for ln, ents in by_layer.items():
        type_counts = {}
        for e in ents:
            type_counts[e["type"]] = type_counts.get(e["type"], 0) + 1
        layer_summary[ln] = {
            "count": len(ents),
            "types": type_counts,
        }

    # ── OUTPUT ────────────────────────────────────────────────────────────────
    output = {
        "source": DWG_PATH,
        "total_entities": total,
        "skipped": skipped,
        "extents": extents,
        "layer_properties": layers_data,
        "layer_summary": layer_summary,
        "texts": all_texts,
        "entities_by_layer": by_layer,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nDone.")
    print(f"  Total entities : {total}")
    print(f"  Skipped        : {skipped}")
    print(f"  Layers         : {len(layers_data)}")
    print(f"  Texts found    : {len(all_texts)}")
    print(f"  Extents        : {extents}")
    print(f"\nOutput: {OUT_PATH}")

    # Quick layer summary print
    print("\nLayer breakdown:")
    for ln, s in sorted(layer_summary.items(), key=lambda x: -x[1]["count"]):
        print(f"  {ln:25s} {s['count']:4d} entities  {s['types']}")


if __name__ == "__main__":
    main()
