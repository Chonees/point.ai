from typing import Optional

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    image: str  # base64 encoded image


class AnalyzeResponse(BaseModel):
    description: str


class GenerateRequest(BaseModel):
    prompt: str
    image: Optional[str] = None  # base64 encoded image


class GenerateResponse(BaseModel):
    dxf_url: str
    plan: dict


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
    annotations: Optional[list] = None  # user-drawn walls/doors/windows


class GenerateStructureResponse(BaseModel):
    dxf_url: str
    preview_url: Optional[str] = None
    artifact_urls: dict = Field(default_factory=dict)
    structure: dict
    needs_review: bool = False
    scale_status: str
    quality_metrics: dict = Field(default_factory=dict)
    review_flags: list[str] = Field(default_factory=list)
