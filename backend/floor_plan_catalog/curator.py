from __future__ import annotations

import hashlib
import re
from pathlib import Path

from backend.cad_workspace.extractor import extract_cad_file

from .audit import audit_floor_plan_source
from .contracts import CatalogBBox, CatalogCadTrace, CatalogPoint, CatalogReadiness, CatalogRoom, FloorPlanCatalogSeed


def curate_floor_plan_seed(
    path: Path,
    *,
    floor_plan_id: str | None = None,
    name: str | None = None,
) -> FloorPlanCatalogSeed:
    extracted = extract_cad_file(path, source_name=path.name)
    audit = audit_floor_plan_source(path)
    floor = extracted["floor_plan"]

    rooms = [
        CatalogRoom(
            name=room["name"],
            polygon=[CatalogPoint(x=point["x"], y=point["y"]) for point in room.get("polygon", [])],
            bbox=_to_catalog_bbox(room.get("bbox")),
            centroid=CatalogPoint(x=room["centroid"]["x"], y=room["centroid"]["y"]),
            width=room["width"],
            height=room["height"],
            area=room["area"],
            measurement_source=room["measurement_source"],
        )
        for room in floor.get("rooms", [])
    ]
    support_entities = floor.get("support_entities") or floor.get("entities", [])
    cad_traces = [
        _to_catalog_trace(entity, index)
        for index, entity in enumerate(support_entities)
        if _classify_trace_kind(entity) is not None
    ]

    bbox = floor.get("bbox") or {"width": 0.0, "height": 0.0}
    return FloorPlanCatalogSeed(
        floor_plan_id=floor_plan_id or _slugify(path.stem),
        name=name or path.stem,
        source_path=str(path),
        canonical_unit=extracted["canonical_unit"],
        footprint_bbox=_to_catalog_bbox(bbox),
        rooms=rooms,
        cad_traces=cad_traces,
        source_layers=audit.source_layers,
        block_refs=sorted(audit.block_refs.keys()),
        readiness=_build_readiness(rooms=rooms, warnings=extracted.get("warnings", [])),
    )


def _build_readiness(*, rooms: list[CatalogRoom], warnings: list[str]) -> CatalogReadiness:
    ignored_warning_prefixes = (
        "Only one spatial view cluster was detected",
        "No separate site-plan cluster was detected",
        "Buildable-fit summary is unavailable because no recognizable buildable envelope layer was extracted.",
        "Floor-plan wall geometry was normalized from dimension annotations before side-by-side comparison.",
        "Floor and site views were separated by CAD layers and semantic role hints because spatial clustering was ambiguous.",
    )
    issues = [
        warning
        for warning in warnings
        if not any(warning.startswith(prefix) for prefix in ignored_warning_prefixes)
    ]
    if not rooms:
        issues.append("No rooms were extracted.")
    if len(rooms) < 2:
        issues.append("Room coverage is too low for a trusted catalog entry.")
    if any(_looks_like_aggregate_room_label(room.name) for room in rooms):
        issues.append("Aggregate room labels suggest unresolved room segmentation.")
    status = "ready_for_catalog" if not issues else "needs_manual_review"
    return CatalogReadiness(status=status, issues=issues)


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "floor-plan"


def _classify_trace_kind(entity: dict) -> str | None:
    layer = (entity.get("layer") or "").upper()
    entity_type = entity.get("type")
    if entity_type not in {"line", "polyline"}:
        return None
    if "WALL" in layer:
        return "wall"
    if "DOOR" in layer:
        return "door"
    if layer in {"WIN", "WINS"} or "WIND" in layer or "WINDOW" in layer:
        return "window"
    return None


def _to_catalog_trace(entity: dict, index: int) -> CatalogCadTrace:
    start = entity.get("start")
    end = entity.get("end")
    points = entity.get("points") or []
    signature = "|".join(
        [
            entity.get("type") or "",
            entity.get("layer") or "",
            str(start or ""),
            str(end or ""),
            str(points),
        ]
    )
    trace_id = hashlib.sha1(f"{index}|{signature}".encode("utf-8")).hexdigest()[:12]
    return CatalogCadTrace(
        trace_id=f"trace-{trace_id}",
        trace_kind=_classify_trace_kind(entity) or "wall",
        type=entity.get("type") or "unknown",
        layer=entity.get("layer") or "0",
        start=_to_catalog_point(start),
        end=_to_catalog_point(end),
        points=[CatalogPoint(x=point["x"], y=point["y"]) for point in points],
        bbox=_to_catalog_bbox(entity.get("bbox")),
    )


def _to_catalog_point(payload: dict | None) -> CatalogPoint | None:
    if not payload:
        return None
    return CatalogPoint(x=payload.get("x", 0.0), y=payload.get("y", 0.0))


def _to_catalog_bbox(payload: dict | None) -> CatalogBBox:
    payload = payload or {}
    return CatalogBBox(
        x1=payload.get("x1", 0.0),
        y1=payload.get("y1", 0.0),
        x2=payload.get("x2", 0.0),
        y2=payload.get("y2", 0.0),
        width=payload.get("width", 0.0),
        height=payload.get("height", 0.0),
    )


def _looks_like_aggregate_room_label(name: str) -> bool:
    upper = name.upper()
    room_keywords = (
        "BEDROOM",
        "BATH",
        "KITCHEN",
        "LIVING",
        "DINING",
        "PANTRY",
        "ENTRY",
        "UTILITY",
        "PATIO",
        "CLOSET",
        "GARAGE",
        "PORCH",
    )
    matched = sum(1 for keyword in room_keywords if keyword in upper)
    return matched >= 4
