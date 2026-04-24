from __future__ import annotations

from pathlib import Path
import math
import tempfile
import shutil
import subprocess
import uuid
import re

import cv2
import ezdxf
import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

from .classification import (
    assign_floor_and_site_clusters as _assign_floor_and_site_clusters,
    cluster_score as _cluster_score,
    is_annotation_geometry_layer as _is_annotation_geometry_layer,
    is_buildable_layer as _is_buildable_layer,
    is_floor_candidate_geometry_entity as _is_floor_candidate_geometry_entity,
    is_floor_wall_layer as _is_floor_wall_layer,
    is_property_layer as _is_property_layer,
    is_room_closure_layer as _is_room_closure_layer,
    is_site_geometry_layer as _is_site_geometry_layer,
)
from .models import CadView, ExtractedCadEntity, ExtractedMeasurements, ExtractedRoom
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
        floor_cluster, site_cluster, assignment_mode = _assign_floor_and_site_clusters(
            ordered,
            parse_dimension_text=_parse_dimension_text,
            is_room_label_entity=_is_room_label_entity,
        )
        floor_entities = _normalize_floor_entities(floor_cluster)
        site_entities = _normalize_site_entities(site_cluster)

        floor_view = _build_view(
            "floor_plan",
            floor_entities["entities"],
            measurements=floor_entities["measurements"],
            rooms=floor_entities["rooms"],
            support_entities=floor_entities["support_entities"],
        )
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
        if assignment_mode == "semantic_layer_split":
            warnings.append("Floor and site views were separated by CAD layers and semantic role hints because spatial clustering was ambiguous.")
        elif len(ordered) == 1:
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


def _flatten_entity(entity, *, source_unit: str, canonical_unit: str, composite_origin: str | None = None):
    dxftype = entity.dxftype()
    if dxftype in COMPOSITE_TYPES:
        try:
            for virtual in entity.virtual_entities():
                yield from _flatten_entity(
                    virtual,
                    source_unit=source_unit,
                    canonical_unit=canonical_unit,
                    composite_origin=dxftype,
                )
        except Exception:
            return
        return
    if dxftype not in SUPPORTED_TYPES:
        return

    extracted = _extract_entity(
        entity,
        source_unit=source_unit,
        canonical_unit=canonical_unit,
        composite_origin=composite_origin,
    )
    if extracted is not None:
        yield extracted


def _extract_entity(entity, *, source_unit: str, canonical_unit: str, composite_origin: str | None = None) -> ExtractedCadEntity | None:
    layer = str(getattr(entity.dxf, "layer", "0") or "0")
    dxftype = entity.dxftype()

    if dxftype == "LINE":
        start = _point(entity.dxf.start.x, entity.dxf.start.y, source_unit, canonical_unit)
        end = _point(entity.dxf.end.x, entity.dxf.end.y, source_unit, canonical_unit)
        bbox = _bbox_from_points((start, end))
        return ExtractedCadEntity(type="line", layer=layer, start=start, end=end, bbox=bbox, origin=composite_origin)

    if dxftype in {"LWPOLYLINE", "POLYLINE"}:
        points = _polyline_points(entity, source_unit=source_unit, canonical_unit=canonical_unit)
        if len(points) < 2:
            return None
        bbox = _bbox_from_points(points)
        return ExtractedCadEntity(type="polyline", layer=layer, points=tuple(points), bbox=bbox, origin=composite_origin)

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
        return ExtractedCadEntity(type="polyline", layer=layer, points=tuple(points), bbox=bbox, origin=composite_origin)

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
        return ExtractedCadEntity(type="polyline", layer=layer, points=tuple(points), bbox=bbox, origin=composite_origin)

    if dxftype == "TEXT":
        text = str(getattr(entity.dxf, "text", "") or "").strip()
        insert = getattr(entity.dxf, "insert", None)
        if insert is None:
            return None
        position = _point(insert.x, insert.y, source_unit, canonical_unit)
        bbox = _bbox_from_points((position,))
        return ExtractedCadEntity(type="text", layer=layer, text=text, position=position, bbox=bbox, origin=composite_origin)

    if dxftype == "MTEXT":
        text = str(entity.text or "").strip()
        insert = getattr(entity.dxf, "insert", None)
        if insert is None:
            return None
        position = _point(insert.x, insert.y, source_unit, canonical_unit)
        bbox = _bbox_from_points((position,))
        return ExtractedCadEntity(type="text", layer=layer, text=text, position=position, bbox=bbox, origin=composite_origin)

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


