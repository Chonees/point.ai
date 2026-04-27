from typing import Optional

from pydantic import BaseModel, Field


class ParseStructureRequest(BaseModel):
    plan: Optional[dict] = None
    structure: Optional[dict] = None
    image: Optional[str] = None
    scale_hint: Optional[float] = None
    model_variant: Optional[str] = None


class ParseStructureResponse(BaseModel):
    structure: dict
    preview_url: Optional[str] = None
    artifact_urls: dict = Field(default_factory=dict)
    quality_metrics: dict = Field(default_factory=dict)
    needs_review: bool = False
    review_flags: list[str] = Field(default_factory=list)


class GenerateStructureRequest(BaseModel):
    plan: Optional[dict] = None
    structure: Optional[dict] = None
    image: Optional[str] = None
    scale_hint: Optional[float] = None
    model_variant: Optional[str] = None


class GenerateStructureResponse(BaseModel):
    dxf_url: str
    preview_url: Optional[str] = None
    artifact_urls: dict = Field(default_factory=dict)
    structure: dict
    needs_review: bool = False
    scale_status: str
    quality_metrics: dict = Field(default_factory=dict)
    review_flags: list[str] = Field(default_factory=list)
