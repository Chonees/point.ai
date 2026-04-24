from __future__ import annotations

from collections import Counter
from pathlib import Path

import ezdxf
from pydantic import BaseModel, Field


class FloorPlanSourceAudit(BaseModel):
    source_layers: list[str] = Field(default_factory=list)
    entity_types: dict[str, int] = Field(default_factory=dict)
    block_refs: dict[str, int] = Field(default_factory=dict)
    room_labels: list[str] = Field(default_factory=list)


def audit_floor_plan_source(path: Path) -> FloorPlanSourceAudit:
    doc = ezdxf.readfile(str(path))
    msp = doc.modelspace()

    layer_counts = Counter()
    type_counts = Counter()
    block_refs = Counter()
    room_labels: list[str] = []

    for entity in msp:
        layer = str(getattr(entity.dxf, "layer", "0") or "0")
        layer_counts[layer] += 1
        type_counts[entity.dxftype()] += 1

        if entity.dxftype() == "INSERT":
            block_refs[str(entity.dxf.name)] += 1

        if entity.dxftype() in {"TEXT", "MTEXT"}:
            text = entity.plain_text() if hasattr(entity, "plain_text") else str(entity.dxf.text)
            normalized = " ".join(text.upper().split())
            if "ROOM" in layer.upper() and normalized:
                room_labels.append(normalized)

    return FloorPlanSourceAudit(
        source_layers=sorted(layer_counts.keys()),
        entity_types=dict(type_counts),
        block_refs=dict(block_refs),
        room_labels=room_labels,
    )
