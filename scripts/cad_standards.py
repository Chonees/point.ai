# cad_standards.py — Pointe Homes CAD Standards
# Fuente: floorplan.dxf extraido y verificado 2026-03-11
# UNICA fuente de verdad para todos los generadores

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

WALL = {
    "thickness": 4,     # inches — dos LINEs paralelas a 4" de distancia
    "lineweight": 60,   # 0.60mm
    "color": 7,
}

DOOR = {
    "layer": "DOORS",
    "swing_angle": 90,
    "lineweight": 9,
}

WINDOW = {
    "layer": "WINS",
    "lineweight": -3,
}

UNITS = {
    "insunits": 2,      # 1 unit = 1 inch
}

TEXT = {
    "room_label_height": 9,
    "dim_text_height":   6,
}
