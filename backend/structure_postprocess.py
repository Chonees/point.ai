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

from collections import defaultdict
from typing import Any

EPSILON = 1e-6
SNAP_TOLERANCE = 4.0
JUNCTION_TOLERANCE = 6.0
MERGE_GAP = 48.0
MIN_WALL_LENGTH = 12.0
EXTERIOR_COVERAGE_THRESHOLD = 0.70

# Diagonal wall projection: walls within this angle of H/V are snapped to axis
DIAGONAL_ANGLE_THRESHOLD_DEG = 15.0

# Furniture filter: closed rectangles smaller than this area are furniture
FURNITURE_MAX_AREA = 200.0 * 200.0   # 200x200 pixels max for furniture bboxes
FURNITURE_MIN_AREA = 4.0 * 4.0       # ignore trivially small detections

# Text filter: walls shorter than this with very low thickness are likely text
TEXT_MAX_LENGTH = 60.0
TEXT_MAX_THICKNESS = 6.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def postprocess_structure(
    *,
    walls: list[dict[str, Any]],
    openings: list[dict[str, Any]],
    structure_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    global SNAP_TOLERANCE, JUNCTION_TOLERANCE, MERGE_GAP, MIN_WALL_LENGTH
    global TEXT_MAX_LENGTH, TEXT_MAX_THICKNESS, FURNITURE_MAX_AREA

    review_flags: list[str] = []

    # Adapt thresholds for pixel-coordinate inputs (model output)
    meta = structure_meta or {}
    if meta.get("unit") == "pixel":
        # Pixel images are ~800-2000px; inch plans are ~200-800 inches.
        # Scale thresholds proportionally to avoid over-merging.
        img_size = meta.get("image_size", {})
        img_w = img_size.get("width", 1000) if isinstance(img_size, dict) else 1000
        scale = max(img_w / 500.0, 1.0)  # ratio vs typical inch-based plan
        SNAP_TOLERANCE = 3.0 * scale
        JUNCTION_TOLERANCE = 4.0 * scale
        MERGE_GAP = 6.0 * scale  # much less aggressive merge for pixels
        MIN_WALL_LENGTH = 8.0 * scale
        TEXT_MAX_LENGTH = 30.0 * scale
        TEXT_MAX_THICKNESS = 4.0 * scale
        FURNITURE_MAX_AREA = (100.0 * scale) ** 2
    else:
        # Reset to defaults for inch-based inputs
        SNAP_TOLERANCE = 4.0
        JUNCTION_TOLERANCE = 6.0
        MERGE_GAP = 48.0
        MIN_WALL_LENGTH = 12.0
        TEXT_MAX_LENGTH = 60.0
        TEXT_MAX_THICKNESS = 6.0
        FURNITURE_MAX_AREA = 200.0 * 200.0

    # Project near-axis diagonal walls to H/V before anything else
    projected, diag_count = _project_diagonal_walls(walls)
    if diag_count:
        review_flags.append(f"Projected {diag_count} near-axis diagonal wall(s) to H/V.")

    # Filter text artifacts (very short, very thin segments)
    filtered_text, text_count = _filter_text_artifacts(projected)
    if text_count:
        review_flags.append(f"Removed {text_count} text-like wall artifact(s).")

    snapped_walls = [_normalize_wall_geometry(wall) for wall in filtered_text]
    snapped_walls = _snap_walls(snapped_walls)
    snapped_walls = _snap_to_intersections(snapped_walls)
    merged_walls = _merge_walls(snapped_walls)
    junctions = build_junction_graph(merged_walls)
    classified_walls = _classify_walls_with_junctions(merged_walls, junctions)

    # Filter furniture-like openings (isolated small closed shapes not connected to walls)
    filtered_openings, furniture_count = _filter_furniture_openings(openings, classified_walls)
    if furniture_count:
        review_flags.append(f"Removed {furniture_count} furniture-like opening(s).")

    wall_map = {wall["id"]: wall for wall in classified_walls}
    anchored_openings, opening_metrics = _anchor_openings(filtered_openings, classified_walls, wall_map, review_flags)

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
    }


# ---------------------------------------------------------------------------
# Junction graph (Phase 3)
# ---------------------------------------------------------------------------

