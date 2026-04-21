import { apiUrl } from '../../lib/api'
import type { V2Result } from '../../types'
import { fileToBase64 } from '../../utils/fileToBase64'
import { buildCadReviewArtifactData } from '../cad/review'
import type { CadWorkspaceExtractResult } from '../cad/contracts'
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

export async function runChatAgentTool({
  prompt,
  attachment,
}: RunChatAgentToolArgs): Promise<RunChatAgentToolResult> {
  const normalizedPrompt = prompt.trim().toLowerCase()

  if (attachment && isImageFile(attachment)) {
    return runGenerateFromImageTool(attachment, prompt)
  }

  if (attachment && isCadFile(attachment)) {
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
