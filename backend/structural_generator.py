"""
structural_generator.py
DXF renderer for the v2 structure contract.

Phase 2: axis-aligned walls with junction-based corner extensions
and corrected door/window anchoring.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from .components.doors import draw_door, draw_garage_door, draw_sliding_door
from .components.layers import setup_doc
from .components.walls import THICKNESS, draw_wall_h, draw_wall_v, split_segments
from .components.windows import draw_window_h, draw_window_v

EPSILON = 1e-6
JUNCTION_TOLERANCE = 6.0


def generate(structure: dict[str, Any], out_path: str) -> None:
    render_plan = build_render_plan(structure)
    doc, msp = setup_doc()
    wall_map = {wall["id"]: wall for wall in render_plan["wall_geometries"]}

    for wall in render_plan["walls"]:
        gaps = [(gap["start"], gap["end"]) for gap in wall.get("gaps", [])]
        if wall["orientation"] == "horizontal":
            draw_wall_h(
                msp,
                wall["start"],
                wall["end"],
                wall["coord"],
                gaps=gaps,
                thickness=wall["draw_thickness"],
            )
        else:
            draw_wall_v(
                msp,
                wall["coord"],
                wall["start"],
                wall["end"],
                gaps=gaps,
                thickness=wall["draw_thickness"],
            )

    for wall_id, openings in render_plan["openings_by_wall"].items():
        wall = wall_map[wall_id]
        for opening in openings:
            _draw_opening(msp, wall, opening)

    doc.saveas(out_path)


def build_render_plan(structure: dict[str, Any]) -> dict[str, Any]:
    use_detected_thickness = _use_detected_wall_thickness(structure)
    wall_geometries = [
        _wall_geometry(wall, use_detected_thickness=use_detected_thickness)
        for wall in structure.get("walls") or []
    ]
    wall_map = {wall["id"]: wall for wall in wall_geometries}

    junctions = structure.get("junctions") or []
    if junctions:
        _apply_junction_extensions(wall_geometries, junctions, wall_map)

    openings_by_wall: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for opening in structure.get("openings") or []:
        wall_id = opening.get("wall_id")
        if wall_id in wall_map:
            openings_by_wall[wall_id].append(_opening_geometry(opening, wall_map[wall_id]))

    wall_plans = []
    wall_lines = []
    for wall in wall_geometries:
        gaps = [
            {
                "start": float(opening["start"]),
                "end": float(opening["end"]),
                "kind": opening["kind"],
                "opening_id": opening["id"],
            }
            for opening in openings_by_wall.get(wall["id"], [])
        ]
        segments = split_segments(wall["start"], wall["end"], [(gap["start"], gap["end"]) for gap in gaps])
        wall_plan = {
            **wall,
            "segments": [{"start": float(start), "end": float(end)} for start, end in segments],
            "gaps": gaps,
        }
        wall_plans.append(wall_plan)
        wall_lines.extend(_wall_line_entities(wall_plan))

    return {
        "meta": {
            "use_detected_thickness": use_detected_thickness,
            "wall_count": len(wall_geometries),
            "opening_count": sum(len(openings) for openings in openings_by_wall.values()),
        },
        "wall_geometries": wall_geometries,
        "walls": wall_plans,
        "openings_by_wall": {wall_id: list(openings) for wall_id, openings in openings_by_wall.items()},
        "wall_lines": wall_lines,
    }


# ---------------------------------------------------------------------------
# Junction-based corner extensions
# ---------------------------------------------------------------------------

def _apply_junction_extensions(
    wall_geometries: list[dict[str, Any]],
    junctions: list[dict[str, Any]],
    wall_map: dict[str, dict[str, Any]],
) -> None:
    """Extend wall endpoints at L/T/X junctions so double-line walls overlap cleanly."""
    # Track which (wall_id, endpoint) pairs have already been extended
    extended: set[tuple[str, str]] = set()

    for junction in junctions:
        jp = junction.get("point", {})
        jx = float(jp.get("x", 0))
        jy = float(jp.get("y", 0))

        for wall_id in junction.get("wall_ids", []):
            wall = wall_map.get(wall_id)
            if wall is None:
                continue
            extension = float(wall.get("draw_thickness", THICKNESS))
            endpoint_tolerance = max(JUNCTION_TOLERANCE, extension / 2.0 + 2.0)

            if wall["orientation"] == "horizontal":
                # Check if junction is at the start (left end) of the wall
                if abs(wall["start"] - jx) <= endpoint_tolerance:
                    key = (wall_id, "start")
                    if key not in extended:
                        wall["start"] -= extension
                        extended.add(key)
                # Check if junction is at the end (right end) of the wall
                elif abs(wall["end"] - jx) <= endpoint_tolerance:
                    key = (wall_id, "end")
                    if key not in extended:
                        wall["end"] += extension
                        extended.add(key)
            else:  # vertical
                # Check if junction is at the start (bottom) of the wall
                if abs(wall["start"] - jy) <= endpoint_tolerance:
                    key = (wall_id, "start")
                    if key not in extended:
                        wall["start"] -= extension
                        extended.add(key)
                # Check if junction is at the end (top) of the wall
                elif abs(wall["end"] - jy) <= endpoint_tolerance:
                    key = (wall_id, "end")
                    if key not in extended:
                        wall["end"] += extension
                        extended.add(key)


# ---------------------------------------------------------------------------
# Wall geometry
# ---------------------------------------------------------------------------

def _wall_geometry(
    wall: dict[str, Any],
    *,
    use_detected_thickness: bool = False,
) -> dict[str, Any]:
    polyline = wall.get("polyline") or []
    if len(polyline) != 2:
        raise ValueError(f"Wall {wall.get('id')} must have exactly 2 polyline points in phase 1.")

    start = _point(polyline[0])
    end = _point(polyline[1])
    raw_thickness = max(1.0, float(wall.get("thickness", THICKNESS)))
    draw_thickness = raw_thickness if use_detected_thickness else float(THICKNESS)

    if abs(start["y"] - end["y"]) <= EPSILON:
        if start["x"] > end["x"]:
            start, end = end, start
        return {
            "id": wall["id"],
            "orientation": "horizontal",
            "coord": start["y"],
            "start": start["x"],
            "end": end["x"],
            "base_start": start["x"],
            "base_end": end["x"],
            "thickness": raw_thickness,
            "draw_thickness": draw_thickness,
            "is_exterior": bool(wall.get("is_exterior", False)),
        }

    if abs(start["x"] - end["x"]) <= EPSILON:
        if start["y"] > end["y"]:
            start, end = end, start
        return {
            "id": wall["id"],
            "orientation": "vertical",
            "coord": start["x"],
            "start": start["y"],
            "end": end["y"],
            "base_start": start["y"],
            "base_end": end["y"],
            "thickness": raw_thickness,
            "draw_thickness": draw_thickness,
            "is_exterior": bool(wall.get("is_exterior", False)),
        }

    raise ValueError(f"Wall {wall.get('id')} is not axis-aligned.")


# ---------------------------------------------------------------------------
# Opening geometry
# ---------------------------------------------------------------------------

def _opening_geometry(opening: dict[str, Any], wall: dict[str, Any]) -> dict[str, Any]:
    span = float(opening["span"])
    offset = opening.get("offset")
    axis_start = float(wall.get("base_start", wall["start"]))
    if offset is None:
        position = _point(opening["position"])
        if wall["orientation"] == "horizontal":
            start = position["x"] - (span / 2.0)
        else:
            start = position["y"] - (span / 2.0)
    else:
        start = axis_start + float(offset)
    end = start + span
    return {
        "id": opening["id"],
        "kind": opening["kind"],
        "wall_id": wall["id"],
        "orientation": wall["orientation"],
        "side": opening.get("side"),
        "swing": opening.get("swing"),
        "door_type": opening.get("door_type", opening.get("type", "normal")),
        "start": start,
        "end": end,
        "span": span,
    }


def _draw_opening(msp: Any, wall: dict[str, Any], opening: dict[str, Any]) -> None:
    if opening["kind"] == "door":
        _draw_door_opening(msp, wall, opening)
        return

    _draw_window_opening(msp, wall, opening)


def _draw_door_opening(msp: Any, wall: dict[str, Any], opening: dict[str, Any]) -> None:
    door_type = opening.get("door_type", "normal")
    wall_thickness = float(wall.get("draw_thickness", THICKNESS))

    if door_type == "garage":
        if opening["orientation"] == "horizontal":
            draw_garage_door(msp, opening["start"], wall["coord"] + wall_thickness / 2, opening["span"], "horizontal")
        else:
            draw_garage_door(msp, wall["coord"] + wall_thickness / 2, opening["start"], opening["span"], "vertical")
        return

    if door_type == "sliding":
        if opening["orientation"] == "horizontal":
            draw_sliding_door(msp, opening["start"], wall["coord"] + wall_thickness / 2, opening["span"], "horizontal")
        else:
            draw_sliding_door(msp, wall["coord"] + wall_thickness / 2, opening["start"], opening["span"], "vertical")
        return

    swing = opening.get("swing") or _default_swing(opening.get("side"))
    if swing is None:
        return

    # Hinge point calculation:
    # wall["coord"] is the bottom/left face of the double-line wall
    # wall["coord"] + THICKNESS is the top/right face
    if opening["orientation"] == "horizontal":
        hinge_x = opening["start"]
        if opening.get("side") == "bottom":
            # Room is above the wall → hinge at top face, swing up
            hinge_y = wall["coord"] + wall_thickness
        else:
            # Room is below the wall → hinge at bottom face, swing down
            hinge_y = wall["coord"]
        draw_door(msp, hinge_x, hinge_y, opening["span"], swing)
        return

    # Vertical wall
    hinge_y = opening["start"]
    if opening.get("side") == "left":
        # Room is to the right → hinge at right face, swing right
        hinge_x = wall["coord"] + wall_thickness
    else:
        # Room is to the left → hinge at left face, swing left
        hinge_x = wall["coord"]
    draw_door(msp, hinge_x, hinge_y, opening["span"], swing)


def _draw_window_opening(msp: Any, wall: dict[str, Any], opening: dict[str, Any]) -> None:
    side = opening.get("side")
    wall_thickness = float(wall.get("draw_thickness", THICKNESS))
    if opening["orientation"] == "horizontal":
        if side == "top":
            # Window on top face of wall
            draw_window_h(msp, opening["start"], wall["coord"] + wall_thickness, opening["span"], side="top")
        else:
            # Window on bottom face of wall (default)
            draw_window_h(msp, opening["start"], wall["coord"], opening["span"], side=side or "bottom")
        return

    draw_window_v(
        msp,
        wall["coord"],
        opening["start"],
        opening["span"],
        side=side or "left",
        thickness=wall_thickness,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _point(raw_point: dict[str, Any] | list[Any] | tuple[Any, Any]) -> dict[str, float]:
    if isinstance(raw_point, dict):
        return {"x": float(raw_point["x"]), "y": float(raw_point["y"])}
    if isinstance(raw_point, (list, tuple)) and len(raw_point) >= 2:
        return {"x": float(raw_point[0]), "y": float(raw_point[1])}
    raise ValueError("Point must be a dict with x/y or a 2-item sequence.")


def _default_swing(side: str | None) -> str | None:
    return {
        "bottom": "up",
        "top": "down",
        "left": "right",
        "right": "left",
    }.get(side)


def _use_detected_wall_thickness(structure: dict[str, Any]) -> bool:
    meta = structure.get("structure_meta") or {}
    return meta.get("unit") == "pixel" or meta.get("scale_status") == "unverified"


def _wall_line_entities(wall: dict[str, Any]) -> list[dict[str, Any]]:
    thickness = float(wall.get("draw_thickness", THICKNESS))
    entities: list[dict[str, Any]] = []
    if wall["orientation"] == "horizontal":
        for segment in wall.get("segments", []):
            start = float(segment["start"])
            end = float(segment["end"])
            entities.append(_line_entity(wall["id"], start, wall["coord"], end, wall["coord"], wall["is_exterior"]))
            entities.append(
                _line_entity(
                    wall["id"],
                    start,
                    wall["coord"] + thickness,
                    end,
                    wall["coord"] + thickness,
                    wall["is_exterior"],
                )
            )
        for gap in wall.get("gaps", []):
            entities.append(
                _line_entity(
                    wall["id"],
                    gap["start"],
                    wall["coord"],
                    gap["start"],
                    wall["coord"] + thickness,
                    wall["is_exterior"],
                )
            )
            entities.append(
                _line_entity(
                    wall["id"],
                    gap["end"],
                    wall["coord"],
                    gap["end"],
                    wall["coord"] + thickness,
                    wall["is_exterior"],
                )
            )
        return entities

    for segment in wall.get("segments", []):
        start = float(segment["start"])
        end = float(segment["end"])
        entities.append(_line_entity(wall["id"], wall["coord"], start, wall["coord"], end, wall["is_exterior"]))
        entities.append(
            _line_entity(
                wall["id"],
                wall["coord"] + thickness,
                start,
                wall["coord"] + thickness,
                end,
                wall["is_exterior"],
            )
        )
    for gap in wall.get("gaps", []):
        entities.append(
            _line_entity(
                wall["id"],
                wall["coord"],
                gap["start"],
                wall["coord"] + thickness,
                gap["start"],
                wall["is_exterior"],
            )
        )
        entities.append(
            _line_entity(
                wall["id"],
                wall["coord"],
                gap["end"],
                wall["coord"] + thickness,
                gap["end"],
                wall["is_exterior"],
            )
        )
    return entities


def _line_entity(
    wall_id: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    is_exterior: bool,
) -> dict[str, Any]:
    return {
        "type": "line",
        "layer": "WALLS",
        "wall_id": wall_id,
        "is_exterior": bool(is_exterior),
        "start": {"x": float(x1), "y": float(y1)},
        "end": {"x": float(x2), "y": float(y2)},
    }
