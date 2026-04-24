import type {
  CadReviewArtifactData,
  CadWorkspaceBBox,
  CadWorkspaceExtractResult,
  CadWorkspaceRoom,
} from '../cad/contracts'

export interface SiteFitCandidateChange {
  boundary_id: string
  side: string
  delta_x: number
  delta_y: number
  owner_room_ids?: string[]
  opening_ids?: string[]
  requires_rehost?: boolean
}

export interface SiteFitComplianceSummary {
  status: string
  checked_rule_ids: string[]
  violations: Array<{
    rule_id?: string
    message?: string
    reason?: string
  }>
  warnings: string[]
  boundary_diagnostics: Array<{
    boundary_id?: string
    status?: string
    reason?: string | null
    side?: string
    axis?: string
    overflow_delta?: number
    owner_room_ids?: string[]
    opening_ids?: string[]
    requires_rehost?: boolean
  }>
  room_diagnostics: Array<{
    room_id?: string
    boundary_id?: string
    status?: string
    reason?: string | null
    projected_width?: number
    projected_height?: number
    projected_area?: number
  }>
  mutation_hints: Array<{
    boundary_id?: string
    side?: string
    axis?: string
    delta_x?: number
    delta_y?: number
    owner_room_ids?: string[]
    opening_ids?: string[]
    requires_rehost?: boolean
  }>
}

export interface SiteFitRegistrationSummary {
  status: string
  canonical_unit?: string | null
  scale_locked?: boolean
  transform?: {
    scale?: number
    rotation_degrees?: number
    translate_x?: number
    translate_y?: number
  }
  registered_plan_bbox?: CadWorkspaceBBox | null
  warnings?: string[]
}

export interface SiteFitPlanSummary {
  source_kind: string
  canonical_unit?: string | null
  room_count: number
  wall_count: number
  opening_count: number
  footprint_bbox?: CadWorkspaceBBox | null
  movable_boundary_count?: number
  protected_boundary_count?: number
  locked_boundary_count?: number
  rehostable_opening_count?: number
}

export interface SiteFitProposalCandidate {
  candidate_id: string
  strategy: string
  summary: string
  fit_status: string
  change_count: number
  score?: number
  changes?: SiteFitCandidateChange[]
}

export interface SiteFitFootprintSummary {
  current?: CadWorkspaceBBox | null
  projected?: CadWorkspaceBBox | null
  buildable?: CadWorkspaceBBox | null
  widthDelta?: number | null
  heightDelta?: number | null
}

export interface SiteFitRoomMeasureSummary {
  name: string
  width: number
  height: number
  area: number
}

export interface SiteFitBridgeProposalResult {
  pipeline: 'site_fit_bridge_mvp_v1'
  scope: 'seminole-2000-only'
  plan_id: string
  plan_name: string
  cad_analysis: CadWorkspaceExtractResult
  proposal_review?: CadWorkspaceExtractResult
  site_constraints: Record<string, unknown>
  proposal: {
    analysis_id?: string
    status: string
    plan_summary?: SiteFitPlanSummary
    registration_summary?: SiteFitRegistrationSummary
    site_summary?: {
      buildable_bbox?: CadWorkspaceBBox | null
      has_buildable_envelope?: boolean
      locked_room_count?: number
      site_unit?: string
    }
    compliance_summary?: SiteFitComplianceSummary
    candidates?: Array<SiteFitProposalCandidate | null> | null
    warnings: string[]
  }
  warnings: string[]
}

export interface SiteFitBridgeApplyResult {
  pipeline: 'site_fit_bridge_mvp_v1'
  scope: 'seminole-2000-only'
  plan_id: string
  plan_name: string
  apply_id: string
  export_url: string
  applied_review: CadWorkspaceExtractResult
  apply: {
    candidate_id: string
    apply_status: string
    registration_summary?: SiteFitRegistrationSummary
    compliance_summary: { status: string }
    change_set?: SiteFitCandidateChange[]
    warnings: string[]
  }
  warnings: string[]
}

export interface SiteFitProposalArtifactData {
  planId: string
  planName: string
  candidateId: string | null
  cadAnalysisId: string | null
  siteConstraints: Record<string, unknown>
  summary: string
  fitStatus: string
  candidateStrategy?: string | null
  changeCount?: number
  preview?: CadReviewArtifactData
  footprint?: SiteFitFootprintSummary
  violationMessages?: string[]
  blockerMessages?: string[]
  mutationHintCount?: number
  changedRoomIds?: string[]
  warnings: string[]
}

export interface SiteFitApplyArtifactData {
  planId: string
  planName: string
  candidateId: string
  applyId: string
  applyStatus: string
  complianceStatus: string
  href?: string
  exportUrl?: string
  preview?: CadReviewArtifactData
  changeCount?: number
  changedRoomIds?: string[]
  beforeFootprint?: CadWorkspaceBBox | null
  afterFootprint?: CadWorkspaceBBox | null
  rooms?: SiteFitRoomMeasureSummary[]
  warnings: string[]
}