def _normalize_floor_entities(cluster: list[ExtractedCadEntity]) -> dict:
    geometry = [
        entity
        for entity in cluster
        if entity.type in {"line", "polyline"} and _is_floor_wall_layer(entity.layer)
    ]
    if not geometry:
        geometry = [
            entity
            for entity in cluster
            if _is_floor_candidate_geometry_entity(entity)
        ]
    if not geometry:
        geometry = [
            entity
            for entity in cluster
            if entity.type in {"line", "polyline"} and not _is_annotation_geometry_layer(entity.layer)
        ]
    room_geometry = [
        entity
        for entity in cluster
        if entity.type in {"line", "polyline"} and (_is_floor_wall_layer(entity.layer) or _is_room_closure_layer(entity.layer))
    ]
    if not room_geometry:
        room_geometry = geometry
    measurements = _derive_floor_measurements(cluster, geometry)
    transform = _resolve_normalization_transform(
        geometry,
        target_width=measurements.width if measurements else None,
        target_height=measurements.height if measurements else None,
    )
    normalized_entities = _apply_normalization_transform(geometry, transform)
    normalized_room_geometry = _apply_normalization_transform(room_geometry, transform)
    room_label_candidates = [
        entity
        for entity in cluster
        if entity.type == "text" and entity.position is not None and _is_room_label_entity(entity)
    ]
    preferred_room_layers = [
        entity
        for entity in room_label_candidates
        if "ROOM" in (entity.layer or "").upper()
    ]
    room_labels = preferred_room_layers or room_label_candidates
    normalized_room_labels = _coalesce_room_labels(_apply_normalization_transform(room_labels, transform))
    rooms = _extract_rooms_from_labels(normalized_room_geometry, normalized_room_labels)
    return {
        "entities": normalized_entities,
        "support_entities": normalized_room_geometry,
        "measurements": measurements,
        "rooms": rooms,
    }


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
    if not buildable_entities:
        buildable_entities = _fallback_buildable_entities(normalized_entities)
    buildable_polygon = _extract_buildable_polygon(buildable_entities)
    if not buildable_polygon and buildable_entities is not normalized_entities:
        buildable_polygon = _extract_buildable_polygon(normalized_entities)
    return {
        "entities": normalized_entities,
        "measurements": measurements,
        "property_bbox": _entities_bbox(property_entities),
        "buildable_bbox": _entities_bbox(buildable_entities),
        "buildable_polygon": buildable_polygon,
    }


def _fallback_buildable_entities(entities: list[ExtractedCadEntity]) -> list[ExtractedCadEntity]:
    if not entities:
        return []
    # When layers are not semantic (very common in user site plans), use all planar entities
    # as a conservative proxy for buildable envelope derivation.
    return entities


def _is_room_label_entity(entity: ExtractedCadEntity) -> bool:
    text = _clean_cad_text(entity.text or "")
    if not text or entity.position is None:
        return False
    if _parse_dimension_text(text) is not None:
        return False
    if len(text) > 28 or len(text.split()) > 3:
        return False
    blocked_text = (
        "FLOOR PLAN",
        "SITE PLAN",
        "BUILDABLE",
        "LOT",
        "SETBACK",
        "EASEMENT",
    )
    if any(token in text for token in blocked_text):
        return False
    return _contains_room_keyword(text)


def _contains_room_keyword(text: str) -> bool:
    room_keywords = (
        "BED",
        "BATH",
        "LIVING",
        "DINING",
        "KITCHEN",
        "GARAGE",
        "CLOSET",
        "CLST",
        "UTILITY",
        "PATIO",
        "PORCH",
        "ENTRY",
        "FOYER",
        "PANTRY",
        "LAUNDRY",
        "MSTR",
        "MASTER",
        "PWDR",
        "FAMILY",
        "BREAKFAST",
        "GAME",
        "MEDIA",
        "FLEX",
        "OFFICE",
        "STUDY",
        "WIC",
        "HALL",
        "ROOM",
        "STAIR",
    )
    return any(keyword in text for keyword in room_keywords)


