import { apiUrl } from '../../lib/api'
import type { V2Result } from '../../types'
import { fileToBase64 } from '../../utils/fileToBase64'
import { buildCadReviewArtifactData } from '../cad/review'
import type { CadWorkspaceExtractResult } from '../cad/contracts'
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
  planName: string
}

interface ChatPlanUpdates {
  imageData?: string | null
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

function isImageFile(file: File | null) {
  if (!file) return false
  return file.type.startsWith('image/') || /\.(png|jpe?g|webp)$/i.test(file.name)
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

async function runGenerateFromImageTool(file: File, prompt: string): Promise<RunChatAgentToolResult> {
  const sourceImageData = await fileToBase64(file)
  const imageBase64 = sourceImageData.replace(/^data:image\/\w+;base64,/, '')
  const response = await fetch(apiUrl('/api/v2/generate-dxf'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      image: imageBase64,
      model_variant: 'ensemble',
    }),
  })
  const payload = await parseJsonOrThrow(response) as V2Result
  const artifacts: ThreadArtifact[] = []

  if (payload.preview_url) {
    artifacts.push({
      id: newMessageId('artifact'),
      kind: 'preview',
      title: 'Floor plan preview',
      description: 'Preview generado por Point.ai a partir de la imagen adjunta.',
      href: apiUrl(payload.preview_url),
    })
  }

  if (payload.dxf_url) {
    artifacts.push({
      id: newMessageId('artifact'),
      kind: 'export',
      title: 'Download DXF',
      description: 'DXF generado a partir del floor plan interpretado.',
      href: apiUrl(payload.dxf_url),
    })
  }

  const reviewText = payload.needs_review ? 'Quedo marcado para revision.' : 'Quedo listo para seguir trabajando.'

  return {
    assistantMessage: buildAssistantMessage(
      `Listo, genere el floor plan desde ${file.name}. ${reviewText}${prompt ? ` Pedido: ${prompt}.` : ''}`,
      artifacts,
    ),
    planUpdates: {
      imageData: sourceImageData,
      structure: payload.structure,
    },
  }
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
    title: 'CAD fit review',
    description: 'Review human-in-the-loop del floor plan sobre el site/buildable dentro del chat.',
    review: {
      ...cadReview,
      export: cadReview.export.ready && cadReview.export.href
        ? { ...cadReview.export, href: apiUrl(cadReview.export.href) }
        : cadReview.export,
    },
  }]

  return {
    assistantMessage: buildAssistantMessage(
      `Listo, analice el CAD ${file.name}. ${buildCadFitText(payload)} Unidad comun: ${payload.canonical_unit}. Te dejo el review inline en este chat.${prompt ? ` Pedido: ${prompt}.` : ''}`,
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
    summary: candidate?.summary ?? 'No vino ningun candidate baseline desde el bridge.',
    fitStatus: candidate?.fit_status ?? payload.proposal.status,
    warnings: [...payload.warnings, ...(payload.proposal.warnings ?? [])],
  }
}

function buildSiteFitApplyArtifactData(payload: SiteFitBridgeApplyResult): SiteFitApplyArtifactData {
  const href = payload.export_url ? apiUrl(payload.export_url) : undefined

  return {
    planId: payload.plan_id,
    planName: payload.plan_name,
    candidateId: payload.apply.candidate_id,
    applyId: payload.apply_id,
    applyStatus: payload.apply.apply_status,
    complianceStatus: payload.apply.compliance_summary.status,
    href,
    exportUrl: href,
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
  const cadReview = buildCadReviewArtifactData(payload.cad_analysis)
  const proposal = buildSiteFitProposalArtifactData(payload)
  const artifacts: ThreadArtifact[] = [
    {
      id: newMessageId('artifact'),
      kind: 'cad-review',
      title: 'CAD diagnostic review',
      description: 'Diagnostico human-in-the-loop del floor plan sobre el site/buildable dentro del chat.',
      review: {
        ...cadReview,
        export: {
          ready: false,
          href: undefined,
          reason: 'Diagnostico solamente. Exporta el resultado real desde el apply.',
        },
      },
    },
    {
      id: newMessageId('artifact'),
      kind: 'site-fit-proposal',
      title: `${payload.plan_name} proposal`,
      proposal,
    },
  ]

  return {
    assistantMessage: buildAssistantMessage(
      `Listo, pase ${file.name} por el bridge site-fit para ${payload.plan_name}. Estado: ${proposal.fitStatus}.${prompt ? ` Pedido: ${prompt}.` : ''}`,
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

  if (attachment && isImageFile(attachment)) {
    return runGenerateFromImageTool(attachment, prompt)
  }

  if (attachment && isCadFile(attachment)) {
    if (wantsSeminoleSiteFit(prompt)) {
      return runSiteFitBridgeTool(attachment, prompt)
    }
    return runCadAnalyzeTool(attachment, prompt)
  }

  if (attachment) {
    return {
      assistantMessage: buildAssistantMessage(
        `Todavia no se usar ${attachment.name}. Subime una imagen del floor plan o un .dxf/.dwg para que ejecute una de las dos herramientas reales.`,
      ),
    }
  }

  if (/(dxf|dwg|cad|site|lot|fit)/i.test(normalizedPrompt)) {
    return {
      assistantMessage: buildAssistantMessage(
        'Subime un .dxf o .dwg y lo analizo contra el site plan desde este mismo chat.',
      ),
    }
  }

  return {
    assistantMessage: buildAssistantMessage(
      'Subime una imagen del floor plan o un .dxf/.dwg. Hoy este agente ya sabe usar esas dos herramientas reales desde el chat.',
    ),
  }
}
