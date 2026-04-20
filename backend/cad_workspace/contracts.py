from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CadWorkspaceBBoxResponse(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    width: float
    height: float


class CadWorkspaceLineEntityResponse(BaseModel):
    type: str
    layer: str
    start: Optional[dict] = None
    end: Optional[dict] = None
    points: list[dict] = Field(default_factory=list)
    text: Optional[str] = None
    position: Optional[dict] = None
    bbox: CadWorkspaceBBoxResponse


class CadWorkspaceViewSummaryResponse(BaseModel):
    entity_count: int
    line_count: int
    polyline_count: int
    text_count: int


class CadWorkspaceMeasurementsResponse(BaseModel):
    width: float
    height: float
    source: str


class CadWorkspaceViewResponse(BaseModel):
    role: str
    bbox: Optional[CadWorkspaceBBoxResponse] = None
    summary: CadWorkspaceViewSummaryResponse
    entities: list[CadWorkspaceLineEntityResponse] = Field(default_factory=list)
    measurements: Optional[CadWorkspaceMeasurementsResponse] = None


class CadWorkspaceSideBySideResponse(BaseModel):
    canonical_unit: str
    gap: float
    floor_width: float = 0.0
    site_width: float = 0.0
    max_height: float = 0.0


class CadWorkspaceFitSummaryResponse(BaseModel):
    comparison_unit: str
    basis: str
    footprint_bbox: Optional[CadWorkspaceBBoxResponse] = None
    property_bbox: Optional[CadWorkspaceBBoxResponse] = None
    buildable_bbox: Optional[CadWorkspaceBBoxResponse] = None
    buildable_polygon: Optional[list[dict]] = None
    width_delta: Optional[float] = None
    height_delta: Optional[float] = None
    fits_within_buildable_bbox: Optional[bool] = None
    fits_within_buildable_polygon: Optional[bool] = None


class CadWorkspaceExtractResponse(BaseModel):
    analysis_id: str
    source_name: str
    source_format: str
    canonical_unit: str
    conversion_status: str
    conversion_note: Optional[str] = None
    floor_plan: CadWorkspaceViewResponse
    site_plan: CadWorkspaceViewResponse
    side_by_side: CadWorkspaceSideBySideResponse
    fit_summary: Optional[CadWorkspaceFitSummaryResponse] = None
    warnings: list[str] = Field(default_factory=list)
