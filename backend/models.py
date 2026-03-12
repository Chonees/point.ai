from pydantic import BaseModel
from typing import Optional


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
