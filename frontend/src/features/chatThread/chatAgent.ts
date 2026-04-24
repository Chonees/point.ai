import { apiUrl } from '../../lib/api'
import { buildCadReviewArtifactData } from '../cad/review'
import type { CadReviewArtifactData, CadWorkspaceExtractResult } from '../cad/contracts'
import type {
  SiteFitApplyArtifactData,
  SiteFitBridgeApplyResult,
  SiteFitBridgeProposalResult,
  SiteFitProposalArtifactData,
} from '../siteFit/contracts'
import type { ThreadArtifact, ThreadMessage } from './thread.types'

interface RunChatAgentToolArgs {
  prompt: string
  attachment: File | null
}

interface ChatPlanUpdates {
  structure?: Record<string, unknown> | null
  totalSqft?: number | null
}

interface RunChatAgentToolResult {
  assistantMessage: ThreadMessage
  planUpdates?: ChatPlanUpdates
}

interface RunSiteFitApplyToolArgs {
  planId: string
  planName: string
  candidateId: string
  cadAnalysisId: string
  siteConstraints: Record<string, unknown>
}

function newMessageId(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`
}

function isCadFile(file: File | null) {
  if (!file) return false
  return /\.(dxf|dwg)$/i.test(file.name)
}

function wantsSeminoleSiteFit(prompt: string) {
  return /seminole|site-fit|fit\s+.*seminole/i.test(prompt)
}

function buildAssistantMessage(content: string, artifacts: ThreadArtifact[] = []): ThreadMessage {
  return {
    id: newMessageId('assistant'),
    role: 'assistant',
    content,
    createdAtIso: new Date().toISOString(),
    artifacts,
  }
}

async function parseJsonOrThrow(response: Response) {
  const payload = await response.json()
  if (!response.ok) {
    throw new Error(payload?.detail || 'No se pudo completar la herramienta.')
  }
  return payload
}

function buildCadFitText(result: CadWorkspaceExtractResult) {
  const fit = result.fit_summary
  if (!fit) return 'No encontre un resumen de encaje todavia.'
  if (fit.basis === 'buildable_polygon') {
    return fit.fits_within_buildable_polygon
      ? 'El footprint entra dentro del poligono construible.'
      : 'El footprint NO entra dentro del poligono construible.'
  }
  if (fit.fits_within_buildable_bbox === true) return 'El footprint entra por bbox.'
  if (fit.fits_within_buildable_bbox === false) return 'El footprint NO entra por bbox.'
  return 'El encaje quedo sin veredicto fuerte.'
}

async function runCadAnalyzeTool(file: File, prompt: string): Promise<RunChatAgentToolResult> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(apiUrl('/api/cad-workspace/extract'), {
    method: 'POST',
    body: formData,
  })
  const payload = await parseJsonOrThrow(response) as CadWorkspaceExtractResult
  const cadReview = buildCadReviewArtifactData(payload)
  const artifacts: ThreadArtifact[] = [{
    id: newMessageId('artifact'),
    kind: 'cad-review',
    title: 'CAD diagnostic review',
    description: 'Diagnostico del CAD cargado para inspeccionar encaje y geometria. No es salida final de producto.',
    review: {
      ...cadReview,
      export: cadReview.export.ready && cadReview.export.href
        ? { ...cadReview.export, href: apiUrl(cadReview.export.href) }
        : cadReview.export,
    },
  }]

  return {
    assistantMessage: buildAssistantMessage(
      `Listo, corri el diagnostico CAD de ${file.name}. ${buildCadFitText(payload)} Unidad comun: ${payload.canonical_unit}. Esto es diagnostico inline, no salida final de producto.${prompt ? ` Pedido: ${prompt}.` : ''}`,
      artifacts,
    ),
  }
}

function buildSiteFitProposalArtifactData(payload: SiteFitBridgeProposalResult): SiteFitProposalArtifactData {
  const candidate = payload.proposal.candidates?.[0] ?? null

  return {
    planId: payload.plan_id,
    planName: payload.plan_name,
    candidateId: candidate?.candidate_id ?? null,
    cadAnalysisId: payload.cad_analysis.analysis_id,
    siteConstraints: payload.site_constraints,
    summary: candidate?.summary ?? 'No vino ningun candidate baseline desde el site-fit.',
    fitStatus: candidate?.fit_status ?? payload.proposal.status,
    warnings: [...payload.warnings, ...(payload.proposal.warnings ?? [])],
  }
}

function buildSiteFitApplyArtifactData(payload: SiteFitBridgeApplyResult): SiteFitApplyArtifactData {
  const href = payload.export_url ? apiUrl(payload.export_url) : undefined
  const preview: CadReviewArtifactData = {
    analysisId: payload.applied_review.analysis_id,
    sourceName: payload.applied_review.source_name,
    canonicalUnit: payload.applied_review.canonical_unit,
    floorPlan: payload.applied_review.floor_plan,
    sitePlan: payload.applied_review.site_plan,
    fitSummary: payload.applied_review.fit_summary ?? null,
    warnings: payload.applied_review.warnings,
    export: {
      ready: false,
      reason: 'Usa el DXF aplicado de esta tarjeta.',
    },
  }

  return {
    planId: payload.plan_id,
    planName: payload.plan_name,
    candidateId: payload.apply.candidate_id,
    applyId: payload.apply_id,
    applyStatus: payload.apply.apply_status,
    complianceStatus: payload.apply.compliance_summary.status,
    href,
    exportUrl: href,
    preview,
    warnings: [...payload.warnings, ...(payload.apply.warnings ?? [])],
  }
}

async function runSiteFitBridgeTool(file: File, prompt: string): Promise<RunChatAgentToolResult> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(apiUrl('/api/v2/site-fit/bridge/propose'), {
    method: 'POST',
    body: formData,
  })
  const payload = await parseJsonOrThrow(response) as SiteFitBridgeProposalResult
  const proposal = buildSiteFitProposalArtifactData(payload)
  const artifacts: ThreadArtifact[] = [
    {
      id: newMessageId('artifact'),
      kind: 'site-fit-proposal',
      title: `${payload.plan_name} proposal`,
      proposal,
    },
  ]

  return {
    assistantMessage: buildAssistantMessage(
      `Listo, corri site-fit de ${payload.plan_name} sobre ${file.name}. Estado: ${proposal.fitStatus}.${prompt ? ` Pedido: ${prompt}.` : ''}`,
      artifacts,
    ),
  }
}

export async function runSiteFitApplyTool({
  planId,
  planName,
  candidateId,
  cadAnalysisId,
  siteConstraints,
}: RunSiteFitApplyToolArgs): Promise<RunChatAgentToolResult> {
  const response = await fetch(apiUrl('/api/v2/site-fit/bridge/apply'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      plan_id: planId,
      site_constraints: siteConstraints,
      candidate_id: candidateId,
      cad_analysis_id: cadAnalysisId,
    }),
  })
  const payload = await parseJsonOrThrow(response) as SiteFitBridgeApplyResult
  const apply = buildSiteFitApplyArtifactData(payload)
  const artifacts: ThreadArtifact[] = [{
    id: newMessageId('artifact'),
    kind: 'site-fit-apply',
    title: 'Applied site-fit result',
    apply,
  }]

  return {
    assistantMessage: buildAssistantMessage(
      `Aplique la propuesta ${candidateId} de ${planName}. Compliance: ${apply.complianceStatus}.`,
      artifacts,
    ),
  }
}

export async function runChatAgentTool({
  prompt,
  attachment,
}: RunChatAgentToolArgs): Promise<RunChatAgentToolResult> {
  const normalizedPrompt = prompt.trim().toLowerCase()

  if (attachment && isCadFile(attachment)) {
    if (wantsSeminoleSiteFit(prompt)) {
      return runSiteFitBridgeTool(attachment, prompt)
    }
    return runCadAnalyzeTool(attachment, prompt)
  }

  if (attachment) {
    return {
      assistantMessage: buildAssistantMessage(
        `No puedo usar ${attachment.name} en esta lane. Solo soportamos site plan .dxf/.dwg para correr site-fit de Seminole 2000 o un diagnostico CAD.`,
      ),
    }
  }

  if (/(dxf|dwg|cad|site|lot|fit)/i.test(normalizedPrompt)) {
    return {
      assistantMessage: buildAssistantMessage(
        'Subime un site plan .dxf o .dwg y corro site-fit de Seminole 2000 o un diagnostico CAD desde este mismo chat.',
      ),
    }
  }

  return {
    assistantMessage: buildAssistantMessage(
      'Esta lane trabaja solo con site plan .dxf/.dwg. Con eso puedo correr site-fit de Seminole 2000 o un diagnostico CAD honesto.',
    ),
  }
}
