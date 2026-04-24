import type { CadWorkspaceExtractResult } from '../cad/contracts'

export interface SiteFitBridgeProposalResult {
  pipeline: 'site_fit_bridge_mvp_v1'
  scope: 'seminole-2000-only'
  plan_id: string
  plan_name: string
  cad_analysis: CadWorkspaceExtractResult
  site_constraints: Record<string, unknown>
  proposal: {
    status: string
    candidates?: Array<{
      candidate_id: string
      strategy: string
      summary: string
      fit_status: string
      change_count: number
    } | null> | null
    warnings: string[]
  }
  warnings: string[]
}

export interface SiteFitBridgeApplyResult {
  pipeline: 'site_fit_bridge_mvp_v1'
  scope: 'seminole-2000-only'
  plan_id: string
  plan_name: string
  apply: {
    candidate_id: string
    apply_status: string
    compliance_summary: { status: string }
    warnings: string[]
  }
  warnings: string[]
}

export interface SiteFitProposalArtifactData {
  planId: string
  planName: string
  candidateId: string | null
  siteConstraints: Record<string, unknown>
  summary: string
  fitStatus: string
  warnings: string[]
}

export interface SiteFitApplyArtifactData {
  planId: string
  planName: string
  candidateId: string
  applyStatus: string
  complianceStatus: string
  warnings: string[]
}
