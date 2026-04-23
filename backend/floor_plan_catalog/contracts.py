from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field


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


class CatalogCadTrace(BaseModel):
    trace_id: str
    trace_kind: str = "wall"
    type: str
    layer: str
    start: CatalogPoint | None = None
    end: CatalogPoint | None = None
    points: list[CatalogPoint] = Field(default_factory=list)
    bbox: CatalogBBox


CatalogWallTrace = CatalogCadTrace


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
    cad_traces: list[CatalogCadTrace] = Field(
        default_factory=list,
        validation_alias=AliasChoices("cad_traces", "wall_traces"),
    )
    source_layers: list[str] = Field(default_factory=list)
    block_refs: list[str] = Field(default_factory=list)
    readiness: CatalogReadiness

    @property
    def wall_traces(self) -> list[CatalogCadTrace]:
        return [trace for trace in self.cad_traces if trace.trace_kind == "wall"]

    @property
    def door_traces(self) -> list[CatalogCadTrace]:
        return [trace for trace in self.cad_traces if trace.trace_kind == "door"]

    @property
    def window_traces(self) -> list[CatalogCadTrace]:
        return [trace for trace in self.cad_traces if trace.trace_kind == "window"]


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
    opening_adjacent_room_ids: list[str] = Field(default_factory=list)
    heuristic_adjacent_room_ids: list[str] = Field(default_factory=list)
    owned_wall_ids: list[str] = Field(default_factory=list)
    shared_wall_ids: list[str] = Field(default_factory=list)
    exterior_wall_ids: list[str] = Field(default_factory=list)
    is_exterior_touching: bool = False
    isolation_status: str = "connected"
    is_wet_zone: bool = False
    is_core: bool = False
    mutability: str = "unknown"
    min_width: float | None = None
    min_height: float | None = None
    min_area: float | None = None
    constraint_reasons: list[str] = Field(default_factory=list)
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


class CatalogWallBoundary(BaseModel):
    wall_id: str
    start: CatalogPoint
    end: CatalogPoint
    orientation: str
    length: float
    is_exterior: bool
    room_ids: list[str] = Field(default_factory=list)
    boundary_kind: str = "unknown"
    owner_room_ids: list[str] = Field(default_factory=list)
    provenance: str = "unknown"
    confidence: str = "unverified"
    trace_support_status: str = "not_evaluated"
    trace_support_ids: list[str] = Field(default_factory=list)
    trace_support_gap: float | None = None
    movable: bool = False
    mutability: str = "unknown"
    structural_unknown: bool = False
    constraint_reasons: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class WallGraphReadiness(BaseModel):
    status: str
    issues: list[str] = Field(default_factory=list)


class FloorPlanWallGraphV1(BaseModel):
    floor_plan_id: str
    name: str
    canonical_unit: str
    footprint_bbox: CatalogBBox
    walls: list[CatalogWallBoundary] = Field(default_factory=list)
    wall_graph_readiness: WallGraphReadiness
    wall_graph_issues: list[str] = Field(default_factory=list)


class CatalogOpening(BaseModel):
    opening_id: str
    opening_kind: str
    host_wall_id: str | None = None
    owner_room_ids: list[str] = Field(default_factory=list)
    connected_room_ids: list[str] = Field(default_factory=list)
    trace_ids: list[str] = Field(default_factory=list)
    orientation: str
    start: CatalogPoint
    end: CatalogPoint
    offset: float
    span: float
    confidence: str = "unverified"
    rehost_required: bool = False
    rehostable: bool = False
    constraint_reasons: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class OpeningGraphReadiness(BaseModel):
    status: str
    issues: list[str] = Field(default_factory=list)


class FloorPlanOpeningGraphV1(BaseModel):
    floor_plan_id: str
    name: str
    canonical_unit: str
    openings: list[CatalogOpening] = Field(default_factory=list)
    opening_graph_readiness: OpeningGraphReadiness
    opening_graph_issues: list[str] = Field(default_factory=list)


class CatalogBoundaryNode(BaseModel):
    node_id: str
    point: CatalogPoint
    node_kind: str = "corner"
    incident_boundary_ids: list[str] = Field(default_factory=list)


class CatalogBoundarySegment(BaseModel):
    boundary_id: str
    start_node_id: str
    end_node_id: str
    start: CatalogPoint
    end: CatalogPoint
    orientation: str
    length: float
    source_trace_ids: list[str] = Field(default_factory=list)
    boundary_kind: str = "unknown"
    owner_room_ids: list[str] = Field(default_factory=list)
    companion_boundary_id: str | None = None
    boundary_family_id: str | None = None
    family_role: str = "unknown"
    duplicate_of_boundary_id: str | None = None
    opening_ids: list[str] = Field(default_factory=list)
    confidence: str = "unverified"
    movable: bool = False
    mutability: str = "unknown"
    structural_unknown: bool = False
    constraint_reasons: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class FloorPlanBoundaryGraphV1(BaseModel):
    floor_plan_id: str
    name: str
    canonical_unit: str
    nodes: list[CatalogBoundaryNode] = Field(default_factory=list)
    boundaries: list[CatalogBoundarySegment] = Field(default_factory=list)
    boundary_graph_readiness: CatalogReadiness
    boundary_graph_issues: list[str] = Field(default_factory=list)
