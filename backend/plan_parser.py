"""
plan_parser.py
Canonical structure parser for the v2 pipeline.

Phase 1 scope:
- normalize or adapt input into a walls/openings contract
- support legacy room-based plans as a compatibility bridge
- produce review flags and lightweight quality metrics
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from .components.walls import THICKNESS
from .quality_gate import apply_quality_gate
from .structure_postprocess import build_junction_graph, postprocess_structure

SIDES = ("bottom", "top", "left", "right")
EPSILON = 1e-6


def parse_structure_payload(
    *,
    plan: dict[str, Any] | None = None,
    structure: dict[str, Any] | None = None,
    scale_hint: float | None = None,
) -> dict[str, Any]:
    if structure:
        return _normalize_structure(structure, scale_hint=scale_hint)
    if plan:
        return _parse_legacy_plan(plan, scale_hint=scale_hint)
    raise ValueError("Either plan or structure must be provided.")


def _parse_legacy_plan(plan: dict[str, Any], scale_hint: float | None) -> dict[str, Any]:
    rooms = plan.get("rooms") or []
    review_flags: list[str] = []

    if not rooms:
        raise ValueError("Legacy plan is missing rooms[].")

    wall_candidates = []
    for room in rooms:
        for side in SIDES:
            wall_candidates.append(_build_wall_candidate(room, side, rooms))

    walls = _merge_wall_candidates(wall_candidates)
    wall_lookup = _build_wall_lookup(walls)

    openings = []
    opening_counter = 0
    unmatched_openings = 0
    unsupported_openings = 0

    for room in rooms:
        for raw_opening in room.get("doors", []):
            opening_counter += 1
            opening = _build_opening(
                room,
                raw_opening,
                kind="door",
                counter=opening_counter,
                rooms=rooms,
                wall_lookup=wall_lookup,
                review_flags=review_flags,
            )
            if opening is None:
                unmatched_openings += 1
            else:
                if opening.get("door_type") not in (None, "normal"):
                    unsupported_openings += 1
                openings.append(opening)

        for raw_opening in room.get("windows", []):
            opening_counter += 1
            opening = _build_opening(
                room,
                raw_opening,
                kind="window",
                counter=opening_counter,
                rooms=rooms,
                wall_lookup=wall_lookup,
                review_flags=review_flags,
            )
            if opening is None:
                unmatched_openings += 1
            else:
                openings.append(opening)

    if unsupported_openings:
        review_flags.append(
            f"{unsupported_openings} non-standard door openings were kept as wall gaps only."
        )

    junctions = build_junction_graph(walls)

    structure_meta = {
        "image_size": None,
        "scale_status": "calibrated",
        "unit": "inch",
    }
    if scale_hint is not None:
        structure_meta["scale_hint"] = float(scale_hint)

    quality_metrics = {
        "parser_version": "v2-phase-2",
        "source_contract": "legacy_rooms",
        "room_count": len(rooms),
        "wall_count": len(walls),
        "opening_count": len(openings),
        "door_count": sum(1 for opening in openings if opening["kind"] == "door"),
        "window_count": sum(1 for opening in openings if opening["kind"] == "window"),
        "exterior_wall_count": sum(1 for wall in walls if wall["is_exterior"]),
        "interior_wall_count": sum(1 for wall in walls if not wall["is_exterior"]),
        "unmatched_openings": unmatched_openings,
        "nonstandard_openings": unsupported_openings,
    }

    structure_result = {
        "model": plan.get("model", "Untitled Structure"),
        "source": "legacy_rooms_adapter",
        "walls": walls,
        "openings": openings,
        "junctions": junctions,
        "structure_meta": structure_meta,
    }
    return _finalize_parse_result(structure_result, quality_metrics, review_flags)


def _normalize_structure(
    structure: dict[str, Any],
    *,
    scale_hint: float | None,
) -> dict[str, Any]:
    review_flags: list[str] = []
    wall_counter = 0
    walls = []

    for raw_wall in structure.get("walls") or []:
        wall_counter += 1
        try:
            walls.append(_normalize_wall(raw_wall, wall_counter))
        except ValueError as exc:
            review_flags.append(f"Skipped wall #{wall_counter}: {exc}")

    opening_counter = 0
    openings = []

    for raw_opening in structure.get("openings") or []:
        opening_counter += 1
        try:
            openings.append(_normalize_raw_opening(raw_opening, opening_counter))
        except ValueError as exc:
            review_flags.append(f"Skipped opening #{opening_counter}: {exc}")

    raw_meta = structure.get("structure_meta") or {}
    if scale_hint is None:
        scale_hint = raw_meta.get("scale_hint")

    unit = raw_meta.get("unit", "pixel")
    scale_status = raw_meta.get("scale_status", "unverified")
    if scale_hint is not None:
        unit = "inch"
        scale_status = "calibrated"

    structure_meta = {
        "image_size": raw_meta.get("image_size"),
        "scale_status": scale_status,
        "unit": unit,
    }
    if scale_hint is not None:
        structure_meta["scale_hint"] = float(scale_hint)

    if scale_hint is not None:
        walls, openings = _apply_scale(walls, openings, float(scale_hint))

    processed = postprocess_structure(
        walls=walls,
        openings=openings,
        structure_meta=structure_meta,
    )
    review_flags.extend(processed["review_flags"])

    quality_metrics = {
        "parser_version": "v2-phase-2",
        "source_contract": "structure",
        "wall_count": len(processed["walls"]),
        "opening_count": len(processed["openings"]),
        "door_count": sum(1 for opening in processed["openings"] if opening["kind"] == "door"),
        "window_count": sum(1 for opening in processed["openings"] if opening["kind"] == "window"),
        "exterior_wall_count": sum(1 for wall in processed["walls"] if wall["is_exterior"]),
        "interior_wall_count": sum(1 for wall in processed["walls"] if not wall["is_exterior"]),
        "review_flag_count": len(review_flags),
        **processed["metrics"],
    }

    structure_result = {
        "model": structure.get("model", "Untitled Structure"),
        "source": structure.get("source", "provided_structure"),
        "walls": processed["walls"],
        "openings": processed["openings"],
        "junctions": processed["junctions"],
        "structure_meta": processed["structure_meta"],
        "inference_debug": structure.get("inference_debug", {}),
    }
    return _finalize_parse_result(structure_result, quality_metrics, review_flags)


def _finalize_parse_result(
    structure: dict[str, Any],
    quality_metrics: dict[str, Any],
    review_flags: list[str],
) -> dict[str, Any]:
    metrics = dict(quality_metrics)
    metrics.setdefault(
        "inference_backend",
        structure.get("inference_debug", {}).get("backend") or structure.get("source", "unknown"),
    )
    metrics, flags = apply_quality_gate(structure, metrics, review_flags)
    structure.pop("inference_debug", None)
    return {
        "structure": structure,
        "quality_metrics": metrics,
        "needs_review": bool(flags),
        "review_flags": flags,
    }


def _build_wall_candidate(room: dict[str, Any], side: str, rooms: list[dict[str, Any]]) -> dict[str, Any]:
    rx = float(room["x"])
    ry = float(room["y"])
    rw = float(room["w"])
    rh = float(room["h"])
    is_interior = _is_interior_wall(room, side, rooms)

    if side == "bottom":
        return {
            "orientation": "horizontal",
            "coord": ry,
            "start": rx,
            "end": rx + rw,
            "is_exterior": not is_interior,
        }

    if side == "top":
        return {
            "orientation": "horizontal",
            "coord": ry + rh,
            "start": rx,
            "end": rx + rw,
            "is_exterior": not is_interior,
        }

    if side == "left":
        return {
            "orientation": "vertical",
            "coord": rx,
            "start": ry + THICKNESS,
            "end": ry + rh - THICKNESS,
            "is_exterior": not is_interior,
        }

    coord = rx + rw - THICKNESS
    if is_interior:
        coord += THICKNESS

    return {
        "orientation": "vertical",
        "coord": coord,
        "start": ry + THICKNESS,
        "end": ry + rh - THICKNESS,
        "is_exterior": not is_interior,
    }


def _merge_wall_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, float, bool], list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        key = (
            candidate["orientation"],
            round(candidate["coord"], 6),
            bool(candidate["is_exterior"]),
        )
        grouped[key].append(candidate)

    walls = []
    wall_index = 0

    for (orientation, coord, is_exterior), items in sorted(grouped.items()):
        spans = sorted((item["start"], item["end"]) for item in items)
        for start, end in _merge_spans(spans):
            wall_index += 1
            if orientation == "horizontal":
                polyline = [_point(start, coord), _point(end, coord)]
            else:
                polyline = [_point(coord, start), _point(coord, end)]

            walls.append(
                {
                    "id": f"wall-{wall_index:04d}",
                    "orientation": orientation,
                    "polyline": polyline,
                    "thickness": float(THICKNESS),
                    "is_exterior": is_exterior,
                    "confidence": 1.0,
                }
            )

    return walls


def _merge_spans(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not spans:
        return []

    merged = []
    current_start, current_end = spans[0]
    for start, end in spans[1:]:
        if start <= current_end + EPSILON:
            current_end = max(current_end, end)
        else:
            merged.append((current_start, current_end))
            current_start, current_end = start, end
    merged.append((current_start, current_end))
    return merged


def _build_wall_lookup(walls: list[dict[str, Any]]) -> dict[tuple[str, float], list[dict[str, Any]]]:
    lookup: dict[tuple[str, float], list[dict[str, Any]]] = defaultdict(list)
    for wall in walls:
        start, end, coord = _wall_span(wall)
        key = (wall["orientation"], round(coord, 6))
        lookup[key].append(
            {
                "wall": wall,
                "start": start,
                "end": end,
            }
        )
    return lookup


def _build_opening(
    room: dict[str, Any],
    raw_opening: dict[str, Any],
    *,
    kind: str,
    counter: int,
    rooms: list[dict[str, Any]],
    wall_lookup: dict[tuple[str, float], list[dict[str, Any]]],
    review_flags: list[str],
) -> dict[str, Any] | None:
    side = raw_opening.get("wall")
    if side not in SIDES:
        review_flags.append(
            f"Skipped {kind} in room {room.get('name', 'UNKNOWN')}: invalid wall side {side!r}."
        )
        return None

    width = float(raw_opening.get("width", 0))
    offset = float(raw_opening.get("offset", 0))
    if width <= 0:
        review_flags.append(
            f"Skipped {kind} in room {room.get('name', 'UNKNOWN')}: width must be positive."
        )
        return None

    geometry = _opening_geometry(room, side, offset, width, rooms)
    match = _find_matching_wall(
        wall_lookup,
        orientation=geometry["orientation"],
        coord=geometry["coord"],
        start=geometry["start"],
        end=geometry["end"],
        is_exterior=geometry["is_exterior"],
    )
    if match is None:
        review_flags.append(
            f"Could not anchor {kind} on {side} wall for room {room.get('name', 'UNKNOWN')}."
        )
        return None

    wall = match["wall"]
    wall_offset = geometry["start"] - match["start"]
    opening_id = f"opening-{counter:04d}"
    position = _opening_position(geometry["orientation"], geometry["coord"], geometry["start"], geometry["end"])
    opening = {
        "id": opening_id,
        "kind": kind,
        "wall_id": wall["id"],
        "position": position,
        "offset": round(wall_offset, 4),
        "span": width,
        "orientation": geometry["orientation"],
        "side": side,
        "confidence": 1.0,
    }

    if kind == "door":
        opening["door_type"] = raw_opening.get("type", "normal")
        opening["swing"] = _door_swing_for_side(side)

    return opening


def _opening_geometry(
    room: dict[str, Any],
    side: str,
    offset: float,
    width: float,
    rooms: list[dict[str, Any]],
) -> dict[str, Any]:
    rx = float(room["x"])
    ry = float(room["y"])
    rw = float(room["w"])
    rh = float(room["h"])
    is_interior = _is_interior_wall(room, side, rooms)

    if side == "bottom":
        start = rx + offset
        end = start + width
        return {
            "orientation": "horizontal",
            "coord": ry,
            "start": start,
            "end": end,
            "is_exterior": not is_interior,
        }

    if side == "top":
        start = rx + offset
        end = start + width
        return {
            "orientation": "horizontal",
            "coord": ry + rh,
            "start": start,
            "end": end,
            "is_exterior": not is_interior,
        }

    if side == "left":
        start = ry + offset
        end = start + width
        return {
            "orientation": "vertical",
            "coord": rx,
            "start": start,
            "end": end,
            "is_exterior": not is_interior,
        }

    coord = rx + rw - THICKNESS
    if is_interior:
        coord += THICKNESS
    start = ry + offset
    end = start + width
    return {
        "orientation": "vertical",
        "coord": coord,
        "start": start,
        "end": end,
        "is_exterior": not is_interior,
    }


def _find_matching_wall(
    wall_lookup: dict[tuple[str, float], list[dict[str, Any]]],
    *,
    orientation: str,
    coord: float,
    start: float,
    end: float,
    is_exterior: bool,
) -> dict[str, Any] | None:
    candidates = wall_lookup.get((orientation, round(coord, 6)), [])
    exact_matches = [
        candidate
        for candidate in candidates
        if candidate["wall"]["is_exterior"] == is_exterior
        and candidate["start"] <= start + EPSILON
        and candidate["end"] >= end - EPSILON
    ]
    if exact_matches:
        return min(exact_matches, key=lambda candidate: candidate["end"] - candidate["start"])

    fallback_matches = [
        candidate
        for candidate in candidates
        if candidate["start"] <= start + EPSILON and candidate["end"] >= end - EPSILON
    ]
    if fallback_matches:
        return min(fallback_matches, key=lambda candidate: candidate["end"] - candidate["start"])
    return None


def _normalize_wall(raw_wall: dict[str, Any], counter: int) -> dict[str, Any]:
    polyline = [_normalize_point(point) for point in raw_wall.get("polyline") or []]
    if len(polyline) != 2:
        raise ValueError("phase 1 only supports axis-aligned walls with exactly 2 points")

    start, end = _sorted_axis_points(polyline[0], polyline[1])
    orientation = raw_wall.get("orientation") or _orientation_from_points(start, end)
    if orientation not in ("horizontal", "vertical"):
        raise ValueError("wall must be axis-aligned")

    return {
        "id": raw_wall.get("id") or f"wall-{counter:04d}",
        "orientation": orientation,
        "polyline": [start, end],
        "thickness": float(raw_wall.get("thickness", THICKNESS)),
        "is_exterior": bool(raw_wall.get("is_exterior", False)),
        "confidence": float(raw_wall.get("confidence", 1.0)),
    }


def _normalize_raw_opening(raw_opening: dict[str, Any], counter: int) -> dict[str, Any]:
    kind = raw_opening.get("kind")
    if kind not in ("door", "window"):
        raise ValueError("kind must be 'door' or 'window'")

    span = float(raw_opening.get("span", 0))
    if span <= 0:
        raise ValueError("span must be positive")
    if raw_opening.get("position") is None and raw_opening.get("offset") is None:
        raise ValueError("opening needs either offset or position")

    opening = {
        "id": raw_opening.get("id") or f"opening-{counter:04d}",
        "kind": kind,
        "wall_id": raw_opening.get("wall_id"),
        "position": _normalize_point(raw_opening["position"]) if raw_opening.get("position") else None,
        "offset": float(raw_opening["offset"]) if raw_opening.get("offset") is not None else None,
        "span": span,
        "orientation": raw_opening.get("orientation"),
        "side": raw_opening.get("side"),
        "confidence": float(raw_opening.get("confidence", 1.0)),
    }

    if kind == "door":
        opening["door_type"] = raw_opening.get("door_type", raw_opening.get("type", "normal"))
        opening["swing"] = raw_opening.get("swing") or _door_swing_for_side(opening.get("side"))
    else:
        opening["swing"] = None

    return opening

def _wall_span(wall: dict[str, Any]) -> tuple[float, float, float]:
    start = wall["polyline"][0]
    end = wall["polyline"][1]
    if wall["orientation"] == "horizontal":
        return float(start["x"]), float(end["x"]), float(start["y"])
    return float(start["y"]), float(end["y"]), float(start["x"])


def _orientation_from_points(start: dict[str, float], end: dict[str, float]) -> str:
    if abs(start["y"] - end["y"]) <= EPSILON:
        return "horizontal"
    if abs(start["x"] - end["x"]) <= EPSILON:
        return "vertical"
    raise ValueError("wall points must be axis-aligned")


def _sorted_axis_points(
    start: dict[str, float],
    end: dict[str, float],
) -> tuple[dict[str, float], dict[str, float]]:
    if abs(start["y"] - end["y"]) <= EPSILON:
        return (start, end) if start["x"] <= end["x"] else (end, start)
    if abs(start["x"] - end["x"]) <= EPSILON:
        return (start, end) if start["y"] <= end["y"] else (end, start)
    raise ValueError("wall points must be axis-aligned")


def _opening_position(
    orientation: str,
    coord: float,
    start: float,
    end: float,
) -> dict[str, float]:
    midpoint = start + ((end - start) / 2.0)
    if orientation == "horizontal":
        return _point(midpoint, coord)
    return _point(coord, midpoint)


def _normalize_point(raw_point: dict[str, Any] | list[Any] | tuple[Any, Any]) -> dict[str, float]:
    if isinstance(raw_point, dict):
        return _point(raw_point["x"], raw_point["y"])
    if isinstance(raw_point, (list, tuple)) and len(raw_point) >= 2:
        return _point(raw_point[0], raw_point[1])
    raise ValueError("point must be a dict with x/y or a 2-item sequence")


def _point(x: Any, y: Any) -> dict[str, float]:
    return {"x": float(x), "y": float(y)}


def _door_swing_for_side(side: str | None) -> str | None:
    return {
        "bottom": "up",
        "top": "down",
        "left": "right",
        "right": "left",
    }.get(side)


def _apply_scale(
    walls: list[dict[str, Any]],
    openings: list[dict[str, Any]],
    scale: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Multiply all pixel coordinates by scale to convert to inches."""
    scaled_walls = []
    for wall in walls:
        scaled_walls.append({
            **wall,
            "polyline": [{"x": p["x"] * scale, "y": p["y"] * scale} for p in wall["polyline"]],
            "thickness": wall["thickness"] * scale,
        })

    scaled_openings = []
    for opening in openings:
        scaled = dict(opening)
        if scaled.get("position") is not None:
            scaled["position"] = {
                "x": scaled["position"]["x"] * scale,
                "y": scaled["position"]["y"] * scale,
            }
        if scaled.get("offset") is not None:
            scaled["offset"] = scaled["offset"] * scale
        if scaled.get("span") is not None:
            scaled["span"] = scaled["span"] * scale
        scaled_openings.append(scaled)

    return scaled_walls, scaled_openings


def _is_interior_wall(room: dict[str, Any], side: str, rooms: list[dict[str, Any]]) -> bool:
    for other in rooms:
        if other is room:
            continue
        if _rooms_share_wall(room, other, side):
            return True
    return False


def _rooms_share_wall(room_a: dict[str, Any], room_b: dict[str, Any], side: str) -> bool:
    x1 = float(room_a["x"])
    y1 = float(room_a["y"])
    w1 = float(room_a["w"])
    h1 = float(room_a["h"])
    x2 = float(room_b["x"])
    y2 = float(room_b["y"])
    w2 = float(room_b["w"])
    h2 = float(room_b["h"])

    if side == "left":
        return abs(x1 - (x2 + w2)) < 5 and y1 < y2 + h2 and y1 + h1 > y2
    if side == "right":
        return abs((x1 + w1) - x2) < 5 and y1 < y2 + h2 and y1 + h1 > y2
    if side == "bottom":
        return abs(y1 - (y2 + h2)) < 5 and x1 < x2 + w2 and x1 + w1 > x2
    if side == "top":
        return abs((y1 + h1) - y2) < 5 and x1 < x2 + w2 and x1 + w1 > x2
    return False
