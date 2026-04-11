from ...observability import log_event
from .coord_transform import CoordTransform, setup_dim_style, _ensure_dot_block, _ensure_layers
from .exterior import (
    _classify_annotations,
    _wall_orientation,
    _wall_extent,
    _opening_on_wall,
    _opening_centerline,
    _opening_cross_coord,
    _find_exterior_walls,
    _annotation_exterior_segments,
    _merge_exterior_segments,
    _extract_exterior_segments_from_wall_mask,
    _building_centroid_from_segments,
    _assign_windows_to_segments,
    _building_centroid_px,
    _plan_width_dxf,
    _add_dim_along_wall,
)
from .formatting import _fmt_inches, _audit_dim_status, AUDIT_GEOMETRY_TOLERANCE_PX, AUDIT_GENERATED_GAP_TOLERANCE_PX
from .room_labels import _label_sizes, _render_manual_room_labels
from .room_metrics import _span_containing_seed, _best_local_seedline_span, _label_room_metrics
from .audit import _make_audit_summary, _log_audit_summary
from .generator import generate_all_dimensions

__all__ = [
    "CoordTransform",
    "setup_dim_style",
    "_ensure_dot_block",
    "_ensure_layers",
    "_classify_annotations",
    "_wall_orientation",
    "_wall_extent",
    "_opening_on_wall",
    "_opening_centerline",
    "_opening_cross_coord",
    "_find_exterior_walls",
    "_annotation_exterior_segments",
    "_merge_exterior_segments",
    "_extract_exterior_segments_from_wall_mask",
    "_building_centroid_from_segments",
    "_assign_windows_to_segments",
    "_building_centroid_px",
    "_plan_width_dxf",
    "_add_dim_along_wall",
    "_fmt_inches",
    "_audit_dim_status",
    "AUDIT_GEOMETRY_TOLERANCE_PX",
    "AUDIT_GENERATED_GAP_TOLERANCE_PX",
    "_label_sizes",
    "_render_manual_room_labels",
    "_span_containing_seed",
    "_best_local_seedline_span",
    "_label_room_metrics",
    "_make_audit_summary",
    "_log_audit_summary",
    "generate_all_dimensions",
]
