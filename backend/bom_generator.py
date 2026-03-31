"""
bom_generator.py — Bill of Materials from canonical structure.

Calculates wall lengths, opening counts, areas, and derived material estimates
from the structure JSON (walls + openings).
"""
from __future__ import annotations

import csv
import io
import math
from typing import Any


def generate_bom(structure: dict[str, Any]) -> dict[str, Any]:
    """Generate a Bill of Materials from the canonical structure."""
    walls = structure.get("walls") or []
    openings = structure.get("openings") or []
    meta = structure.get("structure_meta") or {}
    unit = meta.get("unit", "pixel")
    scale = float(meta.get("scale_hint") or 1.0) if unit == "pixel" else 1.0

    # Wall calculations
    wall_lengths: list[dict[str, Any]] = []
    total_length_in = 0.0
    exterior_length_in = 0.0
    interior_length_in = 0.0

    for wall in walls:
        poly = wall.get("polyline", [])
        if len(poly) < 2:
            continue
        p0, p1 = poly[0], poly[1]
        dx = float(p1["x"]) - float(p0["x"])
        dy = float(p1["y"]) - float(p0["y"])
        length_raw = math.sqrt(dx * dx + dy * dy)
        length_in = length_raw * scale if unit == "pixel" else length_raw

        is_ext = wall.get("is_exterior", False)
        total_length_in += length_in
        if is_ext:
            exterior_length_in += length_in
        else:
            interior_length_in += length_in

        wall_lengths.append({
            "id": wall.get("id", ""),
            "orientation": wall.get("orientation", ""),
            "is_exterior": is_ext,
            "length_in": round(length_in, 1),
            "length_ft": round(length_in / 12, 1),
        })

    # Opening calculations
    doors = [o for o in openings if o.get("kind") == "door"]
    windows = [o for o in openings if o.get("kind") == "window"]

    normal_doors = [d for d in doors if d.get("door_type", "normal") == "normal"]
    garage_doors = [d for d in doors if d.get("door_type") == "garage"]
    sliding_doors = [d for d in doors if d.get("door_type") == "sliding"]

    # Also count from annotations if present (ensemble mode — openings may be empty)
    ann_doors = 0
    ann_windows = 0
    region_plan = meta.get("dxf_region_plan") or {}
    # Count from provenance if available
    provenance = region_plan.get("meta", {}).get("provenance", {})
    if not doors and not windows:
        ann_doors = int(provenance.get("door_count", 0))
        ann_windows = int(provenance.get("window_count", 0))

    total_doors = len(doors) or ann_doors
    total_windows = len(windows) or ann_windows

    # Areas
    wall_height_in = 96.0  # 8 ft standard
    total_wall_area_sqft = (total_length_in * wall_height_in) / 144.0

    # Derived material estimates
    drywall_sheets = math.ceil(total_wall_area_sqft * 2 / 32)  # 2 sides, 4×8 sheets = 32 sqft
    studs_16oc = math.ceil(total_length_in / 16) + len(walls)  # +1 per wall end

    total_length_ft = total_length_in / 12

    summary = {
        "total_wall_length_ft": round(total_length_ft, 1),
        "exterior_wall_length_ft": round(exterior_length_in / 12, 1),
        "interior_wall_length_ft": round(interior_length_in / 12, 1),
        "total_wall_area_sqft": round(total_wall_area_sqft, 0),
        "wall_count": len(walls),
        "total_doors": total_doors,
        "normal_doors": len(normal_doors),
        "garage_doors": len(garage_doors),
        "sliding_doors": len(sliding_doors),
        "total_windows": total_windows,
        "unit": "inch" if unit != "pixel" else f"pixel (scale={scale:.3f})",
    }

    materials = [
        {"item": "Drywall 4×8 sheets", "qty": drywall_sheets, "unit": "sheets"},
        {"item": "2×4 Studs (16\" OC)", "qty": studs_16oc, "unit": "pcs"},
        {"item": "Interior doors", "qty": len(normal_doors) or ann_doors, "unit": "units"},
        {"item": "Garage doors", "qty": len(garage_doors), "unit": "units"},
        {"item": "Sliding doors", "qty": len(sliding_doors), "unit": "units"},
        {"item": "Windows", "qty": total_windows, "unit": "units"},
    ]
    # Remove zero-qty items
    materials = [m for m in materials if m["qty"] > 0]

    return {
        "summary": summary,
        "walls": wall_lengths,
        "materials": materials,
    }


def export_bom_csv(bom: dict[str, Any]) -> str:
    """Export BOM as CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Summary section
    writer.writerow(["=== SUMMARY ==="])
    writer.writerow(["Metric", "Value"])
    summary = bom.get("summary", {})
    writer.writerow(["Total Wall Length", f"{summary.get('total_wall_length_ft', 0)} ft"])
    writer.writerow(["Exterior Walls", f"{summary.get('exterior_wall_length_ft', 0)} ft"])
    writer.writerow(["Interior Walls", f"{summary.get('interior_wall_length_ft', 0)} ft"])
    writer.writerow(["Wall Area", f"{summary.get('total_wall_area_sqft', 0)} sqft"])
    writer.writerow(["Doors", summary.get("total_doors", 0)])
    writer.writerow(["Windows", summary.get("total_windows", 0)])
    writer.writerow([])

    # Materials section
    writer.writerow(["=== MATERIALS ==="])
    writer.writerow(["Item", "Quantity", "Unit"])
    for m in bom.get("materials", []):
        writer.writerow([m["item"], m["qty"], m["unit"]])
    writer.writerow([])

    # Wall detail
    writer.writerow(["=== WALL DETAIL ==="])
    writer.writerow(["ID", "Orientation", "Exterior", "Length (ft)"])
    for w in bom.get("walls", []):
        writer.writerow([w["id"], w["orientation"], w["is_exterior"], w["length_ft"]])

    return output.getvalue()
