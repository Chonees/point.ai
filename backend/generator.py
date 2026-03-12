"""
generator.py — Pointe Homes Floor Plan Generator (Orchestrator)
Recibe floor plan JSON -> produce .dxf profesional.
Uso: python generator.py input.json output.dxf

Logica de dibujo vive en components/. Este archivo solo coordina.
"""
import json
import sys

from components.layers import setup_doc
from components.walls import collect_walls, dedup_walls, draw_all_walls
from components.doors import draw_doors_for_room
from components.windows import draw_windows_for_room
from components.labels import draw_label


def generate(floor_plan: dict, out_path: str):
    """Generate a DXF floor plan from a JSON definition."""
    doc, msp = setup_doc()

    # Phase 1: Collect + deduplicate walls
    h_walls, v_walls = collect_walls(floor_plan["rooms"])
    v_walls = dedup_walls(v_walls)

    # Phase 2: Draw walls
    draw_all_walls(msp, h_walls, v_walls)

    # Phase 3: Doors, windows, labels
    for room in floor_plan["rooms"]:
        draw_doors_for_room(msp, room)
        draw_windows_for_room(msp, room)
        draw_label(msp, room["x"] + room["w"] / 2, room["y"] + room["h"] / 2, room["name"])

    doc.saveas(out_path)
    print(f"Saved: {out_path}")


# ─── TEST HOUSE ───────────────────────────────────────────────────────────────

TEST_HOUSE = {
    "model": "Test House",
    "rooms": [
        {
            "name": "GARAGE 1",
            "x": 0, "y": 0, "w": 380, "h": 248,
            "doors": [{"wall": "bottom", "offset": 40, "width": 144, "type": "garage"}],
        },
        {
            "name": "GARAGE 2",
            "x": 380, "y": 0, "w": 380, "h": 248,
            "doors": [{"wall": "bottom", "offset": 40, "width": 144, "type": "garage"}],
        },
        {
            "name": "LIVING",
            "x": 0, "y": 248, "w": 760, "h": 252,
            "doors": [{"wall": "bottom", "offset": 160, "width": 36}],
            "windows": [{"wall": "right", "offset": 80, "width": 60}],
        },
        {
            "name": "BED 1",
            "x": 0, "y": 500, "w": 190, "h": 204,
            "doors": [{"wall": "bottom", "offset": 20, "width": 32}],
            "windows": [{"wall": "top", "offset": 60, "width": 48}],
        },
        {
            "name": "BED 2",
            "x": 190, "y": 500, "w": 190, "h": 204,
            "doors": [{"wall": "bottom", "offset": 20, "width": 32}],
            "windows": [{"wall": "top", "offset": 60, "width": 48}],
        },
        {
            "name": "BED 3",
            "x": 380, "y": 500, "w": 190, "h": 204,
            "doors": [{"wall": "bottom", "offset": 20, "width": 32}],
            "windows": [{"wall": "top", "offset": 60, "width": 48}],
        },
        {
            "name": "BED 4",
            "x": 570, "y": 500, "w": 190, "h": 204,
            "doors": [{"wall": "bottom", "offset": 20, "width": 32}],
            "windows": [{"wall": "top", "offset": 60, "width": 48}],
        },
    ]
}

if __name__ == "__main__":
    if len(sys.argv) == 3:
        with open(sys.argv[1]) as f:
            plan = json.load(f)
        generate(plan, sys.argv[2])
    else:
        out = "C:/temp/test_house_modular.dxf"
        generate(TEST_HOUSE, out)
        print("Open in AutoCAD to verify.")
