import type { PlanData } from '../projects'
import type { ThreadArtifact, ThreadMessage, ThreadSummary } from './thread.types'

export function planToThreadSummary(plan: PlanData): ThreadSummary {
  return {
    id: plan.id,
    projectId: plan.projectId,
    title: plan.name,
    lastActivityIso: plan.updatedAt,
    preview: plan.structure ? 'Floor plan disponible' : 'Thread listo para empezar',
  }
}

export function planToInitialMessages(plan: PlanData): ThreadMessage[] {
  const artifacts: ThreadArtifact[] = []

  if (plan.imageData) {
    artifacts.push({
      id: `${plan.id}-image`,
      kind: 'image-source',
      title: 'Original image',
      description: 'Fuente persistida del thread',
    })
  }

  if (plan.structure) {
    artifacts.push({
      id: `${plan.id}-preview`,
      kind: 'preview',
      title: 'Latest parsed structure',
      description: 'Persisted geometry is available for the agent to continue from.',
    })
  }

  return [
    {
      id: `${plan.id}-system`,
      role: 'system',
      content: 'Thread restaurado desde el proyecto.',
      createdAtIso: plan.createdAt,
      artifacts: [],
    },
    {
      id: `${plan.id}-assistant`,
      role: 'assistant',
      content: 'Listo para continuar con generacion, fit o ajustes.',
      createdAtIso: plan.updatedAt,
      artifacts,
    },
  ]
}
