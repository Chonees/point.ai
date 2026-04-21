import type { ThreadArtifact, ThreadMessage, ThreadSummary } from '../chatThread/thread.types'
import type { ThreadData } from './thread.types'

export function threadToThreadSummary(thread: ThreadData): ThreadSummary {
  return {
    id: thread.id,
    projectId: thread.projectId,
    title: thread.name,
    lastActivityIso: thread.updatedAt,
    preview: thread.structure ? 'Floor plan disponible' : 'Thread listo para empezar',
  }
}

export function threadToInitialMessages(thread: ThreadData): ThreadMessage[] {
  const artifacts: ThreadArtifact[] = []

  if (thread.imageData) {
    artifacts.push({
      id: `${thread.id}-image`,
      kind: 'image-source',
      title: 'Original image',
      description: 'Fuente persistida del thread',
    })
  }

  if (thread.structure) {
    artifacts.push({
      id: `${thread.id}-preview`,
      kind: 'preview',
      title: 'Latest parsed structure',
      description: 'Persisted geometry is available for the agent to continue from.',
    })
  }

  return [
    {
      id: `${thread.id}-system`,
      role: 'system',
      content: 'Thread restaurado desde el proyecto.',
      createdAtIso: thread.createdAt,
      artifacts: [],
    },
    {
      id: `${thread.id}-assistant`,
      role: 'assistant',
      content: 'Listo para continuar con generacion, fit o ajustes.',
      createdAtIso: thread.updatedAt,
      artifacts,
    },
  ]
}