def _coalesce_room_labels(labels: list[ExtractedCadEntity]) -> list[ExtractedCadEntity]:
    if not labels:
        return []

    parents = list(range(len(labels)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    for left in range(len(labels)):
        for right in range(left + 1, len(labels)):
            if _room_labels_should_merge(labels[left], labels[right]):
                union(left, right)

    grouped: dict[int, list[ExtractedCadEntity]] = {}
    for index, label in enumerate(labels):
        grouped.setdefault(find(index), []).append(label)

    coalesced: list[ExtractedCadEntity] = []
    for group in grouped.values():
        ordered = sorted(
            group,
            key=lambda label: (
                float(label.position["x"]) if label.position else 0.0,
                float(label.position["y"]) if label.position else 0.0,
                _clean_cad_text(label.text or ""),
            ),
        )
        name = _compose_room_name(ordered)
        xs = [float(label.position["x"]) for label in ordered if label.position is not None]
        ys = [float(label.position["y"]) for label in ordered if label.position is not None]
        position = {
            "x": float(sum(xs) / max(1, len(xs))),
            "y": float(sum(ys) / max(1, len(ys))),
        }
        coalesced.append(
            ExtractedCadEntity(
                type="text",
                layer=ordered[0].layer,
                text=name,
                position=position,
                bbox={
                    "x1": position["x"],
                    "y1": position["y"],
                    "x2": position["x"],
                    "y2": position["y"],
                    "width": 0.0,
                    "height": 0.0,
                },
            )
        )
    return coalesced


def _room_labels_should_merge(left: ExtractedCadEntity, right: ExtractedCadEntity) -> bool:
    if left.position is None or right.position is None:
        return False
    left_text = _clean_cad_text(left.text or "")
    right_text = _clean_cad_text(right.text or "")
    if not left_text or not right_text:
        return False
    dx = float(left.position["x"]) - float(right.position["x"])
    dy = float(left.position["y"]) - float(right.position["y"])
    distance = math.hypot(dx, dy)
    if left_text == right_text and distance <= 1.0:
        return True
    return distance <= 24.0


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
    cleaned = _clean_cad_text(text)

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


def _clean_cad_text(text: str) -> str:
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
    return " ".join(cleaned.split())


def _normalize_entities_to_origin(
    entities: list[ExtractedCadEntity],
    *,
    target_width: float | None = None,
    target_height: float | None = None,
) -> list[ExtractedCadEntity]:
    transform = _resolve_normalization_transform(
        entities,
        target_width=target_width,
        target_height=target_height,
    )
    return _apply_normalization_transform(entities, transform)


def _resolve_normalization_transform(
    entities: list[ExtractedCadEntity],
    *,
    target_width: float | None = None,
    target_height: float | None = None,
) -> dict[str, float] | None:
    bbox = _entities_bbox(entities)
    if bbox is None:
        return None

    scale_x = (target_width / bbox["width"]) if target_width is not None and bbox["width"] > 0 else 1.0
    scale_y = (target_height / bbox["height"]) if target_height is not None and bbox["height"] > 0 else 1.0
    return {
        "translate_x": -bbox["x1"],
        "translate_y": -bbox["y1"],
        "scale_x": scale_x,
        "scale_y": scale_y,
    }


def _apply_normalization_transform(
    entities: list[ExtractedCadEntity],
    transform: dict[str, float] | None,
) -> list[ExtractedCadEntity]:
    if transform is None:
        return []

    normalized: list[ExtractedCadEntity] = []
    for entity in entities:
        normalized.append(
            _transform_entity(
                entity,
                translate_x=float(transform["translate_x"]),
                translate_y=float(transform["translate_y"]),
                scale_x=float(transform["scale_x"]),
                scale_y=float(transform["scale_y"]),
            )
        )
    return normalized


def _extract_rooms_from_labels(
    geometry: list[ExtractedCadEntity],
    labels: list[ExtractedCadEntity],
) -> list[ExtractedRoom]:
    if not geometry or not labels:
        return []

    exact_rooms, matched_label_indexes = _extract_polygonized_rooms(geometry, labels)
    remaining_labels = [label for index, label in enumerate(labels) if index not in matched_label_indexes]
    if not remaining_labels:
        return sorted(exact_rooms, key=lambda room: (float(room.centroid["x"]), float(room.centroid["y"]), room.name))

    fallback_rooms = _extract_rasterized_rooms(geometry, remaining_labels)
    merged_rooms = _merge_rooms(exact_rooms, fallback_rooms)
    return sorted(merged_rooms, key=lambda room: (float(room.centroid["x"]), float(room.centroid["y"]), room.name))


def _extract_polygonized_rooms(
    geometry: list[ExtractedCadEntity],
    labels: list[ExtractedCadEntity],
) -> tuple[list[ExtractedRoom], set[int]]:
    room_polygons = _polygonize_floor_regions(geometry)
    if not room_polygons:
        return [], set()

    labels_by_region: dict[int, list[tuple[int, ExtractedCadEntity]]] = {}
    for label_index, label in enumerate(labels):
        if label.position is None:
            continue
        point = Point(float(label.position["x"]), float(label.position["y"]))
        matched_index = None
        for index, polygon in enumerate(room_polygons):
            if polygon.buffer(1e-3).covers(point):
                matched_index = index
                break
        if matched_index is not None:
            labels_by_region.setdefault(matched_index, []).append((label_index, label))

    extracted: list[ExtractedRoom] = []
    matched_label_indexes: set[int] = set()
    for region_index, region_labels in labels_by_region.items():
        polygon = room_polygons[region_index]
        matched_label_indexes.update(index for index, _ in region_labels)
        extracted.append(_build_room_from_polygon(polygon, [label for _, label in region_labels]))
    return extracted, matched_label_indexes


def _polygonize_floor_regions(geometry: list[ExtractedCadEntity]):
    lines = []
    for entity in geometry:
        raw_points = _entity_points(entity)
        if len(raw_points) < 2:
            continue
        coords = [(float(point["x"]), float(point["y"])) for point in raw_points]
        if len(coords) == 2:
            lines.append(LineString(coords))
            continue
        for index in range(len(coords) - 1):
            start = coords[index]
            end = coords[index + 1]
            if start != end:
                lines.append(LineString([start, end]))
    if not lines:
        return []

    merged = unary_union(lines)
    polygons = [
        polygon
        for polygon in polygonize(merged)
        if float(polygon.area) > 36.0
    ]
    return polygons


def _compose_room_name(labels: list[ExtractedCadEntity]) -> str:
    ordered = sorted(
        labels,
        key=lambda label: (
            -float(label.position["y"]) if label.position else 0.0,
            float(label.position["x"]) if label.position else 0.0,
            _clean_cad_text(label.text or ""),
        ),
    )
    parts: list[str] = []
    for label in ordered:
        cleaned = _clean_cad_text(label.text or "")
        if cleaned and cleaned not in parts:
            parts.append(cleaned)
    return " ".join(parts)


def _build_room_from_polygon(polygon, labels: list[ExtractedCadEntity]) -> ExtractedRoom:
    min_x, min_y, max_x, max_y = polygon.bounds
    polygon_points = tuple(
        {"x": float(x), "y": float(y)}
        for x, y in polygon.exterior.coords
    )
    return ExtractedRoom(
        name=_compose_room_name(labels),
        polygon=polygon_points,
        bbox={
            "x1": float(min_x),
            "y1": float(min_y),
            "x2": float(max_x),
            "y2": float(max_y),
            "width": float(max_x - min_x),
            "height": float(max_y - min_y),
        },
        centroid={"x": float(polygon.centroid.x), "y": float(polygon.centroid.y)},
        width=float(max_x - min_x),
        height=float(max_y - min_y),
        area=float(polygon.area),
        measurement_source="room_region",
    )


def _extract_rasterized_rooms(
    geometry: list[ExtractedCadEntity],
    labels: list[ExtractedCadEntity],
) -> list[ExtractedRoom]:
    if not geometry or not labels:
        return []

    bbox = _entities_bbox(geometry)
    if bbox is None:
        return []

    scale = max(2.0, min(4.0, 1600.0 / max(float(bbox["width"]), float(bbox["height"]), 1.0)))
    padding = max(24, int(round(scale * 18)))
    width_px = int(math.ceil(float(bbox["width"]) * scale)) + (padding * 2) + 1
    height_px = int(math.ceil(float(bbox["height"]) * scale)) + (padding * 2) + 1
    mask = np.zeros((height_px, width_px), dtype=np.uint8)
    wall_thickness = max(3, int(round(scale * 4)))
    closure_thickness = max(wall_thickness * 3, int(round(scale * 10)))

    for entity in geometry:
        points = _entity_points(entity)
        if len(points) < 2:
            continue
        pixel_points = np.array(
            [
                [
                    int(round(float(point["x"]) * scale)) + padding,
                    int(round(float(point["y"]) * scale)) + padding,
                ]
                for point in points
            ],
            dtype=np.int32,
        )
        stroke_thickness = closure_thickness if _is_room_closure_layer(entity.layer) else wall_thickness
        if len(pixel_points) == 2:
            cv2.line(mask, tuple(pixel_points[0]), tuple(pixel_points[1]), 255, thickness=stroke_thickness)
        else:
            cv2.polylines(mask, [pixel_points], False, 255, thickness=stroke_thickness)

    kernel_size = max(3, int(round(scale * 4)))
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    closed_mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)

    rooms: list[ExtractedRoom] = []
    component_map, components = _extract_open_space_components(closed_mask)
    component_groups: dict[int, dict[str, object]] = {}
    unresolved_indexes: set[int] = set()
    for index, label in enumerate(labels):
        seed = _resolve_room_seed(closed_mask, label=label, scale=scale, padding=padding)
        if seed is None:
            unresolved_indexes.add(index)
            continue
        seed_x, seed_y = seed
        component_id = int(component_map[seed_y, seed_x])
        component = components.get(component_id)
        if component is None or component["touches_border"]:
            unresolved_indexes.add(index)
            continue
        component_groups.setdefault(component_id, {"labels": [], "indexes": [], "seeds": []})
        component_groups[component_id]["labels"].append(label)
        component_groups[component_id]["indexes"].append(index)
        component_groups[component_id]["seeds"].append(seed)

    for component_id, payload in component_groups.items():
        if len(payload["labels"]) > 1:
            partitioned_rooms = _build_partitioned_rooms_from_component(
                component_map=component_map,
                component_id=component_id,
                labels=payload["labels"],
                seeds=payload["seeds"],
                scale=scale,
                padding=padding,
            )
            if partitioned_rooms:
                rooms.extend(partitioned_rooms)
                continue
        room = _build_room_from_component(
            component_map=component_map,
            component_id=component_id,
            labels=payload["labels"],
            scale=scale,
            padding=padding,
        )
        if room is not None:
            rooms.append(room)
            continue
        unresolved_indexes.update(payload["indexes"])

    unresolved_labels = [label for index, label in enumerate(labels) if index in unresolved_indexes]
    if unresolved_labels:
        locally_resolved_rooms, still_unresolved = _extract_local_clustered_rooms(
            closed_mask,
            unresolved_labels,
            scale=scale,
            padding=padding,
        )
        rooms.extend(locally_resolved_rooms)
        if still_unresolved:
            rooms.extend(_extract_raycast_rooms(closed_mask, still_unresolved, scale=scale, padding=padding))
    return rooms


def _extract_open_space_components(mask: np.ndarray) -> tuple[np.ndarray, dict[int, dict[str, float | bool]]]:
    open_mask = np.where(mask == 0, 255, 0).astype(np.uint8)
    count, component_map, stats, _ = cv2.connectedComponentsWithStats(open_mask, connectivity=4)
    height, width = mask.shape[:2]
    components: dict[int, dict[str, float | bool]] = {}
    for component_id in range(1, count):
        x = int(stats[component_id, cv2.CC_STAT_LEFT])
        y = int(stats[component_id, cv2.CC_STAT_TOP])
        component_width = int(stats[component_id, cv2.CC_STAT_WIDTH])
        component_height = int(stats[component_id, cv2.CC_STAT_HEIGHT])
        area = int(stats[component_id, cv2.CC_STAT_AREA])
        if area < 64:
            continue
        touches_border = (
            x <= 0
            or y <= 0
            or (x + component_width) >= width
            or (y + component_height) >= height
        )
        components[component_id] = {
            "touches_border": touches_border,
            "area_px": area,
        }
    return component_map, components


def _resolve_room_seed(
    mask: np.ndarray,
    *,
    label: ExtractedCadEntity,
    scale: float,
    padding: int,
) -> tuple[int, int] | None:
    if label.position is None:
        return None
    seed_x = int(round(float(label.position["x"]) * scale)) + padding
    seed_y = int(round(float(label.position["y"]) * scale)) + padding
    height, width = mask.shape[:2]
    seed_x = max(0, min(seed_x, width - 1))
    seed_y = max(0, min(seed_y, height - 1))
    if mask[seed_y, seed_x] == 0:
        return seed_x, seed_y
    return _find_nearest_open(mask, seed_x=seed_x, seed_y=seed_y, radius=max(12, int(width * 0.02)))


def _build_room_from_component(
    *,
    component_map: np.ndarray,
    component_id: int,
    labels: list[ExtractedCadEntity],
    scale: float,
    padding: int,
    pixel_offset: tuple[int, int] = (0, 0),
) -> ExtractedRoom | None:
    component_mask = np.where(component_map == component_id, 255, 0).astype(np.uint8)
    return _build_room_from_binary_mask(
        binary_mask=component_mask,
        labels=labels,
        scale=scale,
        padding=padding,
        measurement_source="label_region_fill",
        pixel_offset=pixel_offset,
    )


def _build_partitioned_rooms_from_component(
    *,
    component_map: np.ndarray,
    component_id: int,
    labels: list[ExtractedCadEntity],
    seeds: list[tuple[int, int]],
    scale: float,
    padding: int,
    pixel_offset: tuple[int, int] = (0, 0),
) -> list[ExtractedRoom]:
    component_mask = component_map == component_id
    ys, xs = np.nonzero(component_mask)
    if len(xs) == 0 or len(labels) != len(seeds):
        return []

    best_index = np.full(len(xs), -1, dtype=np.int32)
    best_distance = np.full(len(xs), np.inf, dtype=np.float32)
    for label_index, (seed_x, seed_y) in enumerate(seeds):
        distances = ((xs - seed_x) ** 2) + ((ys - seed_y) ** 2)
        better = distances < best_distance
        best_distance[better] = distances[better]
        best_index[better] = label_index

    rooms: list[ExtractedRoom] = []
    for label_index, label in enumerate(labels):
        assigned = best_index == label_index
        if int(np.count_nonzero(assigned)) < 64:
            continue
        label_mask = np.zeros(component_map.shape, dtype=np.uint8)
        label_mask[ys[assigned], xs[assigned]] = 255
        room = _build_room_from_binary_mask(
            binary_mask=label_mask,
            labels=[label],
            scale=scale,
            padding=padding,
            measurement_source="label_region_partition",
            pixel_offset=pixel_offset,
        )
        if room is not None:
            rooms.append(room)
    return rooms


def _build_room_from_binary_mask(
    *,
    binary_mask: np.ndarray,
    labels: list[ExtractedCadEntity],
    scale: float,
    padding: int,
    measurement_source: str,
    pixel_offset: tuple[int, int] = (0, 0),
) -> ExtractedRoom | None:
    contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) < 64:
        return None

    perimeter = cv2.arcLength(contour, True)
    epsilon = max(2.0, perimeter * 0.0025)
    simplified = cv2.approxPolyDP(contour, epsilon, True)
    world_points = [
        (
            (float(point[0][0] + pixel_offset[0]) - padding) / scale,
            (float(point[0][1] + pixel_offset[1]) - padding) / scale,
        )
        for point in simplified
    ]
    if len(world_points) < 3:
        return None
    if world_points[0] != world_points[-1]:
        world_points.append(world_points[0])

    polygon = Polygon(world_points)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty:
        return None
    if polygon.geom_type == "MultiPolygon":
        polygon = max(polygon.geoms, key=lambda candidate: float(candidate.area))
    polygon = polygon.simplify(max(0.5, 1.0 / scale), preserve_topology=True)
    if polygon.is_empty or polygon.area <= 1.0:
        return None

    room = _build_room_from_polygon(polygon, labels)
    return ExtractedRoom(
        name=room.name,
        polygon=room.polygon,
        bbox=room.bbox,
        centroid=room.centroid,
        width=room.width,
        height=room.height,
        area=room.area,
        measurement_source=measurement_source,
    )