def build_junction_graph(walls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Detect L, T, and X junctions between walls.

    A junction is a point where two or more walls meet or cross.
    - L: two walls meet at an endpoint-to-endpoint corner
    - T: one wall's endpoint touches another wall's body
    - X: two walls cross each other through their bodies
    """
    h_walls = [w for w in walls if w["orientation"] == "horizontal"]
    v_walls = [w for w in walls if w["orientation"] == "vertical"]

    junctions: list[dict[str, Any]] = []
    seen_points: dict[tuple[float, float], dict[str, Any]] = {}

    for hw in h_walls:
        hy = hw["polyline"][0]["y"]
        hx1 = hw["polyline"][0]["x"]
        hx2 = hw["polyline"][1]["x"]

        for vw in v_walls:
            vx = vw["polyline"][0]["x"]
            vy1 = vw["polyline"][0]["y"]
            vy2 = vw["polyline"][1]["y"]

            # Check if they intersect or are close enough
            if vx < hx1 - JUNCTION_TOLERANCE or vx > hx2 + JUNCTION_TOLERANCE:
                continue
            if hy < vy1 - JUNCTION_TOLERANCE or hy > vy2 + JUNCTION_TOLERANCE:
                continue

            point = (round(vx, 2), round(hy, 2))
            junction_type = _classify_junction(hx1, hx2, hy, vx, vy1, vy2)

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
) -> str:
    """Determine if junction is L, T, or X based on endpoint proximity."""
    h_at_left = abs(vx - hx1) <= JUNCTION_TOLERANCE
    h_at_right = abs(vx - hx2) <= JUNCTION_TOLERANCE
    h_endpoint = h_at_left or h_at_right

    v_at_top = abs(hy - vy1) <= JUNCTION_TOLERANCE
    v_at_bottom = abs(hy - vy2) <= JUNCTION_TOLERANCE
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


# ---------------------------------------------------------------------------
# Snap to intersections (Phase 3)
# ---------------------------------------------------------------------------

def _snap_to_intersections(walls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Snap wall endpoints to nearby wall intersections.

    When a horizontal wall's endpoint is close to a vertical wall's axis
    (or vice versa), extend/trim the endpoint to meet exactly.
    """
    h_walls = [w for w in walls if w["orientation"] == "horizontal"]
    v_walls = [w for w in walls if w["orientation"] == "vertical"]

    v_x_coords = [w["polyline"][0]["x"] for w in v_walls]
    h_y_coords = [w["polyline"][0]["y"] for w in h_walls]

    result = []
    for wall in walls:
        start, end = wall["polyline"]
        if wall["orientation"] == "horizontal":
            new_x1 = _snap_endpoint_to_axes(start["x"], v_x_coords, JUNCTION_TOLERANCE)
            new_x2 = _snap_endpoint_to_axes(end["x"], v_x_coords, JUNCTION_TOLERANCE)
            result.append({
                **wall,
                "polyline": [
                    {"x": new_x1, "y": start["y"]},
                    {"x": new_x2, "y": end["y"]},
                ],
            })
        else:
            new_y1 = _snap_endpoint_to_axes(start["y"], h_y_coords, JUNCTION_TOLERANCE)
            new_y2 = _snap_endpoint_to_axes(end["y"], h_y_coords, JUNCTION_TOLERANCE)
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
) -> list[dict[str, Any]]:
    """
    Classify walls as exterior or interior using bounding box coverage
    and junction connectivity, not just proximity to extremes.

    A wall on the bounding perimeter that covers a significant portion of
    the corresponding side is exterior. Interior walls that only partially
    span are not promoted even if they touch the boundary.
    """
    if not walls:
        return []

    all_points = [p for w in walls for p in w["polyline"]]
    min_x = min(p["x"] for p in all_points)
    max_x = max(p["x"] for p in all_points)
    min_y = min(p["y"] for p in all_points)
    max_y = max(p["y"] for p in all_points)

    bbox_width = max_x - min_x
    bbox_height = max_y - min_y

    # Build junction connectivity per wall
    wall_junction_count: dict[str, int] = defaultdict(int)
    for j in junctions:
        for wid in j["wall_ids"]:
            wall_junction_count[wid] += 1

    classified = []
    for wall in walls:
        start, end = wall["polyline"]
        side = None
        is_exterior = False
        length = _wall_length(wall)

        if wall["orientation"] == "horizontal":
            ref_size = bbox_width if bbox_width > EPSILON else 1.0
            coverage = length / ref_size

            if abs(start["y"] - min_y) <= SNAP_TOLERANCE:
                if coverage >= EXTERIOR_COVERAGE_THRESHOLD or length >= ref_size - SNAP_TOLERANCE:
                    side = "bottom"
                    is_exterior = True
            elif abs(start["y"] - max_y) <= SNAP_TOLERANCE:
                if coverage >= EXTERIOR_COVERAGE_THRESHOLD or length >= ref_size - SNAP_TOLERANCE:
                    side = "top"
                    is_exterior = True
        else:
            ref_size = bbox_height if bbox_height > EPSILON else 1.0
            coverage = length / ref_size

            if abs(start["x"] - min_x) <= SNAP_TOLERANCE:
                if coverage >= EXTERIOR_COVERAGE_THRESHOLD or length >= ref_size - SNAP_TOLERANCE:
                    side = "left"
                    is_exterior = True
            elif abs(start["x"] - max_x) <= SNAP_TOLERANCE:
                if coverage >= EXTERIOR_COVERAGE_THRESHOLD or length >= ref_size - SNAP_TOLERANCE:
                    side = "right"
                    is_exterior = True

        confidence = wall["confidence"]
        if is_exterior:
            confidence = min(0.995, confidence + 0.05)

        # Boost confidence for well-connected walls
        jcount = wall_junction_count.get(wall["id"], 0)
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
) -> tuple[list[dict[str, Any]], int]:
    """Remove wall segments that are likely text or dimension labels.

    Heuristic: a segment is text-like when it is both very short AND very thin.
    Real walls in floor plans have either significant length or significant thickness.
    """
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
        if length < TEXT_MAX_LENGTH and thickness < TEXT_MAX_THICKNESS:
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
) -> tuple[list[dict[str, Any]], int]:
    """Remove opening detections that are not near any wall.

    An opening that cannot be placed within SNAP_TOLERANCE of any wall axis
    is likely a furniture contour (closed small rectangle) and should be dropped.
    """
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
                if abs(py - axis["coord"]) <= SNAP_TOLERANCE * 3:
                    if px - half <= axis["span_end"] + SNAP_TOLERANCE and px + half >= axis["span_start"] - SNAP_TOLERANCE:
                        near_wall = True
                        break
            else:
                if abs(px - axis["coord"]) <= SNAP_TOLERANCE * 3:
                    if py - half <= axis["span_end"] + SNAP_TOLERANCE and py + half >= axis["span_start"] - SNAP_TOLERANCE:
                        near_wall = True
                        break

        if near_wall:
            kept.append(opening)
        else:
            removed += 1

    return kept, removed


