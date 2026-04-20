from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import tempfile
import shutil
import subprocess
import uuid
import re

import ezdxf

from ..site_fit.cad_units import canonical_internal_unit, convert_value


DXF_UNIT_MAP = {
    0: "unitless",
    1: "inch",
    2: "foot",
    4: "mm",
    5: "cm",
    6: "m",
}

SUPPORTED_TYPES = {"LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "TEXT", "MTEXT"}
COMPOSITE_TYPES = {"INSERT", "DIMENSION"}


@dataclass(frozen=True)
class ExtractedCadEntity:
    type: str
    layer: str
    bbox: dict[str, float]
    start: dict[str, float] | None = None
    end: dict[str, float] | None = None
    points: tuple[dict[str, float], ...] = ()
    text: str | None = None
    position: dict[str, float] | None = None


@dataclass(frozen=True)
class CadView:
    role: str
    bbox: dict[str, float] | None
    entities: tuple[ExtractedCadEntity, ...]


@dataclass(frozen=True)
class ExtractedMeasurements:
    width: float
    height: float
    source: str


def extract_cad_file(path: Path, *, source_name: str | None = None) -> dict:
    normalized_path, conversion_status, conversion_note, cleanup_dir = _resolve_input_file(path)
    try:
        doc = ezdxf.readfile(str(normalized_path))
        source_unit = _resolve_doc_unit(doc)
        canonical_unit = canonical_internal_unit(source_unit, fallback="inch")
        entities = tuple(_iter_entities(doc, source_unit=source_unit, canonical_unit=canonical_unit))
        if not entities:
            raise ValueError("No supported CAD entities were found in the uploaded file.")

        clusters = _cluster_entities(entities)
        ordered = sorted(clusters, key=_cluster_score, reverse=True)
        floor_cluster, site_cluster = _assign_floor_and_site_clusters(ordered)
        floor_entities = _normalize_floor_entities(floor_cluster)
        site_entities = _normalize_site_entities(site_cluster)

        floor_view = _build_view("floor_plan", floor_entities["entities"], measurements=floor_entities["measurements"])
        site_view = _build_view("site_plan", site_entities["entities"], measurements=site_entities["measurements"])
        fit_summary = _build_fit_summary(
            canonical_unit=canonical_unit,
            floor_entities=floor_view.get("entities", []),
            footprint_bbox=floor_view.get("bbox"),
            property_bbox=site_entities.get("property_bbox"),
            buildable_bbox=site_entities.get("buildable_bbox"),
            buildable_polygon=site_entities.get("buildable_polygon"),
        )
        warnings: list[str] = []
        if len(ordered) == 1:
            warnings.append("Only one spatial view cluster was detected; site extraction may be incomplete.")
        if site_view["bbox"] is None:
            warnings.append("No separate site-plan cluster was detected.")
        if floor_entities["measurements"] is not None:
            warnings.append("Floor-plan wall geometry was normalized from dimension annotations before side-by-side comparison.")
        if fit_summary.get("fits_within_buildable_bbox") is None:
            warnings.append("Buildable-fit summary is unavailable because no recognizable buildable envelope layer was extracted.")

        return {
            "analysis_id": uuid.uuid4().hex[:12],
            "source_name": source_name or path.name,
            "source_format": path.suffix.lower().lstrip("."),
            "canonical_unit": canonical_unit,
            "conversion_status": conversion_status,
            "conversion_note": conversion_note,
            "floor_plan": floor_view,
            "site_plan": site_view,
            "side_by_side": _build_side_by_side(floor_view, site_view, canonical_unit=canonical_unit),
            "fit_summary": fit_summary,
            "warnings": _build_warnings(source_unit=source_unit, warnings=warnings),
        }
    finally:
        if cleanup_dir is not None:
            shutil.rmtree(cleanup_dir, ignore_errors=True)


def _resolve_input_file(path: Path) -> tuple[Path, str, str | None, Path | None]:
    suffix = path.suffix.lower()
    if suffix == ".dxf":
        return path, "native_dxf", None, None
    if suffix == ".dwg":
        converted, temp_dir = _convert_dwg_to_dxf(path)
        return converted, "dwg_converted_to_dxf", "DWG was converted to DXF via AutoCAD Core Console.", temp_dir
    raise ValueError("Only .dxf and .dwg files are supported.")


def _convert_dwg_to_dxf(path: Path) -> tuple[Path, Path]:
    accoreconsole = _find_accoreconsole()
    if accoreconsole is None:
        raise ValueError("DWG support requires AutoCAD Core Console, but it was not found on this machine.")

    temp_dir = Path(tempfile.mkdtemp(prefix="pointai_cad_"))
    script_path = temp_dir / "convert.scr"
    out_path = temp_dir / f"{path.stem}.dxf"
    script_path.write_text(
        "\n".join(
            [
                "FILEDIA 0",
                "CMDDIA 0",
                "_.SAVEAS",
                "2018 DXF",
                str(out_path),
                "_.QUIT",
            ]
        ),
        encoding="utf-8",
    )
    command = [
        str(accoreconsole),
        "/i",
        str(path),
        "/s",
        str(script_path),
        "/l",
        "en-US",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
    if result.returncode != 0 or not out_path.exists():
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        message = stderr or stdout or "Unknown AutoCAD Core Console failure."
        raise ValueError(f"DWG conversion failed: {message}")
    return out_path, temp_dir


def _find_accoreconsole() -> Path | None:
    env_value = None
    try:
        import os
        env_value = os.environ.get("POINTAI_ACCORECONSOLE")
    except Exception:
        env_value = None
    candidates = [
        Path(env_value) if env_value else None,
        Path(r"C:\Program Files\Autodesk\AutoCAD LT 2026\accoreconsole.exe"),
        Path(r"C:\Program Files\Autodesk\AutoCAD 2026\accoreconsole.exe"),
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    resolved = shutil.which("accoreconsole.exe")
    return Path(resolved) if resolved else None


def _resolve_doc_unit(doc) -> str:
    unit_code = int(getattr(doc, "units", 0) or 0)
    return DXF_UNIT_MAP.get(unit_code, "inch")


def _iter_entities(doc, *, source_unit: str, canonical_unit: str):
    for entity in doc.modelspace():
        yield from _flatten_entity(entity, source_unit=source_unit, canonical_unit=canonical_unit)


def _flatten_entity(entity, *, source_unit: str, canonical_unit: str):
    dxftype = entity.dxftype()
    if dxftype in COMPOSITE_TYPES:
        try:
            for virtual in entity.virtual_entities():
                yield from _flatten_entity(virtual, source_unit=source_unit, canonical_unit=canonical_unit)
        except Exception:
            return
        return
    if dxftype not in SUPPORTED_TYPES:
        return

    extracted = _extract_entity(entity, source_unit=source_unit, canonical_unit=canonical_unit)
    if extracted is not None:
        yield extracted


def _extract_entity(entity, *, source_unit: str, canonical_unit: str) -> ExtractedCadEntity | None:
    layer = str(getattr(entity.dxf, "layer", "0") or "0")
    dxftype = entity.dxftype()

    if dxftype == "LINE":
        start = _point(entity.dxf.start.x, entity.dxf.start.y, source_unit, canonical_unit)
        end = _point(entity.dxf.end.x, entity.dxf.end.y, source_unit, canonical_unit)
        bbox = _bbox_from_points((start, end))
        return ExtractedCadEntity(type="line", layer=layer, start=start, end=end, bbox=bbox)

    if dxftype in {"LWPOLYLINE", "POLYLINE"}:
        points = _polyline_points(entity, source_unit=source_unit, canonical_unit=canonical_unit)
        if len(points) < 2:
            return None
        bbox = _bbox_from_points(points)
        return ExtractedCadEntity(type="polyline", layer=layer, points=tuple(points), bbox=bbox)

    if dxftype == "ARC":
        points = _sample_arc(
            center=(float(entity.dxf.center.x), float(entity.dxf.center.y)),
            radius=float(entity.dxf.radius),
            start_angle=float(entity.dxf.start_angle),
            end_angle=float(entity.dxf.end_angle),
            source_unit=source_unit,
            canonical_unit=canonical_unit,
        )
        bbox = _bbox_from_points(points)
        return ExtractedCadEntity(type="polyline", layer=layer, points=tuple(points), bbox=bbox)

    if dxftype == "CIRCLE":
        points = _sample_arc(
            center=(float(entity.dxf.center.x), float(entity.dxf.center.y)),
            radius=float(entity.dxf.radius),
            start_angle=0.0,
            end_angle=360.0,
            source_unit=source_unit,
            canonical_unit=canonical_unit,
        )
        bbox = _bbox_from_points(points)
        return ExtractedCadEntity(type="polyline", layer=layer, points=tuple(points), bbox=bbox)

    if dxftype == "TEXT":
        text = str(getattr(entity.dxf, "text", "") or "").strip()
        insert = getattr(entity.dxf, "insert", None)
        if insert is None:
            return None
        position = _point(insert.x, insert.y, source_unit, canonical_unit)
        bbox = _bbox_from_points((position,))
        return ExtractedCadEntity(type="text", layer=layer, text=text, position=position, bbox=bbox)

    if dxftype == "MTEXT":
        text = str(entity.text or "").strip()
        insert = getattr(entity.dxf, "insert", None)
        if insert is None:
            return None
        position = _point(insert.x, insert.y, source_unit, canonical_unit)
        bbox = _bbox_from_points((position,))
        return ExtractedCadEntity(type="text", layer=layer, text=text, position=position, bbox=bbox)

    return None


def _polyline_points(entity, *, source_unit: str, canonical_unit: str) -> list[dict[str, float]]:
    if entity.dxftype() == "LWPOLYLINE":
        raw_points = [(float(point[0]), float(point[1])) for point in entity.get_points("xy")]
    else:
        raw_points = [(float(vertex.dxf.location.x), float(vertex.dxf.location.y)) for vertex in entity.vertices]
    points = [_point(x, y, source_unit, canonical_unit) for x, y in raw_points]
    if getattr(entity, "closed", False) and points and points[0] != points[-1]:
        points.append(dict(points[0]))
    return points


def _sample_arc(*, center: tuple[float, float], radius: float, start_angle: float, end_angle: float, source_unit: str, canonical_unit: str) -> list[dict[str, float]]:
    if end_angle < start_angle:
        end_angle += 360.0
    steps = max(16, int(abs(end_angle - start_angle) / 15.0))
    cx, cy = center
    points: list[dict[str, float]] = []
    for idx in range(steps + 1):
        angle = math.radians(start_angle + ((end_angle - start_angle) * idx / steps))
        x = cx + (radius * math.cos(angle))
        y = cy + (radius * math.sin(angle))
        points.append(_point(x, y, source_unit, canonical_unit))
    return points


def _point(x: float, y: float, source_unit: str, canonical_unit: str) -> dict[str, float]:
    return {
        "x": convert_value(float(x), from_unit=source_unit, to_unit=canonical_unit),
        "y": convert_value(float(y), from_unit=source_unit, to_unit=canonical_unit),
    }


def _bbox_from_points(points) -> dict[str, float]:
    xs = [float(point["x"]) for point in points]
    ys = [float(point["y"]) for point in points]
    x1 = min(xs)
    y1 = min(ys)
    x2 = max(xs)
    y2 = max(ys)
    return {
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "width": x2 - x1,
        "height": y2 - y1,
    }


def _cluster_entities(entities: tuple[ExtractedCadEntity, ...]) -> list[list[ExtractedCadEntity]]:
    if not entities:
        return []
    overall = _bbox_from_points(
        [{"x": e.bbox["x1"], "y": e.bbox["y1"]} for e in entities]
        + [{"x": e.bbox["x2"], "y": e.bbox["y2"]} for e in entities]
    )
    margin = max(overall["width"], overall["height"]) * 0.03
    parent = list(range(len(entities)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for left in range(len(entities)):
        bbox_left = _expand_bbox(entities[left].bbox, margin)
        for right in range(left + 1, len(entities)):
            bbox_right = _expand_bbox(entities[right].bbox, margin)
            if _bboxes_overlap(bbox_left, bbox_right):
                union(left, right)

    grouped: dict[int, list[ExtractedCadEntity]] = {}
    for index, entity in enumerate(entities):
        grouped.setdefault(find(index), []).append(entity)
    return list(grouped.values())


def _expand_bbox(bbox: dict[str, float], margin: float) -> dict[str, float]:
    return {
        "x1": bbox["x1"] - margin,
        "y1": bbox["y1"] - margin,
        "x2": bbox["x2"] + margin,
        "y2": bbox["y2"] + margin,
    }


def _bboxes_overlap(left: dict[str, float], right: dict[str, float]) -> bool:
    return not (
        left["x2"] < right["x1"]
        or left["x1"] > right["x2"]
        or left["y2"] < right["y1"]
        or left["y1"] > right["y2"]
    )


def _cluster_score(entities: list[ExtractedCadEntity]) -> tuple[float, int]:
    bbox = _bbox_from_points(
        [{"x": entity.bbox["x1"], "y": entity.bbox["y1"]} for entity in entities]
        + [{"x": entity.bbox["x2"], "y": entity.bbox["y2"]} for entity in entities]
    )
    area = bbox["width"] * bbox["height"]
    return (area, len(entities))


def _assign_floor_and_site_clusters(clusters: list[list[ExtractedCadEntity]]) -> tuple[list[ExtractedCadEntity], list[ExtractedCadEntity]]:
    if not clusters:
        return [], []

    floor_index = _find_cluster_by_anchor(clusters, "FLOOR PLAN")
    site_index = _find_cluster_by_anchor(clusters, "SITE PLAN")

    if floor_index is None:
        floor_index = 0
    if site_index is None:
        remaining = [idx for idx in range(len(clusters)) if idx != floor_index]
        site_index = remaining[0] if remaining else None

    floor_cluster = list(clusters[floor_index])
    site_cluster: list[ExtractedCadEntity] = []
    for index, cluster in enumerate(clusters):
        if index == floor_index:
            continue
        if site_index is None or index == site_index or len(clusters) > 2:
            site_cluster.extend(cluster)
    return floor_cluster, site_cluster


def _find_cluster_by_anchor(clusters: list[list[ExtractedCadEntity]], anchor: str) -> int | None:
    upper_anchor = anchor.upper()
    for index, cluster in enumerate(clusters):
        for entity in cluster:
            if entity.type == "text" and entity.text and upper_anchor in entity.text.upper():
                return index
    return None


def _normalize_floor_entities(cluster: list[ExtractedCadEntity]) -> dict:
    geometry = [
        entity
        for entity in cluster
        if entity.type in {"line", "polyline"} and _is_floor_wall_layer(entity.layer)
    ]
    if not geometry:
        geometry = [entity for entity in cluster if entity.type in {"line", "polyline"}]
    measurements = _derive_floor_measurements(cluster, geometry)
    normalized_entities = _normalize_entities_to_origin(
        geometry,
        target_width=measurements.width if measurements else None,
        target_height=measurements.height if measurements else None,
    )
    return {"entities": normalized_entities, "measurements": measurements}


def _normalize_site_entities(cluster: list[ExtractedCadEntity]) -> dict:
    geometry = [
        entity
        for entity in cluster
        if entity.type in {"line", "polyline"} and _is_site_geometry_layer(entity.layer)
    ]
    if not geometry:
        geometry = [entity for entity in cluster if entity.type in {"line", "polyline"}]
    normalized_entities = _normalize_entities_to_origin(geometry)
    measurements = None
    bbox = _entities_bbox(normalized_entities)
    if bbox is not None:
        measurements = ExtractedMeasurements(width=bbox["width"], height=bbox["height"], source="geometry")
    property_entities = [entity for entity in normalized_entities if _is_property_layer(entity.layer)]
    buildable_entities = [entity for entity in normalized_entities if _is_buildable_layer(entity.layer)]
    return {
        "entities": normalized_entities,
        "measurements": measurements,
        "property_bbox": _entities_bbox(property_entities),
        "buildable_bbox": _entities_bbox(buildable_entities),
        "buildable_polygon": _extract_buildable_polygon(buildable_entities),
    }


def _is_floor_wall_layer(layer: str) -> bool:
    upper = (layer or "").upper()
    if "WALL" not in upper:
        return False
    blocked = ("ELECTRICAL", "WIRE", "DUCT", "HATCH")
    return not any(token in upper for token in blocked)


def _is_site_geometry_layer(layer: str) -> bool:
    upper = (layer or "").upper()
    keywords = ("SETBACK", "PROP", "SITE", "LOT", "BUILD", "EASE")
    return any(keyword in upper for keyword in keywords)


def _is_property_layer(layer: str) -> bool:
    upper = (layer or "").upper()
    return "PROP" in upper or "LOT" in upper


def _is_buildable_layer(layer: str) -> bool:
    upper = (layer or "").upper()
    return "SETBACK" in upper or "BUILD" in upper


def _derive_floor_measurements(cluster: list[ExtractedCadEntity], geometry: list[ExtractedCadEntity]) -> ExtractedMeasurements | None:
    wall_bbox = _entities_bbox(geometry)
    if wall_bbox is None:
        return None

    horizontal_candidates: list[float] = []
    vertical_candidates: list[float] = []
    for entity in cluster:
        if entity.type != "text" or not entity.text:
            continue
        if "DIM" not in (entity.layer or "").upper():
            continue
        if entity.position is None:
            continue
        value = _parse_dimension_text(entity.text)
        if value is None:
            continue
        x = float(entity.position["x"])
        y = float(entity.position["y"])
        if y < wall_bbox["y1"] or y > wall_bbox["y2"]:
            horizontal_candidates.append(value)
        if x < wall_bbox["x1"] or x > wall_bbox["x2"]:
            vertical_candidates.append(value)

    if not horizontal_candidates and not vertical_candidates:
        return None

    width = max(horizontal_candidates) if horizontal_candidates else wall_bbox["width"]
    height = max(vertical_candidates) if vertical_candidates else wall_bbox["height"]
    return ExtractedMeasurements(width=width, height=height, source="dimensions")


def _parse_dimension_text(text: str) -> float | None:
    cleaned = str(text or "").upper()
    cleaned = cleaned.replace("\\P", " ")
    cleaned = re.sub(r"\\A\d+;", "", cleaned)
    cleaned = re.sub(r"\\H[^;]*;", "", cleaned)
    cleaned = re.sub(r"\\C\d+;", "", cleaned)
    cleaned = re.sub(r"\\T[^;]*;", "", cleaned)
    cleaned = re.sub(r"\\[A-Z]", "", cleaned)
    cleaned = re.sub(r"\{\\H[^;]*;\\S(\d+)\/(\d+);?\}", lambda match: f" {match.group(1)}/{match.group(2)}", cleaned)
    cleaned = re.sub(r"\{[^}]*\}", " ", cleaned)
    cleaned = cleaned.replace("\\", " ")
    cleaned = " ".join(cleaned.split())

    match = re.match(r"^(?:(\d+)\')?\s*(?:(\d+)(?:\s+(\d+)/(\d+))?\")?", cleaned)
    if not match:
        return None
    feet = int(match.group(1) or 0)
    inches = int(match.group(2) or 0)
    numerator = int(match.group(3) or 0)
    denominator = int(match.group(4) or 1)
    fraction = (numerator / denominator) if numerator and denominator else 0.0
    total_inches = (feet * 12) + inches + fraction
    return total_inches if total_inches > 0 else None


def _normalize_entities_to_origin(
    entities: list[ExtractedCadEntity],
    *,
    target_width: float | None = None,
    target_height: float | None = None,
) -> list[ExtractedCadEntity]:
    bbox = _entities_bbox(entities)
    if bbox is None:
        return []

    scale_x = (target_width / bbox["width"]) if target_width is not None and bbox["width"] > 0 else 1.0
    scale_y = (target_height / bbox["height"]) if target_height is not None and bbox["height"] > 0 else 1.0
    normalized: list[ExtractedCadEntity] = []
    for entity in entities:
        normalized.append(
            _transform_entity(
                entity,
                translate_x=-bbox["x1"],
                translate_y=-bbox["y1"],
                scale_x=scale_x,
                scale_y=scale_y,
            )
        )
    return normalized


def _extract_buildable_polygon(entities: list[ExtractedCadEntity]) -> list[dict[str, float]] | None:
    paths = []
    for entity in entities:
        points = _entity_points(entity)
        if len(points) < 2:
            continue
        paths.append(points)
    if not paths:
        return None

    tolerance = 1e-3
    components = _group_paths_by_connectivity(paths, tolerance=tolerance)
    candidates: list[list[dict[str, float]]] = []
    for component in components:
        polygon = _compose_closed_path(component, tolerance=tolerance)
        if polygon is not None and len(polygon) >= 4:
            candidates.append(polygon)
    if not candidates:
        return None
    return max(candidates, key=lambda polygon: abs(_polygon_area(polygon)))


def _entity_points(entity: ExtractedCadEntity) -> list[dict[str, float]]:
    if entity.type == "line" and entity.start is not None and entity.end is not None:
        return [entity.start, entity.end]
    if entity.type == "polyline":
        return list(entity.points)
    return []


def _group_paths_by_connectivity(paths: list[list[dict[str, float]]], *, tolerance: float) -> list[list[list[dict[str, float]]]]:
    groups: list[list[list[dict[str, float]]]] = []
    for path in paths:
        matched_indexes: list[int] = []
        for index, group in enumerate(groups):
            if any(_paths_connected(path, candidate, tolerance=tolerance) for candidate in group):
                matched_indexes.append(index)
        if not matched_indexes:
            groups.append([path])
            continue
        base_group = groups[matched_indexes[0]]
        base_group.append(path)
        for index in reversed(matched_indexes[1:]):
            base_group.extend(groups.pop(index))
    return groups


def _paths_connected(left: list[dict[str, float]], right: list[dict[str, float]], *, tolerance: float) -> bool:
    left_ends = (left[0], left[-1])
    right_ends = (right[0], right[-1])
    return any(_points_close(a, b, tolerance=tolerance) for a in left_ends for b in right_ends)


def _compose_closed_path(paths: list[list[dict[str, float]]], *, tolerance: float) -> list[dict[str, float]] | None:
    if not paths:
        return None
    if len(paths) == 1:
        candidate = list(paths[0])
        if _points_close(candidate[0], candidate[-1], tolerance=tolerance):
            return candidate
        return None

    remaining = [list(path) for path in paths]
    ordered = remaining.pop(0)
    while remaining:
        current_end = ordered[-1]
        next_index = None
        next_path = None
        for index, candidate in enumerate(remaining):
            if _points_close(candidate[0], current_end, tolerance=tolerance):
                next_index = index
                next_path = candidate
                break
            if _points_close(candidate[-1], current_end, tolerance=tolerance):
                next_index = index
                next_path = list(reversed(candidate))
                break
        if next_path is None or next_index is None:
            return None
        ordered.extend(next_path[1:])
        remaining.pop(next_index)

    if not _points_close(ordered[0], ordered[-1], tolerance=tolerance):
        return None
    return ordered


def _points_close(left: dict[str, float], right: dict[str, float], *, tolerance: float) -> bool:
    return abs(float(left["x"]) - float(right["x"])) <= tolerance and abs(float(left["y"]) - float(right["y"])) <= tolerance


def _polygon_area(points: list[dict[str, float]]) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    for index in range(len(points) - 1):
        x1 = float(points[index]["x"])
        y1 = float(points[index]["y"])
        x2 = float(points[index + 1]["x"])
        y2 = float(points[index + 1]["y"])
        area += (x1 * y2) - (x2 * y1)
    return area / 2.0


def _point_in_polygon(point: dict[str, float], polygon: list[dict[str, float]]) -> bool:
    x = float(point["x"])
    y = float(point["y"])
    inside = False
    for index in range(len(polygon) - 1):
        x1 = float(polygon[index]["x"])
        y1 = float(polygon[index]["y"])
        x2 = float(polygon[index + 1]["x"])
        y2 = float(polygon[index + 1]["y"])
        intersects = ((y1 > y) != (y2 > y)) and (
            x < ((x2 - x1) * (y - y1) / ((y2 - y1) or 1e-9)) + x1
        )
        if intersects:
            inside = not inside
    return inside or _point_on_polygon_boundary(point, polygon, tolerance=1e-3)


def _point_on_polygon_boundary(point: dict[str, float], polygon: list[dict[str, float]], *, tolerance: float) -> bool:
    px = float(point["x"])
    py = float(point["y"])
    for index in range(len(polygon) - 1):
        ax = float(polygon[index]["x"])
        ay = float(polygon[index]["y"])
        bx = float(polygon[index + 1]["x"])
        by = float(polygon[index + 1]["y"])
        if _distance_point_to_segment(px, py, ax, ay, bx, by) <= tolerance:
            return True
    return False


def _distance_point_to_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx = bx - ax
    dy = by - ay
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / ((dx * dx) + (dy * dy))
    t = max(0.0, min(1.0, t))
    closest_x = ax + (t * dx)
    closest_y = ay + (t * dy)
    return math.hypot(px - closest_x, py - closest_y)


def _center_floor_bbox_within_buildable(footprint_bbox: dict[str, float], buildable_bbox: dict[str, float]) -> tuple[float, float]:
    x1 = float(buildable_bbox["x1"]) + ((float(buildable_bbox["width"]) - float(footprint_bbox["width"])) / 2.0)
    y1 = float(buildable_bbox["y1"]) + ((float(buildable_bbox["height"]) - float(footprint_bbox["height"])) / 2.0)
    return x1 - float(footprint_bbox["x1"]), y1 - float(footprint_bbox["y1"])


def _sample_entity_points(entity: dict, *, step: float = 24.0) -> list[dict[str, float]]:
    entity_type = str(entity.get("type") or "").lower()
    if entity_type == "line":
        start = entity.get("start")
        end = entity.get("end")
        if start is None or end is None:
            return []
        length = math.hypot(float(end["x"]) - float(start["x"]), float(end["y"]) - float(start["y"]))
        samples = max(2, int(length / step) + 1)
        points = []
        for idx in range(samples + 1):
            t = idx / samples
            points.append({
                "x": float(start["x"]) + ((float(end["x"]) - float(start["x"])) * t),
                "y": float(start["y"]) + ((float(end["y"]) - float(start["y"])) * t),
            })
        return points
    if entity_type == "polyline":
        raw_points = entity.get("points") or []
        if len(raw_points) < 2:
            return []
        samples: list[dict[str, float]] = []
        for index in range(len(raw_points) - 1):
            start = raw_points[index]
            end = raw_points[index + 1]
            segment_length = math.hypot(float(end["x"]) - float(start["x"]), float(end["y"]) - float(start["y"]))
            segment_samples = max(1, int(segment_length / step))
            for sample_index in range(segment_samples + 1):
                t = sample_index / segment_samples if segment_samples else 0.0
                point = {
                    "x": float(start["x"]) + ((float(end["x"]) - float(start["x"])) * t),
                    "y": float(start["y"]) + ((float(end["y"]) - float(start["y"])) * t),
                }
                if not samples or not _points_close(samples[-1], point, tolerance=1e-6):
                    samples.append(point)
        return samples
    return []


def _translated_entities_fit_polygon(entities: list[dict], *, dx: float, dy: float, polygon: list[dict[str, float]]) -> bool:
    for entity in entities:
        for point in _sample_entity_points(entity):
            shifted = {"x": float(point["x"]) + dx, "y": float(point["y"]) + dy}
            if not _point_in_polygon(shifted, polygon):
                return False
    return True


def _transform_entity(
    entity: ExtractedCadEntity,
    *,
    translate_x: float,
    translate_y: float,
    scale_x: float,
    scale_y: float,
) -> ExtractedCadEntity:
    def transform_point(point: dict[str, float] | None) -> dict[str, float] | None:
        if point is None:
            return None
        return {
            "x": (float(point["x"]) + translate_x) * scale_x,
            "y": (float(point["y"]) + translate_y) * scale_y,
        }

    start = transform_point(entity.start)
    end = transform_point(entity.end)
    points = tuple(transform_point(point) for point in entity.points)
    position = transform_point(entity.position)
    bbox_points = []
    if start is not None:
        bbox_points.append(start)
    if end is not None:
        bbox_points.append(end)
    bbox_points.extend(point for point in points if point is not None)
    if position is not None:
        bbox_points.append(position)
    bbox = _bbox_from_points(bbox_points) if bbox_points else {
        "x1": 0.0,
        "y1": 0.0,
        "x2": 0.0,
        "y2": 0.0,
        "width": 0.0,
        "height": 0.0,
    }
    return ExtractedCadEntity(
        type=entity.type,
        layer=entity.layer,
        bbox=bbox,
        start=start,
        end=end,
        points=tuple(point for point in points if point is not None),
        text=entity.text,
        position=position,
    )


def _entities_bbox(entities: list[ExtractedCadEntity]) -> dict[str, float] | None:
    if not entities:
        return None
    return _bbox_from_points(
        [{"x": entity.bbox["x1"], "y": entity.bbox["y1"]} for entity in entities]
        + [{"x": entity.bbox["x2"], "y": entity.bbox["y2"]} for entity in entities]
    )


def _build_view(role: str, entities: list[ExtractedCadEntity], *, measurements: ExtractedMeasurements | None = None) -> dict:
    if not entities:
        return {
            "role": role,
            "bbox": None,
            "summary": {"entity_count": 0, "line_count": 0, "polyline_count": 0, "text_count": 0},
            "entities": [],
            "measurements": None,
        }

    bbox = _entities_bbox(entities)
    summary = {
        "entity_count": len(entities),
        "line_count": sum(1 for entity in entities if entity.type == "line"),
        "polyline_count": sum(1 for entity in entities if entity.type == "polyline"),
        "text_count": sum(1 for entity in entities if entity.type == "text"),
    }
    serialized = []
    for entity in entities:
        serialized.append(
            {
                "type": entity.type,
                "layer": entity.layer,
                "start": entity.start,
                "end": entity.end,
                "points": list(entity.points),
                "text": entity.text,
                "position": entity.position,
                "bbox": entity.bbox,
            }
        )
    measurements_payload = None
    if measurements is not None:
        measurements_payload = {
            "width": measurements.width,
            "height": measurements.height,
            "source": measurements.source,
        }
    elif bbox is not None:
        measurements_payload = {
            "width": bbox["width"],
            "height": bbox["height"],
            "source": "geometry",
        }
    return {"role": role, "bbox": bbox, "summary": summary, "entities": serialized, "measurements": measurements_payload}


def _build_side_by_side(floor_view: dict, site_view: dict, *, canonical_unit: str) -> dict:
    floor_width = float((floor_view.get("bbox") or {}).get("width", 0.0) or 0.0)
    site_width = float((site_view.get("bbox") or {}).get("width", 0.0) or 0.0)
    floor_height = float((floor_view.get("bbox") or {}).get("height", 0.0) or 0.0)
    site_height = float((site_view.get("bbox") or {}).get("height", 0.0) or 0.0)
    gap = max(24.0, (floor_width + site_width) * 0.02)
    return {
        "canonical_unit": canonical_unit,
        "gap": gap,
        "floor_width": floor_width,
        "site_width": site_width,
        "max_height": max(floor_height, site_height),
    }


def _build_fit_summary(
    *,
    canonical_unit: str,
    floor_entities: list[dict],
    footprint_bbox: dict[str, float] | None,
    property_bbox: dict[str, float] | None,
    buildable_bbox: dict[str, float] | None,
    buildable_polygon: list[dict[str, float]] | None,
) -> dict:
    summary = {
        "comparison_unit": canonical_unit,
        "basis": "unavailable",
        "footprint_bbox": footprint_bbox,
        "property_bbox": property_bbox,
        "buildable_bbox": buildable_bbox,
        "buildable_polygon": buildable_polygon,
        "width_delta": None,
        "height_delta": None,
        "fits_within_buildable_bbox": None,
        "fits_within_buildable_polygon": None,
    }
    if footprint_bbox is not None and buildable_bbox is not None:
        width_delta = float(buildable_bbox["width"]) - float(footprint_bbox["width"])
        height_delta = float(buildable_bbox["height"]) - float(footprint_bbox["height"])
        summary["width_delta"] = width_delta
        summary["height_delta"] = height_delta
        summary["fits_within_buildable_bbox"] = width_delta >= -0.001 and height_delta >= -0.001
        summary["basis"] = "bbox"

    if footprint_bbox is not None and buildable_bbox is not None and buildable_polygon:
        dx, dy = _center_floor_bbox_within_buildable(footprint_bbox, buildable_bbox)
        summary["fits_within_buildable_polygon"] = _translated_entities_fit_polygon(
            floor_entities,
            dx=dx,
            dy=dy,
            polygon=buildable_polygon,
        )
        summary["basis"] = "buildable_polygon"
    return summary


def _build_warnings(*, source_unit: str, warnings: list[str]) -> list[str]:
    combined = list(warnings)
    if source_unit == "unitless":
        combined.append("CAD file did not declare a drawing unit. The workspace assumed inch as the fallback unit.")
    return combined
