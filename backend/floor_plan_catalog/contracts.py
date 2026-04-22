from __future__ import annotations

from pydantic import BaseModel, Field


class CatalogReadiness(BaseModel):
    status: str
    issues: list[str] = Field(default_factory=list)


class CatalogBBox(BaseModel):
    width: float
    height: float


class CatalogRoom(BaseModel):
    name: str
    width: float
    height: float
    area: float
    measurement_source: str


class FloorPlanCatalogSeed(BaseModel):
    floor_plan_id: str
    name: str
    source_path: str
    canonical_unit: str
    footprint_bbox: CatalogBBox
    rooms: list[CatalogRoom] = Field(default_factory=list)
    source_layers: list[str] = Field(default_factory=list)
    block_refs: list[str] = Field(default_factory=list)
    readiness: CatalogReadiness
