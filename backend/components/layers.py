"""
layers.py — Pointe Homes layer definitions + document setup.
This is the ONLY shared config — setup_doc() needs all layers at once.
Source: Seminole 2000 FARMHOUSE floorplan.dxf, verified 2026-03-11.
"""
import ezdxf

LAYERS = {
    "WALLS":            {"color": 7,   "lineweight": 60},
    "DOORS":            {"color": 157, "lineweight": 9},
    "WINS":             {"color": 121, "lineweight": -3},
    "DIMS":             {"color": 137, "lineweight": 15},
    "HATCH":            {"color": 123, "lineweight": 0},
    "FIXTURES":         {"color": 2,   "lineweight": 15},
    "ROOM LBLS":        {"color": 253, "lineweight": 30},
    "TEXT LBLS":        {"color": 81,  "lineweight": 18},
    "TEXT":             {"color": 7,   "lineweight": -3},
    "DOORTEXT":         {"color": 253, "lineweight": 20},
    "CABS-FLOORPLAN":   {"color": 4,   "lineweight": -3},
    "HEADERS":          {"color": 7,   "lineweight": 50},
    "ELECTRICAL":       {"color": 164, "lineweight": -3},
    "ELECTRICAL WALLS": {"color": 65,  "lineweight": 9},
    "MISC":             {"color": 3,   "lineweight": 30},
}


def setup_doc():
    """Create DXF document with all Pointe Homes layers. Returns (doc, msp)."""
    doc = ezdxf.new("R2018")
    doc.units = 1  # inches

    msp = doc.modelspace()

    for name, props in LAYERS.items():
        layer = doc.layers.new(name=name)
        layer.color = props["color"]
        lw = props["lineweight"]
        if lw > 0:
            layer.lineweight = lw

    return doc, msp
