"""Backward-compat barrel — re-exports from backend.measurement."""
from .observability import log_event
from .measurement.calibration import calibrate_scale, inches_to_feet_inches
from .measurement.flood_fill import (
    flood_fill_bbox,
    flood_fill_room_region,
    _build_closed_mask,
    _find_nearest_open,
    _flood_fill_area,
)
from .measurement.room_analysis import analyze_labeled_rooms
from .measurement.region_overlay import ROOM_PALETTE, generate_region_overlay, encode_overlay_png

__all__ = [
    "log_event",
    "calibrate_scale",
    "inches_to_feet_inches",
    "flood_fill_bbox",
    "flood_fill_room_region",
    "_build_closed_mask",
    "_find_nearest_open",
    "_flood_fill_area",
    "analyze_labeled_rooms",
    "ROOM_PALETTE",
    "generate_region_overlay",
    "encode_overlay_png",
]