# ---------------------------------------------------------------------------
# Normalize + Snap + Merge (from Phase 2, preserved)
# ---------------------------------------------------------------------------

def _normalize_wall_geometry(wall: dict[str, Any]) -> dict[str, Any]:
    points = wall.get("polyline") or []
    if len(points) != 2:
        raise ValueError("postprocess only supports 2-point axis-aligned walls")

    start = _point(points[0])
    end = _point(points[1])
    orientation = wall.get("orientation") or _orientation(start, end)
    if orientation == "horizontal" and start["x"] > end["x"]:
        start, end = end, start
    if orientation == "vertical" and start["y"] > end["y"]:
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


def _snap_walls(walls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not walls:
        return []

    h_coords = _cluster_values([wall["polyline"][0]["y"] for wall in walls if wall["orientation"] == "horizontal"])
    v_coords = _cluster_values([wall["polyline"][0]["x"] for wall in walls if wall["orientation"] == "vertical"])
    x_values = _cluster_values(
        [point["x"] for wall in walls for point in wall["polyline"] if wall["orientation"] == "horizontal"]
    )
    y_values = _cluster_values(
        [point["y"] for wall in walls for point in wall["polyline"] if wall["orientation"] == "vertical"]
    )

    snapped = []
    for wall in walls:
        start, end = wall["polyline"]
        if wall["orientation"] == "horizontal":
            y = _snap_value(start["y"], h_coords)
            snapped.append(
                {
                    **wall,
                    "polyline": [
                        {"x": _snap_value(start["x"], x_values), "y": y},
                        {"x": _snap_value(end["x"], x_values), "y": y},
                    ],
                }
            )
        else:
            x = _snap_value(start["x"], v_coords)
            snapped.append(
                {
                    **wall,
                    "polyline": [
                        {"x": x, "y": _snap_value(start["y"], y_values)},
                        {"x": x, "y": _snap_value(end["y"], y_values)},
                    ],
                }
            )
    return snapped


def _merge_walls(walls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, float], list[dict[str, Any]]] = defaultdict(list)
    for wall in walls:
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
            if start <= current_end + MERGE_GAP:
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
                if _wall_length(merged_wall) >= MIN_WALL_LENGTH:
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
        if _wall_length(merged_wall) >= MIN_WALL_LENGTH:
            merged.append(merged_wall)
            counter += 1

    return merged


