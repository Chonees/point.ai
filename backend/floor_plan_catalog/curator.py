from __future__ import annotations

import re
from pathlib import Path

from backend.cad_workspace.extractor import extract_cad_file

from .audit import audit_floor_plan_source
from .contracts import CatalogBBox, CatalogReadiness, CatalogRoom, FloorPlanCatalogSeed


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
            width=room["width"],
            height=room["height"],
            area=room["area"],
            measurement_source=room["measurement_source"],
        )
        for room in floor.get("rooms", [])
    ]

    bbox = floor.get("bbox") or {"width": 0.0, "height": 0.0}
    return FloorPlanCatalogSeed(
        floor_plan_id=floor_plan_id or _slugify(path.stem),
        name=name or path.stem,
        source_path=str(path),
        canonical_unit=extracted["canonical_unit"],
        footprint_bbox=CatalogBBox(width=bbox["width"], height=bbox["height"]),
        rooms=rooms,
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
    status = "ready_for_catalog" if not issues else "needs_manual_review"
    return CatalogReadiness(status=status, issues=issues)


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "floor-plan"
