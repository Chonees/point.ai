from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


SITE_FIT_CONTRACT_VERSION = "site_fit_contract_v1"


class SiteFitBaseRequest(BaseModel):
    plan: Optional[dict] = None
    structure: Optional[dict] = None
    site_constraints: dict
    design_locks: dict = Field(default_factory=dict)
    jurisdiction: Optional[str] = None
    ruleset_version: str = SITE_FIT_CONTRACT_VERSION


class SiteFitAnalyzeRequest(SiteFitBaseRequest):
    pass


class SiteFitApplyRequest(SiteFitBaseRequest):
    candidate_id: str


class SiteFitIsolationResponse(BaseModel):
    pipeline: str = "site_fit"
    separate_contracts: bool = True
    touched_existing_parse_generate_pipeline: bool = False


class SiteFitPlanSummaryResponse(BaseModel):
    source_kind: str
    canonical_unit: Optional[str] = None
    room_count: int = 0
    wall_count: int = 0
    opening_count: int = 0
    footprint_bbox: Optional[dict] = None


class SiteFitRegistrationTransformResponse(BaseModel):
    scale: float = 1.0
    rotation_degrees: float = 0.0
    translate_x: float = 0.0
    translate_y: float = 0.0


class SiteFitRegistrationSummaryResponse(BaseModel):
    status: str
    canonical_unit: Optional[str] = None
    scale_locked: bool = True
    transform: SiteFitRegistrationTransformResponse = Field(default_factory=SiteFitRegistrationTransformResponse)
    registered_plan_bbox: Optional[dict] = None
    warnings: list[str] = Field(default_factory=list)


class SiteFitComplianceSummaryResponse(BaseModel):
    status: str
    checked_rule_ids: list[str] = Field(default_factory=list)
    violations: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SiteFitCandidateResponse(BaseModel):
    candidate_id: str
    strategy: str
    summary: str
    fit_status: str
    change_count: int = 0
    score: float = 0.0
    changes: list[dict] = Field(default_factory=list)


class SiteFitAnalysisResponse(BaseModel):
    analysis_id: str
    contract_version: str = SITE_FIT_CONTRACT_VERSION
    status: str
    isolation: SiteFitIsolationResponse
    plan_summary: SiteFitPlanSummaryResponse
    registration_summary: SiteFitRegistrationSummaryResponse
    site_summary: dict = Field(default_factory=dict)
    compliance_summary: SiteFitComplianceSummaryResponse
    warnings: list[str] = Field(default_factory=list)


class SiteFitProposeResponse(BaseModel):
    analysis_id: str
    contract_version: str = SITE_FIT_CONTRACT_VERSION
    status: str
    isolation: SiteFitIsolationResponse
    plan_summary: SiteFitPlanSummaryResponse
    registration_summary: SiteFitRegistrationSummaryResponse
    site_summary: dict = Field(default_factory=dict)
    compliance_summary: SiteFitComplianceSummaryResponse
    candidates: list[SiteFitCandidateResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SiteFitApplyResponse(BaseModel):
    analysis_id: str
    contract_version: str = SITE_FIT_CONTRACT_VERSION
    candidate_id: str
    apply_status: str
    isolation: SiteFitIsolationResponse
    registration_summary: SiteFitRegistrationSummaryResponse
    compliance_summary: SiteFitComplianceSummaryResponse
    applied_plan: dict = Field(default_factory=dict)
    change_set: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SiteFitValidateResponse(BaseModel):
    analysis_id: str
    contract_version: str = SITE_FIT_CONTRACT_VERSION
    status: str
    isolation: SiteFitIsolationResponse
    plan_summary: SiteFitPlanSummaryResponse
    registration_summary: SiteFitRegistrationSummaryResponse
    site_summary: dict = Field(default_factory=dict)
    compliance_summary: SiteFitComplianceSummaryResponse
    warnings: list[str] = Field(default_factory=list)
