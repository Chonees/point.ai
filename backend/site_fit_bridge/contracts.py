from pydantic import BaseModel, Field

from ..cad_workspace.contracts import CadWorkspaceExtractResponse
from ..site_fit.contracts import SiteFitApplyResponse, SiteFitProposeResponse


class SiteFitBridgeApplyRequest(BaseModel):
    plan_id: str
    site_constraints: dict
    candidate_id: str
    cad_analysis_id: str


class SiteFitBridgeProposeResponse(BaseModel):
    pipeline: str = "site_fit_bridge_mvp_v1"
    scope: str = "seminole-2000-only"
    plan_id: str
    plan_name: str
    cad_analysis: CadWorkspaceExtractResponse
    site_constraints: dict = Field(default_factory=dict)
    proposal: SiteFitProposeResponse
    warnings: list[str] = Field(default_factory=list)


class SiteFitBridgeApplyResponse(BaseModel):
    pipeline: str = "site_fit_bridge_mvp_v1"
    scope: str = "seminole-2000-only"
    plan_id: str
    plan_name: str
    apply_id: str
    export_url: str
    apply: SiteFitApplyResponse
    warnings: list[str] = Field(default_factory=list)
