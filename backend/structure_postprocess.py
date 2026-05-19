"""
structure_postprocess.py
Phase 3 geometric cleanup, junction graph, and anchoring for the v2 structure contract.

Pipeline:
  1. Normalize wall geometry
  2. Snap walls to clustered grid lines
  3. Snap wall endpoints to intersections (Phase 3)
  4. Merge colinear walls
  5. Build junction graph L/T/X (Phase 3)
  6. Classify exterior/interior with coverage heuristic (Phase 3)
  7. Anchor openings to valid walls
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from collections import defaultdict
from typing import Any

from .components.walls import INTERIOR_THICKNESS

EPSILON = 1e-6
DEFAULT_SNAP_TOLERANCE = 4.0
DEFAULT_JUNCTION_TOLERANCE = 6.0
DEFAULT_MERGE_GAP = 48.0
DEFAULT_MIN_WALL_LENGTH = 12.0
EXTERIOR_COVERAGE_THRESHOLD = 0.70

# Diagonal wall projection: walls within this angle of H/V are snapped to axis
from .geometry_utils import DIAGONAL_ANGLE_THRESHOLD_DEG, is_diagonal as _is_diagonal_wall

# Furniture filter: closed rectangles smaller than this area are furniture
DEFAULT_FURNITURE_MAX_AREA = 200.0 * 200.0   # 200x200 pixels max for furniture bboxes
FURNITURE_MIN_AREA = 4.0 * 4.0       # ignore trivially small detections

# Text filter: walls shorter than this with very low thickness are likely text
DEFAULT_TEXT_MAX_LENGTH = 60.0
DEFAULT_TEXT_MAX_THICKNESS = 6.0


@dataclass(frozen=True)
class PostprocessConfig:
    snap_tolerance: float = DEFAULT_SNAP_TOLERANCE
    junction_tolerance: float = DEFAULT_JUNCTION_TOLERANCE
    merge_gap: float = DEFAULT_MERGE_GAP
    min_wall_length: float = DEFAULT_MIN_WALL_LENGTH
    text_max_length: float = DEFAULT_TEXT_MAX_LENGTH
    text_max_thickness: float = DEFAULT_TEXT_MAX_THICKNESS
    furniture_max_area: float = DEFAULT_FURNITURE_MAX_AREA
    exterior_coverage_threshold: float = EXTERIOR_COVERAGE_THRESHOLD


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _resolve_postprocess_config(structure_meta: dict[str, Any]) -> PostprocessConfig:
    if structure_meta.get("unit") == "pixel":
        img_size = structure_meta.get("image_size", {})
        img_w = img_size.get("width", 1000) if isinstance(img_size, dict) else 1000
        scale = max(img_w / 500.0, 1.0)
        return PostprocessConfig(
            snap_tolerance=3.0 * scale,
            junction_tolerance=5.0 * scale,
            merge_gap=6.0 * scale,
            min_wall_length=5.0 * scale,
            text_max_length=30.0 * scale,
            text_max_thickness=2.0 * scale,
            furniture_max_area=(100.0 * scale) ** 2,
        )

    return PostprocessConfig()

def postprocess_structure(
    *,
    walls: list[dict[str, Any]],
    openings: list[dict[str, Any]],
    structure_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = _resolve_postprocess_config(structure_meta or {})
    review_flags: list[str] = []
    pipeline_debug: dict[str, Any] = {
        "config": asdict(config),
        "raw_segments": walls,
        "raw_openings": openings,
    }

    # Project near-axis diagonal walls to H/V before anything else
    projected, diag_count = _project_diagonal_walls(walls)
    pipeline_debug["projected_segments"] = projected
    if diag_count:
        review_flags.append(f"Projected {diag_count} near-axis diagonal wall(s) to H/V.")

    normalized_walls = [_normalize_wall_geometry(wall) for wall in projected]
    pipeline_debug["normalized_segments"] = normalized_walls

    snapped_walls = _snap_walls(normalized_walls, config=config)
    pipeline_debug["snapped_segments"] = snapped_walls

    snapped_intersections = _snap_to_intersections(snapped_walls, config=config)
    pipeline_debug["intersection_snapped_segments"] = snapped_intersections

    merged_walls = _merge_walls(snapped_intersections, config=config)
    pipeline_debug["merged_segments"] = merged_walls

    junctions = build_junction_graph(merged_walls, config=config)
    pipeline_debug["junctions"] = junctions
    classified_walls = _classify_walls_with_junctions(merged_walls, junctions, config=config)

    # Filter text artifacts only after junctions exist, so short real walls that
    # genuinely connect to the graph are not discarded prematurely.
    classified_walls, text_count = _filter_text_artifacts(classified_walls, junctions, config=config)
    if text_count:
        review_flags.append(f"Removed {text_count} text-like wall artifact(s).")
        junctions = build_junction_graph(classified_walls, config=config)
        classified_walls = _classify_walls_with_junctions(classified_walls, junctions, config=config)

    # Filter isolated noisy walls (dimension annotations, symbols with no junctions)
    classified_walls, isolated_noise_count = _filter_isolated_noisy_walls(classified_walls, junctions, config=config)
    if isolated_noise_count:
        review_flags.append(f"Removed {isolated_noise_count} isolated noisy wall segment(s).")
        junctions = build_junction_graph(classified_walls, config=config)
        classified_walls = _classify_walls_with_junctions(classified_walls, junctions, config=config)

    # Filter furniture-like openings (isolated small closed shapes not connected to walls)
    filtered_openings, furniture_count = _filter_furniture_openings(openings, classified_walls, config=config)
    if furniture_count:
        review_flags.append(f"Removed {furniture_count} furniture-like opening(s).")

    # Deduplicate overlapping openings on the same wall
    filtered_openings, dup_count = _deduplicate_openings(filtered_openings, classified_walls)
    if dup_count:
        review_flags.append(f"Removed {dup_count} duplicate/overlapping opening(s).")

    # Limit windows on exterior walls — too many signals false positives (deck junctions, etc.)
    filtered_openings, excess_count = _limit_exterior_wall_windows(filtered_openings, classified_walls)
    if excess_count:
        review_flags.append(f"Removed {excess_count} excess window(s) from dense exterior wall(s).")

    wall_map = {wall["id"]: wall for wall in classified_walls}
    anchored_openings, opening_metrics = _anchor_openings(
        filtered_openings,
        classified_walls,
        wall_map,
        review_flags,
        config=config,
    )
    pipeline_debug["anchored_openings"] = anchored_openings
    pipeline_debug["final_walls"] = classified_walls

    junction_summary = _summarize_junctions(junctions)

    metrics = {
        "raw_wall_count": len(walls),
        "snapped_wall_count": len(snapped_walls),
        "merged_wall_count": len(classified_walls),
        "raw_opening_count": len(openings),
        "anchored_opening_count": len(anchored_openings),
        **junction_summary,
        **opening_metrics,
    }

    return {
        "walls": classified_walls,
        "openings": anchored_openings,
        "junctions": junctions,
        "structure_meta": structure_meta or {},
        "metrics": metrics,
        "review_flags": review_flags,
        "pipeline_debug": pipeline_debug,
    }


# ---------------------------------------------------------------------------
# Junction graph (Phase 3)
# ---------------------------------------------------------------------------

def build_junction_graph(
    walls: list[dict[str, Any]],
    *,
    config: PostprocessConfig | None = None,
) -> list[dict[str, Any]]:
    """
    Detect L, T, and X junctions between walls.

    A junction is a point where two or more walls meet or cross.
    - L: two walls meet at an endpoint-to-endpoint corner
    - T: one wall's endpoint touches another wall's body
    - X: two walls cross each other through their bodies
    """
    resolved = config or PostprocessConfig()
    h_walls = [w for w in walls if w["orientation"] == "horizontal"]
    v_walls = [w for w in walls if w["orientation"] == "vertical"]

    junctions: list[dict[str, Any]] = []
    seen_points: dict[tuple[float, float], dict[str, Any]] = {}

    for hw in h_walls:
        hy = hw["polyline"][0]["y"]
        hx1 = hw["polyline"][0]["x"]
        hx2 = hw["polyline"][1]["x"]

        for vw in v_walls:
            pair_tolerance = _wall_connection_tolerance(hw, vw, config=resolved)
            vx = vw["polyline"][0]["x"]
            vy1 = vw["polyline"][0]["y"]
            vy2 = vw["polyline"][1]["y"]

            # Check if they intersect or are close enough
            if vx < hx1 - pair_tolerance or vx > hx2 + pair_tolerance:
                continue
            if hy < vy1 - pair_tolerance or hy > vy2 + pair_tolerance:
                continue

            point = (round(vx, 2), round(hy, 2))
            junction_type = _classify_junction(hx1, hx2, hy, vx, vy1, vy2, pair_tolerance)

            if point in seen_points:
                existing = seen_points[point]
                if hw["id"] not in existing["wall_ids"]:
                    existing["wall_ids"].append(hw["id"])
                if vw["id"] not in existing["wall_ids"]:
                    existing["wall_ids"].append(vw["id"])
                # Upgrade type: L < T < X
                existing["type"] = _upgrade_junction_type(existing["type"], junction_type)
            else:
                junction = {
                    "point": {"x": point[0], "y": point[1]},
                    "type": junction_type,
                    "wall_ids": [hw["id"], vw["id"]],
                }
                seen_points[point] = junction
                junctions.append(junction)

    return junctions


def _classify_junction(
    hx1: float, hx2: float, hy: float,
    vx: float, vy1: float, vy2: float,
    tolerance: float,
) -> str:
    """Determine if junction is L, T, or X based on endpoint proximity."""
    h_at_left = abs(vx - hx1) <= tolerance
    h_at_right = abs(vx - hx2) <= tolerance
    h_endpoint = h_at_left or h_at_right

    v_at_top = abs(hy - vy1) <= tolerance
    v_at_bottom = abs(hy - vy2) <= tolerance
    v_endpoint = v_at_top or v_at_bottom

    if h_endpoint and v_endpoint:
        return "L"
    if h_endpoint or v_endpoint:
        return "T"
    return "X"


def _upgrade_junction_type(existing: str, new: str) -> str:
    rank = {"L": 0, "T": 1, "X": 2}
    return existing if rank.get(existing, 0) >= rank.get(new, 0) else new


def _summarize_junctions(junctions: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {"L": 0, "T": 0, "X": 0}
    for j in junctions:
        counts[j["type"]] = counts.get(j["type"], 0) + 1
    return {
        "junction_count": len(junctions),
        "junction_L": counts["L"],
        "junction_T": counts["T"],
        "junction_X": counts["X"],
    }


def _connected_wall_ids(junctions: list[dict[str, Any]]) -> set[str]:
    connected_ids: set[str] = set()
    for junction in junctions:
        for wall_id in junction.get("wall_ids", []):
            connected_ids.add(wall_id)
    return connected_ids


def _wall_connection_tolerance(
    wall_a: dict[str, Any],
    wall_b: dict[str, Any],
    *,
    config: PostprocessConfig | None = None,
) -> float:
    resolved = config or PostprocessConfig()
    thickness_a = float(wall_a.get("thickness", 4.0))
    thickness_b = float(wall_b.get("thickness", 4.0))
    adaptive = max(thickness_a, thickness_b) / 2.0 + resolved.snap_tolerance
    return min(max(resolved.junction_tolerance, adaptive), resolved.junction_tolerance * 2.5)


def _supported_wall_ids(walls: list[dict[str, Any]], *, config: PostprocessConfig | None = None) -> set[str]:
    resolved = config or PostprocessConfig()
    supported_ids: set[str] = set()
    for wall in walls:
        for other in walls:
            if wall["id"] == other["id"] or wall["orientation"] == other["orientation"]:
                continue
            tolerance = _wall_connection_tolerance(wall, other, config=resolved)
            if _wall_has_endpoint_support(wall, other, tolerance):
                supported_ids.add(wall["id"])
                break
    return supported_ids


def _wall_has_endpoint_support(
    wall: dict[str, Any],
    other: dict[str, Any],
    tolerance: float,
) -> bool:
    start, end = wall["polyline"]
    other_start, other_end = other["polyline"]

    if wall["orientation"] == "horizontal" and other["orientation"] == "vertical":
        wall_y = float(start["y"])
        other_x = float(other_start["x"])
        other_y1 = min(float(other_start["y"]), float(other_end["y"]))
        other_y2 = max(float(other_start["y"]), float(other_end["y"]))
        if wall_y < other_y1 - tolerance or wall_y > other_y2 + tolerance:
            return False
        return any(abs(float(point["x"]) - other_x) <= tolerance for point in (start, end))

    if wall["orientation"] == "vertical" and other["orientation"] == "horizontal":
        wall_x = float(start["x"])
        other_y = float(other_start["y"])
        other_x1 = min(float(other_start["x"]), float(other_end["x"]))
        other_x2 = max(float(other_start["x"]), float(other_end["x"]))
        if wall_x < other_x1 - tolerance or wall_x > other_x2 + tolerance:
            return False
        return any(abs(float(point["y"]) - other_y) <= tolerance for point in (start, end))

    return False


# ---------------------------------------------------------------------------
# Snap to intersections (Phase 3)
# ---------------------------------------------------------------------------

def _snap_to_intersections(
    walls: list[dict[str, Any]],
    *,
    config: PostprocessConfig | None = None,
) -> list[dict[str, Any]]:
    """
    Snap wall endpoints to nearby wall intersections.

    When a horizontal wall's endpoint is close to a vertical wall's axis
    (or vice versa), extend/trim the endpoint to meet exactly.
    """
    resolved = config or PostprocessConfig()
    h_walls = [w for w in walls if w["orientation"] == "horizontal"]
    v_walls = [w for w in walls if w["orientation"] == "vertical"]

    v_x_coords = [w["polyline"][0]["x"] for w in v_walls]
    h_y_coords = [w["polyline"][0]["y"] for w in h_walls]

    result = []
    for wall in walls:
        start, end = wall["polyline"]
        if wall["orientation"] == "diagonal":
            result.append(wall)
        elif wall["orientation"] == "horizontal":
            new_x1 = _snap_endpoint_to_axes(start["x"], v_x_coords, resolved.junction_tolerance)
            new_x2 = _snap_endpoint_to_axes(end["x"], v_x_coords, resolved.junction_tolerance)
            result.append({
                **wall,
                "polyline": [
                    {"x": new_x1, "y": start["y"]},
                    {"x": new_x2, "y": end["y"]},
                ],
            })
        else:
            new_y1 = _snap_endpoint_to_axes(start["y"], h_y_coords, resolved.junction_tolerance)
            new_y2 = _snap_endpoint_to_axes(end["y"], h_y_coords, resolved.junction_tolerance)
            result.append({
                **wall,
                "polyline": [
                    {"x": start["x"], "y": new_y1},
                    {"x": end["x"], "y": new_y2},
                ],
            })
    return result


def _snap_endpoint_to_axes(value: float, axes: list[float], tolerance: float) -> float:
    """Snap a value to the nearest axis if within tolerance."""
    if not axes:
        return value
    best = min(axes, key=lambda a: abs(a - value))
    if abs(best - value) <= tolerance:
        return best
    return value


# ---------------------------------------------------------------------------
# Improved exterior/interior classification (Phase 3)
# ---------------------------------------------------------------------------

def _classify_walls_with_junctions(
    walls: list[dict[str, Any]],
    junctions: list[dict[str, Any]],
    *,
    config: PostprocessConfig | None = None,
) -> list[dict[str, Any]]:
    """
    Classify walls as exterior or interior via 6-ray line-of-sight.

    For each wall we evaluate two FACE points (perpendicular offset from the
    centerline). From each face point we cast 3 rays away from the wall body
    (the ray that would pierce the wall is omitted). A face is "exposed to
    outside" iff at least one of its 3 rays reaches the global bbox edge
    without crossing another wall. The wall is EXTERIOR iff at least one
    face is exposed.

    Robust against any plan shape: rectangular, L, U, bump-outs, internal
    courtyards. The U-notch case (open space parallel to a wall) is handled
    correctly because each face casts axial rays in BOTH the perpendicular
    AND parallel directions.

    Junction connectivity is preserved as a confidence-only signal.
    """
    resolved = config or PostprocessConfig()
    if not walls:
        return []

    all_points = [p for w in walls for p in w["polyline"]]
    min_x = min(p["x"] for p in all_points)
    max_x = max(p["x"] for p in all_points)
    min_y = min(p["y"] for p in all_points)
    max_y = max(p["y"] for p in all_points)

    # Pre-index axis-aligned walls for fast ray casting.
    h_index: list[tuple[float, float, float, str]] = []
    v_index: list[tuple[float, float, float, str]] = []
    for w in walls:
        p1, p2 = w["polyline"]
        ori = w.get("orientation")
        if ori == "horizontal":
            h_index.append((float(p1["y"]),
                            float(min(p1["x"], p2["x"])),
                            float(max(p1["x"], p2["x"])),
                            w["id"]))
        elif ori == "vertical":
            v_index.append((float(p1["x"]),
                            float(min(p1["y"], p2["y"])),
                            float(max(p1["y"], p2["y"])),
                            w["id"]))

    # eps must exceed half the maximum wall thickness so face points fall
    # OUTSIDE the wall body. span_tol is kept tight so wall endpoints don't
    # spuriously block adjacent rays at L/T/X corners.
    eps = 4.0
    span_tol = 0.5

    def _vray_clear(x: float, y_lo: float, y_hi: float, exclude_id: str) -> bool:
        """Vertical ray at column x from y_lo to y_hi: clear iff no horizontal wall blocks."""
        if y_lo >= y_hi:
            return True
        for hy, hx1, hx2, hid in h_index:
            if hid == exclude_id:
                continue
            if y_lo <= hy <= y_hi and (hx1 - span_tol) <= x <= (hx2 + span_tol):
                return False
        return True

    def _hray_clear(y: float, x_lo: float, x_hi: float, exclude_id: str) -> bool:
        """Horizontal ray at row y from x_lo to x_hi: clear iff no vertical wall blocks."""
        if x_lo >= x_hi:
            return True
        for vx, vy1, vy2, vid in v_index:
            if vid == exclude_id:
                continue
            if x_lo <= vx <= x_hi and (vy1 - span_tol) <= y <= (vy2 + span_tol):
                return False
        return True

    # Build junction connectivity per wall (used only to boost confidence).
    wall_junction_count: dict[str, int] = defaultdict(int)
    for j in junctions:
        for wid in j["wall_ids"]:
            wall_junction_count[wid] += 1

    classified = []
    for wall in walls:
        start, end = wall["polyline"]
        side = None
        is_exterior = False
        ori = wall.get("orientation")
        wid = wall["id"]

        if ori == "horizontal":
            mx = (float(start["x"]) + float(end["x"])) / 2.0
            wy = float(start["y"])

            # Top face: cast UP, LEFT, RIGHT (the DOWN ray would pierce the wall).
            face_y = wy + eps
            top_clear = (
                _vray_clear(mx, face_y, max_y + 1.0, wid)
                or _hray_clear(face_y, min_x - 1.0, mx, wid)
                or _hray_clear(face_y, mx, max_x + 1.0, wid)
            )

            # Bottom face: cast DOWN, LEFT, RIGHT.
            face_y = wy - eps
            bottom_clear = (
                _vray_clear(mx, min_y - 1.0, face_y, wid)
                or _hray_clear(face_y, min_x - 1.0, mx, wid)
                or _hray_clear(face_y, mx, max_x + 1.0, wid)
            )

            if top_clear and not bottom_clear:
                is_exterior = True
                side = "top"
            elif bottom_clear and not top_clear:
                is_exterior = True
                side = "bottom"
            elif top_clear and bottom_clear:
                is_exterior = True
                side = "top" if abs(wy - max_y) <= abs(wy - min_y) else "bottom"

        elif ori == "vertical":
            wx = float(start["x"])
            my = (float(start["y"]) + float(end["y"])) / 2.0

            # Right face: cast RIGHT, UP, DOWN (LEFT ray would pierce the wall).
            face_x = wx + eps
            right_clear = (
                _hray_clear(my, face_x, max_x + 1.0, wid)
                or _vray_clear(face_x, my, max_y + 1.0, wid)
                or _vray_clear(face_x, min_y - 1.0, my, wid)
            )

            # Left face: cast LEFT, UP, DOWN.
            face_x = wx - eps
            left_clear = (
                _hray_clear(my, min_x - 1.0, face_x, wid)
                or _vray_clear(face_x, my, max_y + 1.0, wid)
                or _vray_clear(face_x, min_y - 1.0, my, wid)
            )

            if right_clear and not left_clear:
                is_exterior = True
                side = "right"
            elif left_clear and not right_clear:
                is_exterior = True
                side = "left"
            elif right_clear and left_clear:
                is_exterior = True
                side = "right" if abs(wx - max_x) <= abs(wx - min_x) else "left"
        # Diagonal walls: keep defaults (not exterior, no side).

        confidence = wall["confidence"]
        if is_exterior:
            confidence = min(0.995, confidence + 0.05)

        jcount = wall_junction_count.get(wid, 0)
        if jcount >= 2:
            confidence = min(0.995, confidence + 0.03)

        classified.append({
            **wall,
            "is_exterior": is_exterior,
            "side": side,
            "confidence": round(confidence, 4),
        })

    return classified


# ---------------------------------------------------------------------------
# Diagonal wall projection (Fase 4)
# ---------------------------------------------------------------------------

def _project_diagonal_walls(
    walls: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Project walls that are near-horizontal or near-vertical onto their axis.

    If the angle from horizontal is < DIAGONAL_ANGLE_THRESHOLD_DEG, snap to H.
    If the angle from vertical is < DIAGONAL_ANGLE_THRESHOLD_DEG, snap to V.
    Walls that are too diagonal (>15° from both axes) are kept unchanged.
    """
    import math
    projected = []
    count = 0
    threshold_rad = math.radians(DIAGONAL_ANGLE_THRESHOLD_DEG)

    for wall in walls:
        points = wall.get("polyline") or []
        if len(points) != 2:
            projected.append(wall)
            continue

        p0 = points[0]
        p1 = points[1]
        dx = float(p1["x"]) - float(p0["x"])
        dy = float(p1["y"]) - float(p0["y"])
        length = (dx * dx + dy * dy) ** 0.5
        if length < EPSILON:
            projected.append(wall)
            continue

        # Skip walls already axis-aligned — nothing to project
        if abs(dy) < EPSILON or abs(dx) < EPSILON:
            projected.append(wall)
            continue

        angle_from_h = abs(math.atan2(abs(dy), abs(dx)))  # 0=horizontal, pi/2=vertical
        angle_from_v = abs(math.pi / 2 - angle_from_h)

        if angle_from_h <= threshold_rad:
            # Project to horizontal: average y
            y_avg = (float(p0["y"]) + float(p1["y"])) / 2.0
            x1 = min(float(p0["x"]), float(p1["x"]))
            x2 = max(float(p0["x"]), float(p1["x"]))
            projected.append({
                **wall,
                "orientation": "horizontal",
                "polyline": [{"x": x1, "y": y_avg}, {"x": x2, "y": y_avg}],
            })
            count += 1
        elif angle_from_v <= threshold_rad:
            # Project to vertical: average x
            x_avg = (float(p0["x"]) + float(p1["x"])) / 2.0
            y1 = min(float(p0["y"]), float(p1["y"]))
            y2 = max(float(p0["y"]), float(p1["y"]))
            projected.append({
                **wall,
                "orientation": "vertical",
                "polyline": [{"x": x_avg, "y": y1}, {"x": x_avg, "y": y2}],
            })
            count += 1
        else:
            projected.append(wall)

    return projected, count


