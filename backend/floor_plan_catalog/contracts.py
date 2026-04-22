from __future__ import annotations

from pydantic import BaseModel, Field


class CatalogReadiness(BaseModel):
    status: str
    issues: list[str] = Field(default_factory=list)


class CatalogBBox(BaseModel):
    x1: float = 0.0
    y1: float = 0.0
    x2: float = 0.0
    y2: float = 0.0
    width: float
    height: float


class CatalogPoint(BaseModel):
    x: float
    y: float


class CatalogRoom(BaseModel):
    name: str
    polygon: list[CatalogPoint] = Field(default_factory=list)
    bbox: CatalogBBox
    centroid: CatalogPoint
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


class CatalogRoomTopology(BaseModel):
    room_id: str
    name: str
    category: str
    polygon: list[CatalogPoint] = Field(default_factory=list)
    bbox: CatalogBBox
    centroid: CatalogPoint
    width: float
    height: float
    area: float
    measurement_source: str
    adjacent_room_ids: list[str] = Field(default_factory=list)
    is_exterior_touching: bool = False
    issues: list[str] = Field(default_factory=list)


class TopologyReadiness(BaseModel):
    status: str
    issues: list[str] = Field(default_factory=list)


class FloorPlanTopologyV1(BaseModel):
    floor_plan_id: str
    name: str
    canonical_unit: str
    footprint_bbox: CatalogBBox
    rooms: list[CatalogRoomTopology] = Field(default_factory=list)
    topology_readiness: TopologyReadiness
    topology_issues: list[str] = Field(default_factory=list)