def _extract_local_clustered_rooms(
    mask: np.ndarray,
    labels: list[ExtractedCadEntity],
    *,
    scale: float,
    padding: int,
) -> tuple[list[ExtractedRoom], list[ExtractedCadEntity]]:
    candidates = _collect_raycast_candidates(mask, labels, scale=scale, padding=padding)
    if not candidates:
        return [], labels

    clusters = _cluster_raycast_candidates(candidates, margin=max(18, int(round(scale * 12))))
    rooms: list[ExtractedRoom] = []
    resolved_indexes: set[int] = set()

    for cluster in clusters:
        crop_margin = max(18, int(round(scale * 10)))
        crop_x1 = max(0, min(candidate["bbox_px"][0] for candidate in cluster) - crop_margin)
        crop_y1 = max(0, min(candidate["bbox_px"][1] for candidate in cluster) - crop_margin)
        crop_x2 = min(mask.shape[1] - 1, max(candidate["bbox_px"][2] for candidate in cluster) + crop_margin)
        crop_y2 = min(mask.shape[0] - 1, max(candidate["bbox_px"][3] for candidate in cluster) + crop_margin)
        crop_mask = mask[crop_y1:crop_y2 + 1, crop_x1:crop_x2 + 1].copy()
        crop_mask[0, :] = 255
        crop_mask[-1, :] = 255
        crop_mask[:, 0] = 255
        crop_mask[:, -1] = 255

        crop_component_map, crop_components = _extract_open_space_components(crop_mask)
        crop_groups: dict[int, dict[str, object]] = {}
        unresolved_cluster_indexes: set[int] = set()
        for candidate in cluster:
            local_seed = (candidate["seed"][0] - crop_x1, candidate["seed"][1] - crop_y1)
            local_x = max(0, min(local_seed[0], crop_mask.shape[1] - 1))
            local_y = max(0, min(local_seed[1], crop_mask.shape[0] - 1))
            component_id = int(crop_component_map[local_y, local_x])
            component = crop_components.get(component_id)
            if component is None:
                unresolved_cluster_indexes.add(candidate["index"])
                continue
            crop_groups.setdefault(component_id, {"labels": [], "indexes": [], "seeds": []})
            crop_groups[component_id]["labels"].append(candidate["label"])
            crop_groups[component_id]["indexes"].append(candidate["index"])
            crop_groups[component_id]["seeds"].append((local_x, local_y))

        for component_id, payload in crop_groups.items():
            resolved: list[ExtractedRoom] = []
            if len(payload["labels"]) > 1:
                resolved = _build_partitioned_rooms_from_component(
                    component_map=crop_component_map,
                    component_id=component_id,
                    labels=payload["labels"],
                    seeds=payload["seeds"],
                    scale=scale,
                    padding=padding,
                    pixel_offset=(crop_x1, crop_y1),
                )
            if not resolved:
                single_room = _build_room_from_component(
                    component_map=crop_component_map,
                    component_id=component_id,
                    labels=payload["labels"],
                    scale=scale,
                    padding=padding,
                    pixel_offset=(crop_x1, crop_y1),
                )
                if single_room is not None:
                    resolved = [single_room]
            if resolved:
                rooms.extend(resolved)
                resolved_indexes.update(payload["indexes"])
                continue
            unresolved_cluster_indexes.update(payload["indexes"])

    unresolved = [label for index, label in enumerate(labels) if index not in resolved_indexes]
    return rooms, unresolved