def _build_merged_wall(
    orientation: str,
    coord: float,
    start: float,
    end: float,
    source_walls: list[dict[str, Any]],
    counter: int,
) -> dict[str, Any]:
    avg_thickness = sum(wall["thickness"] for wall in source_walls) / len(source_walls)
    avg_confidence = sum(wall["confidence"] for wall in source_walls) / len(source_walls)
    if orientation == "horizontal":
        polyline = [{"x": start, "y": coord}, {"x": end, "y": coord}]
    else:
        polyline = [{"x": coord, "y": start}, {"x": coord, "y": end}]
    return {
        "id": f"wall-{counter:04d}",
        "orientation": orientation,
        "polyline": polyline,
        "thickness": avg_thickness,
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
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    anchored = []
    filtered = 0
    inferred_side_count = 0
    for counter, opening in enumerate(openings, start=1):
        normalized = _normalize_opening(opening, counter)
        wall = None

        if normalized.get("wall_id") and normalized["wall_id"] in wall_map:
            wall = wall_map[normalized["wall_id"]]
        else:
            wall = _find_best_wall(normalized, walls)

        if wall is None:
            filtered += 1
            review_flags.append(f"Filtered opening {normalized['id']}: no compatible wall found.")
            continue

        offset = _opening_offset_for_wall(normalized, wall)
        if offset < -SNAP_TOLERANCE or offset + normalized["span"] > _wall_length(wall) + SNAP_TOLERANCE:
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


def _find_best_wall(opening: dict[str, Any], walls: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = []
    for wall in walls:
        if opening.get("orientation") and wall["orientation"] != opening["orientation"]:
            continue
        distance = _opening_distance_to_wall(opening, wall)
        if distance is None:
            continue
        candidates.append((distance, -_wall_length(wall), wall))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def _opening_distance_to_wall(opening: dict[str, Any], wall: dict[str, Any]) -> float | None:
    if opening["position"] is None:
        return None

    point = opening["position"]
    start, end = _wall_span(wall)
    half_span = opening["span"] / 2.0
    if wall["orientation"] == "horizontal":
        if point["x"] + half_span < start - SNAP_TOLERANCE or point["x"] - half_span > end + SNAP_TOLERANCE:
            return None
        return abs(point["y"] - wall["polyline"][0]["y"])

    if point["y"] + half_span < start - SNAP_TOLERANCE or point["y"] - half_span > end + SNAP_TOLERANCE:
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
    return float(start["y"]), float(end["y"])


def _wall_axis_points(wall: dict[str, Any]) -> tuple[float, float]:
    start = wall["polyline"][0]
    if wall["orientation"] == "horizontal":
        return float(start["x"]), float(start["y"])
    return float(start["y"]), float(start["x"])


def _wall_length(wall: dict[str, Any]) -> float:
    start, end = _wall_span(wall)
    return end - start


def _cluster_values(values: list[float]) -> list[float]:
    if not values:
        return []
    sorted_values = sorted(values)
    clusters: list[list[float]] = [[sorted_values[0]]]
    for value in sorted_values[1:]:
        if abs(value - clusters[-1][-1]) <= SNAP_TOLERANCE:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [sum(cluster) / len(cluster) for cluster in clusters]


def _snap_value(value: float, clusters: list[float]) -> float:
    if not clusters:
        return value
    best = min(clusters, key=lambda cluster: abs(cluster - value))
    if abs(best - value) <= SNAP_TOLERANCE:
        return best
    return value


def _orientation(start: dict[str, float], end: dict[str, float]) -> str:
    if abs(start["y"] - end["y"]) <= EPSILON:
        return "horizontal"
    if abs(start["x"] - end["x"]) <= EPSILON:
        return "vertical"
    raise ValueError("wall is not axis-aligned")


def _default_side_for_wall(wall: dict[str, Any]) -> str:
    if wall["side"]:
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