# ---------------------------------------------------------------------------
# Text artifact filter (Fase 4)
# ---------------------------------------------------------------------------

def _filter_text_artifacts(
    walls: list[dict[str, Any]],
    junctions: list[dict[str, Any]],
    *,
    config: PostprocessConfig | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Remove wall segments that are likely text or dimension labels.

    Heuristic: a segment is text-like when it is compact (length ~= thickness),
    short, and not structurally connected. This avoids filtering long thin wall
    returns that the model detected correctly but that happen to be short.
    """
    resolved = config or PostprocessConfig()
    connected_ids = _connected_wall_ids(junctions)
    supported_ids = _supported_wall_ids(walls, config=resolved)
    filtered = []
    removed = 0
    for wall in walls:
        points = wall.get("polyline") or []
        if len(points) != 2:
            filtered.append(wall)
            continue
        p0, p1 = points
        dx = float(p1["x"]) - float(p0["x"])
        dy = float(p1["y"]) - float(p0["y"])
        length = (dx * dx + dy * dy) ** 0.5
        thickness = float(wall.get("thickness", 4.0))
        aspect_ratio = length / max(thickness, EPSILON)
        is_supported = (
            wall["id"] in connected_ids
            or wall["id"] in supported_ids
            or bool(wall.get("is_exterior", False))
        )
        if (
            not is_supported
            and length < resolved.text_max_length
            and thickness < resolved.text_max_thickness
            and aspect_ratio < 3.0
        ):
            removed += 1
        else:
            filtered.append(wall)
    return filtered, removed


# ---------------------------------------------------------------------------
# Furniture opening filter (Fase 4)
# ---------------------------------------------------------------------------

def _filter_furniture_openings(
    openings: list[dict[str, Any]],
    walls: list[dict[str, Any]],
    *,
    config: PostprocessConfig | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Remove opening detections that are not near any wall.

    An opening that cannot be placed within SNAP_TOLERANCE of any wall axis
    is likely a furniture contour (closed small rectangle) and should be dropped.
    """
    resolved = config or PostprocessConfig()
    if not walls:
        return openings, 0

    # Build a set of (orientation, coord, span_start, span_end) for quick lookup
    wall_axes: list[dict[str, Any]] = []
    for wall in walls:
        if len(wall.get("polyline", [])) != 2:
            continue
        start, end = wall["polyline"]
        if wall["orientation"] == "horizontal":
            wall_axes.append({
                "orientation": "horizontal",
                "coord": float(start["y"]),
                "span_start": float(start["x"]),
                "span_end": float(end["x"]),
            })
        else:
            wall_axes.append({
                "orientation": "vertical",
                "coord": float(start["x"]),
                "span_start": float(start["y"]),
                "span_end": float(end["y"]),
            })

    kept = []
    removed = 0
    for opening in openings:
        span = float(opening.get("span", 0))
        area = span * span  # bounding square approximation

        # Keep openings with large span — they can't be furniture
        if span > 200:
            kept.append(opening)
            continue

        pos = opening.get("position")
        if pos is None:
            kept.append(opening)
            continue

        px = float(pos["x"])
        py = float(pos["y"])
        half = span / 2.0

        near_wall = False
        for axis in wall_axes:
            if axis["orientation"] == "horizontal":
                if abs(py - axis["coord"]) <= resolved.snap_tolerance * 3:
                    if px - half <= axis["span_end"] + resolved.snap_tolerance and px + half >= axis["span_start"] - resolved.snap_tolerance:
                        near_wall = True
                        break
            else:
                if abs(px - axis["coord"]) <= resolved.snap_tolerance * 3:
                    if py - half <= axis["span_end"] + resolved.snap_tolerance and py + half >= axis["span_start"] - resolved.snap_tolerance:
                        near_wall = True
                        break

        if near_wall:
            kept.append(opening)
        else:
            removed += 1

    return kept, removed


# ---------------------------------------------------------------------------
# Isolated noisy wall filter
# ---------------------------------------------------------------------------

def _filter_isolated_noisy_walls(
    walls: list[dict[str, Any]],
    junctions: list[dict[str, Any]],
    *,
    config: PostprocessConfig | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Remove short isolated wall segments caused by dimension annotations or symbols.

    Walls with no junctions whose thickness-to-length ratio exceeds 0.4 are
    almost certainly CAD annotation artifacts rather than structural walls.
    """
    resolved = config or PostprocessConfig()
    connected_ids = _connected_wall_ids(junctions)
    supported_ids = _supported_wall_ids(walls, config=resolved)

    filtered = []
    removed = 0
    for wall in walls:
        length = _wall_length(wall)
        thickness = float(wall.get("thickness", 4.0))
        is_supported = (
            wall["id"] in connected_ids
            or wall["id"] in supported_ids
            or bool(wall.get("is_exterior", False))
        )
        if is_supported:
            filtered.append(wall)
            continue
        # High thickness-to-length ratio on UNCONNECTED walls = dimension symbol or
        # annotation artifact.  Structurally connected walls are kept regardless of
        # ratio because corner polygons from CubiCasa can appear nearly square.
        if length > 0 and thickness / length > 0.55 and length < resolved.min_wall_length * 2:
            removed += 1
            continue
        # Also drop short unconnected walls
        if length < max(resolved.min_wall_length * 1.5, thickness * 2.0):
            removed += 1
            continue
        filtered.append(wall)
    return filtered, removed


# ---------------------------------------------------------------------------
# Opening deduplication
# ---------------------------------------------------------------------------

def _deduplicate_openings(
    openings: list[dict[str, Any]],
    walls: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Remove openings that overlap more than 50% with a larger opening on the same wall.

    CubiCasa sometimes emits multiple nearby detections for the same window or door.
    Keep the one with the larger span when two same-kind openings heavily overlap.
    """
    wall_map = {w["id"]: w for w in walls}

    by_wall_kind: dict[tuple[str | None, str], list[dict[str, Any]]] = defaultdict(list)
    for op in openings:
        by_wall_kind[(op.get("wall_id"), op["kind"])].append(op)

    kept: list[dict[str, Any]] = []
    removed = 0
    for (wall_id, _kind), ops in by_wall_kind.items():
        if len(ops) <= 1:
            kept.extend(ops)
            continue

        wall = wall_map.get(wall_id) if wall_id else None
        if wall is None:
            kept.extend(ops)
            continue

        axis_key = "x" if wall["orientation"] == "horizontal" else "y"
        ops_sorted = sorted(ops, key=lambda o: o["position"][axis_key])

        wall_kept: list[dict[str, Any]] = []
        for op in ops_sorted:
            span = op["span"]
            center = op["position"][axis_key]
            op_start = center - span / 2
            op_end = center + span / 2

            overlapping_with = None
            for k_op in wall_kept:
                k_span = k_op["span"]
                k_center = k_op["position"][axis_key]
                k_start = k_center - k_span / 2
                k_end = k_center + k_span / 2
                overlap = max(0.0, min(op_end, k_end) - max(op_start, k_start))
                min_span = min(span, k_span)
                if min_span > 0 and overlap / min_span > 0.5:
                    overlapping_with = k_op
                    break

            if overlapping_with is None:
                wall_kept.append(op)
            elif op["span"] > overlapping_with["span"]:
                wall_kept.remove(overlapping_with)
                wall_kept.append(op)
                removed += 1
            else:
                removed += 1

        kept.extend(wall_kept)

    return kept, removed


# ---------------------------------------------------------------------------
# Exterior wall window density filter
# ---------------------------------------------------------------------------

_MAX_WINDOWS_PER_EXTERIOR_WALL = 3


def _limit_exterior_wall_windows(
    openings: list[dict[str, Any]],
    walls: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Cap the number of windows on any single exterior wall to MAX_WINDOWS_PER_EXTERIOR_WALL.

    CubiCasa often fires many small window detections where a deck or extension
    attaches to an exterior wall. When a wall has more windows than the cap,
    keep only the largest ones (by span).
    """
    wall_map = {w["id"]: w for w in walls}

    windows_by_wall: dict[str, list[dict[str, Any]]] = defaultdict(list)
    other_openings: list[dict[str, Any]] = []

    for op in openings:
        if op["kind"] == "window":
            windows_by_wall[op.get("wall_id", "")].append(op)
        else:
            other_openings.append(op)

    kept_windows: list[dict[str, Any]] = []
    removed = 0
    for wall_id, wins in windows_by_wall.items():
        wall = wall_map.get(wall_id)
        if wall is None or not wall.get("is_exterior", False):
            kept_windows.extend(wins)
        elif len(wins) <= _MAX_WINDOWS_PER_EXTERIOR_WALL:
            kept_windows.extend(wins)
        else:
            wins_sorted = sorted(wins, key=lambda o: o["span"], reverse=True)
            kept_windows.extend(wins_sorted[:_MAX_WINDOWS_PER_EXTERIOR_WALL])
            removed += len(wins) - _MAX_WINDOWS_PER_EXTERIOR_WALL

    return other_openings + kept_windows, removed


# ---------------------------------------------------------------------------
# Normalize + Snap + Merge (from Phase 2, preserved)
# ---------------------------------------------------------------------------

def _normalize_wall_geometry(wall: dict[str, Any]) -> dict[str, Any]:
    points = wall.get("polyline") or []
    if len(points) != 2:
        raise ValueError("postprocess only supports 2-point walls")

    start = _point(points[0])
    end = _point(points[1])
    orientation = wall.get("orientation") or _orientation(start, end)
    if orientation == "horizontal" and start["x"] > end["x"]:
        start, end = end, start
    if orientation == "vertical" and start["y"] > end["y"]:
        start, end = end, start
    if orientation == "diagonal" and start["x"] > end["x"]:
        start, end = end, start

    return {
        "id": wall.get("id"),
        "orientation": orientation,
        "polyline": [start, end],
        "thickness": float(wall.get("thickness", 4.0)),
        "confidence": float(wall.get("confidence", 1.0)),
        "is_exterior": bool(wall.get("is_exterior", False)),
        "side": wall.get("side"),
    }


def _snap_walls(
    walls: list[dict[str, Any]],
    *,
    config: PostprocessConfig | None = None,
) -> list[dict[str, Any]]:
    resolved = config or PostprocessConfig()
    if not walls:
        return []

    h_coords = _cluster_values(
        [wall["polyline"][0]["y"] for wall in walls if wall["orientation"] == "horizontal"],
        tolerance=resolved.snap_tolerance,
    )
    v_coords = _cluster_values(
        [wall["polyline"][0]["x"] for wall in walls if wall["orientation"] == "vertical"],
        tolerance=resolved.snap_tolerance,
    )
    x_values = _cluster_values(
        [point["x"] for wall in walls for point in wall["polyline"] if wall["orientation"] == "horizontal"],
        tolerance=resolved.snap_tolerance,
    )
    y_values = _cluster_values(
        [point["y"] for wall in walls for point in wall["polyline"] if wall["orientation"] == "vertical"],
        tolerance=resolved.snap_tolerance,
    )

    snapped = []
    for wall in walls:
        start, end = wall["polyline"]
        if wall["orientation"] == "diagonal":
            # Pass diagonal walls through without axis-snapping
            snapped.append(wall)
        elif wall["orientation"] == "horizontal":
            y = _snap_value(start["y"], h_coords, tolerance=resolved.snap_tolerance)
            snapped.append(
                {
                    **wall,
                    "polyline": [
                        {"x": _snap_value(start["x"], x_values, tolerance=resolved.snap_tolerance), "y": y},
                        {"x": _snap_value(end["x"], x_values, tolerance=resolved.snap_tolerance), "y": y},
                    ],
                }
            )
        else:
            x = _snap_value(start["x"], v_coords, tolerance=resolved.snap_tolerance)
            snapped.append(
                {
                    **wall,
                    "polyline": [
                        {"x": x, "y": _snap_value(start["y"], y_values, tolerance=resolved.snap_tolerance)},
                        {"x": x, "y": _snap_value(end["y"], y_values, tolerance=resolved.snap_tolerance)},
                    ],
                }
            )
    return snapped


def _merge_walls(
    walls: list[dict[str, Any]],
    *,
    config: PostprocessConfig | None = None,
) -> list[dict[str, Any]]:
    resolved = config or PostprocessConfig()
    # Diagonal walls can't be merged — pass through directly
    diagonals = [w for w in walls if w["orientation"] == "diagonal"]
    hv_walls = [w for w in walls if w["orientation"] != "diagonal"]
    grouped: dict[tuple[str, float], list[dict[str, Any]]] = defaultdict(list)
    for wall in hv_walls:
        coord = wall["polyline"][0]["y"] if wall["orientation"] == "horizontal" else wall["polyline"][0]["x"]
        grouped[(wall["orientation"], coord)].append(wall)

    merged = []
    counter = 0
    for (orientation, coord), group in grouped.items():
        spans = []
        for wall in group:
            start, end = _wall_span(wall)
            spans.append((start, end, wall))
        spans.sort(key=lambda item: item[0])

        current_start, current_end, current_walls = spans[0][0], spans[0][1], [spans[0][2]]
        for start, end, wall in spans[1:]:
            if start <= current_end + resolved.merge_gap:
                current_end = max(current_end, end)
                current_walls.append(wall)
            else:
                merged_wall = _build_merged_wall(
                    orientation,
                    coord,
                    current_start,
                    current_end,
                    current_walls,
                    counter + 1,
                )
                if _wall_length(merged_wall) >= resolved.min_wall_length:
                    merged.append(merged_wall)
                    counter += 1
                current_start, current_end, current_walls = start, end, [wall]

        merged_wall = _build_merged_wall(
            orientation,
            coord,
            current_start,
            current_end,
            current_walls,
            counter + 1,
        )
        if _wall_length(merged_wall) >= resolved.min_wall_length:
            merged.append(merged_wall)
            counter += 1

    merged.extend(diagonals)
    return merged


def _build_merged_wall(
    orientation: str,
    coord: float,
    start: float,
    end: float,
    source_walls: list[dict[str, Any]],
    counter: int,
) -> dict[str, Any]:
    avg_confidence = sum(wall["confidence"] for wall in source_walls) / len(source_walls)
    if orientation == "horizontal":
        polyline = [{"x": start, "y": coord}, {"x": end, "y": coord}]
    else:
        polyline = [{"x": coord, "y": start}, {"x": coord, "y": end}]
    # Thickness is a placeholder here. The framing rule (exterior=2x6,
    # interior=2x4) is applied downstream in structural_generator after the
    # wall is classified by `_classify_walls_with_junctions`.
    return {
        "id": f"wall-{counter:04d}",
        "orientation": orientation,
        "polyline": polyline,
        "thickness": float(INTERIOR_THICKNESS),
        "confidence": round(min(0.99, avg_confidence + 0.15), 4),
        "is_exterior": False,
        "side": None,
    }


# ---------------------------------------------------------------------------
# Opening anchoring (from Phase 2, preserved)
# ---------------------------------------------------------------------------

def _anchor_openings(
    openings: list[dict[str, Any]],
    walls: list[dict[str, Any]],
    wall_map: dict[str, dict[str, Any]],
    review_flags: list[str],
    *,
    config: PostprocessConfig | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    resolved = config or PostprocessConfig()
    anchored = []
    filtered = 0
    inferred_side_count = 0

    def _pick_wall(normalized_opening: dict[str, Any]) -> dict[str, Any] | None:
        if normalized_opening.get("wall_id") and normalized_opening["wall_id"] in wall_map:
            return wall_map[normalized_opening["wall_id"]]
        return _find_best_wall(normalized_opening, walls, config=resolved)

    for counter, opening in enumerate(openings, start=1):
        normalized = _normalize_opening(opening, counter)
        wall = _pick_wall(normalized)

        if wall is None:
            if normalized.get("orientation"):
                retry_normalized = dict(normalized)
                retry_normalized["orientation"] = None
                retry_normalized["wall_id"] = None
                wall = _pick_wall(retry_normalized)
                if wall is not None:
                    normalized = retry_normalized
            if wall is None:
                filtered += 1
                review_flags.append(f"Filtered opening {normalized['id']}: no compatible wall found.")
                continue

        offset = _opening_offset_for_wall(normalized, wall)
        if offset < -resolved.snap_tolerance or offset + normalized["span"] > _wall_length(wall) + resolved.snap_tolerance:
            if normalized.get("orientation"):
                retry_normalized = dict(normalized)
                retry_normalized["orientation"] = None
                retry_normalized["wall_id"] = None
                retry_wall = _pick_wall(retry_normalized)
                if retry_wall is not None:
                    retry_offset = _opening_offset_for_wall(retry_normalized, retry_wall)
                    if -resolved.snap_tolerance <= retry_offset and retry_offset + retry_normalized["span"] <= _wall_length(retry_wall) + resolved.snap_tolerance:
                        normalized = retry_normalized
                        wall = retry_wall
                        offset = retry_offset
            if offset < -resolved.snap_tolerance or offset + normalized["span"] > _wall_length(wall) + resolved.snap_tolerance:
                filtered += 1
                review_flags.append(f"Filtered opening {normalized['id']}: opening span does not fit wall {wall['id']}.")
                continue

        side = normalized.get("side") or wall.get("side") or _default_side_for_wall(wall)
        if normalized.get("side") is None:
            inferred_side_count += 1

        position = _opening_position_from_offset(wall, offset, normalized["span"])
        anchored_opening = {
            "id": normalized["id"],
            "kind": normalized["kind"],
            "wall_id": wall["id"],
            "position": position,
            "offset": round(offset, 4),
            "span": normalized["span"],
            "orientation": wall["orientation"],
            "side": side,
            "confidence": round(min(normalized["confidence"], wall["confidence"]), 4),
        }
        if normalized["kind"] == "door":
            anchored_opening["swing"] = normalized.get("swing") or _default_swing(side)
            anchored_opening["door_type"] = normalized.get("door_type", "normal")
        else:
            anchored_opening["swing"] = None
        anchored.append(anchored_opening)

    return anchored, {
        "filtered_opening_count": filtered,
        "inferred_opening_side_count": inferred_side_count,
    }


def _normalize_opening(opening: dict[str, Any], counter: int) -> dict[str, Any]:
    position = opening.get("position")
    normalized = {
        "id": opening.get("id") or f"opening-{counter:04d}",
        "kind": opening["kind"],
        "wall_id": opening.get("wall_id"),
        "position": _point(position) if position is not None else None,
        "offset": opening.get("offset"),
        "span": float(opening["span"]),
        "orientation": opening.get("orientation"),
        "side": opening.get("side"),
        "confidence": float(opening.get("confidence", 1.0)),
        "swing": opening.get("swing"),
        "door_type": opening.get("door_type", opening.get("type", "normal")),
    }
    return normalized


def _find_best_wall(
    opening: dict[str, Any],
    walls: list[dict[str, Any]],
    *,
    config: PostprocessConfig | None = None,
) -> dict[str, Any] | None:
    def _collect_candidates(enforce_orientation: bool) -> list[tuple[float, float, dict[str, Any]]]:
        candidates = []
        for wall in walls:
            if enforce_orientation and opening.get("orientation") and wall["orientation"] != opening["orientation"]:
                continue
            distance = _opening_distance_to_wall(opening, wall, config=config)
            if distance is None:
                continue
            candidates.append((distance, -_wall_length(wall), wall))
        return candidates

    candidates = _collect_candidates(enforce_orientation=True)
    if not candidates and opening.get("orientation"):
        candidates = _collect_candidates(enforce_orientation=False)
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def _opening_distance_to_wall(
    opening: dict[str, Any],
    wall: dict[str, Any],
    *,
    config: PostprocessConfig | None = None,
) -> float | None:
    resolved = config or PostprocessConfig()
    if opening["position"] is None:
        return None

    point = opening["position"]
    start, end = _wall_span(wall)
    half_span = opening["span"] / 2.0
    if wall["orientation"] == "horizontal":
        if point["x"] + half_span < start - resolved.snap_tolerance or point["x"] - half_span > end + resolved.snap_tolerance:
            return None
        return abs(point["y"] - wall["polyline"][0]["y"])

    if point["y"] + half_span < start - resolved.snap_tolerance or point["y"] - half_span > end + resolved.snap_tolerance:
        return None
    return abs(point["x"] - wall["polyline"][0]["x"])


def _opening_offset_for_wall(opening: dict[str, Any], wall: dict[str, Any]) -> float:
    if opening.get("offset") is not None:
        return float(opening["offset"])

    start, _ = _wall_axis_points(wall)
    if wall["orientation"] == "horizontal":
        return opening["position"]["x"] - start - (opening["span"] / 2.0)
    return opening["position"]["y"] - start - (opening["span"] / 2.0)


def _opening_position_from_offset(wall: dict[str, Any], offset: float, span: float) -> dict[str, float]:
    start, coord = _wall_axis_points(wall)
    center = start + offset + (span / 2.0)
    if wall["orientation"] == "horizontal":
        return {"x": center, "y": coord}
    return {"x": coord, "y": center}


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _wall_span(wall: dict[str, Any]) -> tuple[float, float]:
    start, end = wall["polyline"]
    if wall["orientation"] == "horizontal":
        return float(start["x"]), float(end["x"])
    if wall["orientation"] == "diagonal":
        # For diagonals, span is the full Euclidean length anchored at 0
        dx = float(end["x"]) - float(start["x"])
        dy = float(end["y"]) - float(start["y"])
        return 0.0, (dx * dx + dy * dy) ** 0.5
    return float(start["y"]), float(end["y"])


def _wall_axis_points(wall: dict[str, Any]) -> tuple[float, float]:
    start = wall["polyline"][0]
    if wall["orientation"] == "horizontal":
        return float(start["x"]), float(start["y"])
    return float(start["y"]), float(start["x"])


def _wall_length(wall: dict[str, Any]) -> float:
    start, end = _wall_span(wall)
    return end - start


def _cluster_values(values: list[float], *, tolerance: float) -> list[float]:
    if not values:
        return []
    sorted_values = sorted(values)
    clusters: list[list[float]] = [[sorted_values[0]]]
    for value in sorted_values[1:]:
        if abs(value - clusters[-1][-1]) <= tolerance:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [sum(cluster) / len(cluster) for cluster in clusters]


def _snap_value(value: float, clusters: list[float], *, tolerance: float) -> float:
    if not clusters:
        return value
    best = min(clusters, key=lambda cluster: abs(cluster - value))
    if abs(best - value) <= tolerance:
        return best
    return value


def _orientation(start: dict[str, float], end: dict[str, float]) -> str:
    if abs(start["y"] - end["y"]) <= EPSILON:
        return "horizontal"
    if abs(start["x"] - end["x"]) <= EPSILON:
        return "vertical"
    return "diagonal"


def _default_side_for_wall(wall: dict[str, Any]) -> str:
    if wall.get("side"):
        return wall["side"]
    if wall["orientation"] == "horizontal":
        return "top"
    return "right"


def _default_swing(side: str | None) -> str | None:
    return {
        "bottom": "up",
        "top": "down",
        "left": "right",
        "right": "left",
    }.get(side)


def _point(raw: dict[str, Any] | list[Any] | tuple[Any, Any]) -> dict[str, float]:
    if isinstance(raw, dict):
        return {"x": float(raw["x"]), "y": float(raw["y"])}
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        return {"x": float(raw[0]), "y": float(raw[1])}
    raise ValueError("point must be a dict with x/y or a 2-item sequence")