def _collect_raycast_candidates(
    mask: np.ndarray,
    labels: list[ExtractedCadEntity],
    *,
    scale: float,
    padding: int,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for index, label in enumerate(labels):
        seed = _resolve_room_seed(mask, label=label, scale=scale, padding=padding)
        if seed is None:
            continue
        bbox_px = _raycast_room_bbox(mask, seed_x=seed[0], seed_y=seed[1])
        if bbox_px is None:
            continue
        candidates.append({"index": index, "label": label, "seed": seed, "bbox_px": bbox_px})
    return candidates


def _cluster_raycast_candidates(candidates: list[dict[str, object]], *, margin: int) -> list[list[dict[str, object]]]:
    if not candidates:
        return []

    parents = list(range(len(candidates)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    for left in range(len(candidates)):
        for right in range(left + 1, len(candidates)):
            if _bbox_tuple_overlap(candidates[left]["bbox_px"], candidates[right]["bbox_px"], margin=margin):
                union(left, right)

    grouped: dict[int, list[dict[str, object]]] = {}
    for index, candidate in enumerate(candidates):
        grouped.setdefault(find(index), []).append(candidate)
    return list(grouped.values())


def _bbox_tuple_overlap(left: tuple[int, int, int, int], right: tuple[int, int, int, int], *, margin: int) -> bool:
    return not (
        (left[2] + margin) < right[0]
        or (right[2] + margin) < left[0]
        or (left[3] + margin) < right[1]
        or (right[3] + margin) < left[1]
    )


def _extract_raycast_rooms(
    mask: np.ndarray,
    labels: list[ExtractedCadEntity],
    *,
    scale: float,
    padding: int,
) -> list[ExtractedRoom]:
    grouped_by_signature: dict[tuple[int, int, int, int], dict[str, object]] = {}
    for label in labels:
        seed = _resolve_room_seed(mask, label=label, scale=scale, padding=padding)
        if seed is None:
            continue
        seed_x, seed_y = seed
        bbox_px = _raycast_room_bbox(mask, seed_x=seed_x, seed_y=seed_y)
        if bbox_px is None:
            continue
        signature = tuple(int(round(value / max(1.0, scale * 2.0))) for value in bbox_px)
        grouped_by_signature.setdefault(signature, {"labels": [], "bbox_px": bbox_px})
        grouped_by_signature[signature]["labels"].append(label)

    rooms: list[ExtractedRoom] = []
    for payload in grouped_by_signature.values():
        room = _build_room_from_raycast_bbox(
            bbox_px=payload["bbox_px"],
            labels=payload["labels"],
            scale=scale,
            padding=padding,
        )
        if room is not None:
            rooms.append(room)
    return rooms


def _raycast_room_bbox(mask: np.ndarray, *, seed_x: int, seed_y: int) -> tuple[int, int, int, int] | None:
    height, width = mask.shape[:2]
    seed_x = max(0, min(seed_x, width - 1))
    seed_y = max(0, min(seed_y, height - 1))
    if mask[seed_y, seed_x] != 0:
        seed = _find_nearest_open(mask, seed_x=seed_x, seed_y=seed_y, radius=max(12, int(width * 0.02)))
        if seed is None:
            return None
        seed_x, seed_y = seed

    left = _scan_until_block(mask, start_x=seed_x, start_y=seed_y, step_x=-1, step_y=0)
    right = _scan_until_block(mask, start_x=seed_x, start_y=seed_y, step_x=1, step_y=0)
    top = _scan_until_block(mask, start_x=seed_x, start_y=seed_y, step_x=0, step_y=-1)
    bottom = _scan_until_block(mask, start_x=seed_x, start_y=seed_y, step_x=0, step_y=1)
    if None in {left, right, top, bottom}:
        return None
    if (right - left) < 8 or (bottom - top) < 8:
        return None
    return int(left), int(top), int(right), int(bottom)


def _scan_until_block(mask: np.ndarray, *, start_x: int, start_y: int, step_x: int, step_y: int) -> int | None:
    height, width = mask.shape[:2]
    x = start_x
    y = start_y
    last_open = x if step_y == 0 else y
    while 0 <= x < width and 0 <= y < height:
        if mask[y, x] != 0:
            return last_open
        last_open = x if step_y == 0 else y
        x += step_x
        y += step_y
    return None


def _find_nearest_open(mask: np.ndarray, *, seed_x: int, seed_y: int, radius: int) -> tuple[int, int] | None:
    height, width = mask.shape[:2]
    for current_radius in range(1, radius + 1):
        for dx in range(-current_radius, current_radius + 1):
            for dy in range(-current_radius, current_radius + 1):
                x = seed_x + dx
                y = seed_y + dy
                if 0 <= x < width and 0 <= y < height and mask[y, x] == 0:
                    return x, y
    return None


def _build_room_from_raycast_bbox(
    *,
    bbox_px: tuple[int, int, int, int],
    labels: list[ExtractedCadEntity],
    scale: float,
    padding: int,
) -> ExtractedRoom | None:
    x1_px, y1_px, x2_px, y2_px = bbox_px
    x1 = (float(x1_px) - padding) / scale
    y1 = (float(y1_px) - padding) / scale
    x2 = (float(x2_px) - padding) / scale
    y2 = (float(y2_px) - padding) / scale
    if x2 <= x1 or y2 <= y1:
        return None
    polygon = Polygon([(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)])
    room = _build_room_from_polygon(polygon, labels)
    return ExtractedRoom(
        name=room.name,
        polygon=room.polygon,
        bbox=room.bbox,
        centroid=room.centroid,
        width=room.width,
        height=room.height,
        area=room.area,
        measurement_source="label_raycast",
    )


def _merge_rooms(primary: list[ExtractedRoom], secondary: list[ExtractedRoom]) -> list[ExtractedRoom]:
    merged = list(primary)
    for candidate in secondary:
        duplicate = next(
            (
                existing
                for existing in merged
                if abs(existing.centroid["x"] - candidate.centroid["x"]) <= 6.0
                and abs(existing.centroid["y"] - candidate.centroid["y"]) <= 6.0
            ),
            None,
        )
        if duplicate is None:
            merged.append(candidate)
    return merged


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
        origin=entity.origin,
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


def _build_view(
    role: str,
    entities: list[ExtractedCadEntity],
    *,
    measurements: ExtractedMeasurements | None = None,
    rooms: list[ExtractedRoom] | None = None,
    support_entities: list[ExtractedCadEntity] | None = None,
) -> dict:
    if not entities:
        return {
            "role": role,
            "bbox": None,
            "summary": {"entity_count": 0, "line_count": 0, "polyline_count": 0, "text_count": 0},
            "entities": [],
            "support_entities": [],
            "measurements": None,
            "rooms": [],
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
                "origin": entity.origin,
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
    rooms_payload = []
    for room in rooms or []:
        rooms_payload.append(
            {
                "name": room.name,
                "polygon": list(room.polygon),
                "bbox": room.bbox,
                "centroid": room.centroid,
                "width": room.width,
                "height": room.height,
                "area": room.area,
                "measurement_source": room.measurement_source,
            }
        )
    support_serialized = []
    for entity in support_entities or []:
        support_serialized.append(
            {
                "type": entity.type,
                "layer": entity.layer,
                "origin": entity.origin,
                "start": entity.start,
                "end": entity.end,
                "points": list(entity.points),
                "text": entity.text,
                "position": entity.position,
                "bbox": entity.bbox,
            }
        )
    return {
        "role": role,
        "bbox": bbox,
        "summary": summary,
        "entities": serialized,
        "support_entities": support_serialized,
        "measurements": measurements_payload,
        "rooms": rooms_payload,
    }


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
