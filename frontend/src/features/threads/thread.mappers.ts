import type { ThreadMessage, ThreadSummary } from '../chatThread/thread.types'
import type { ThreadData } from './thread.types'

export function threadToThreadSummary(thread: ThreadData): ThreadSummary {
  return {
    id: thread.id,
    projectId: thread.projectId,
    title: thread.name,
    lastActivityIso: thread.updatedAt,
    preview: thread.structure ? 'Site-fit workspace ready' : 'Site-fit thread ready to start',
  }
}

export function threadToInitialMessages(thread: ThreadData): ThreadMessage[] {
  return [
    {
      id: `${thread.id}-system`,
      role: 'system',
      content: 'Thread restaurado desde el workspace site-fit.',
      createdAtIso: thread.createdAt,
      artifacts: [],
    },
    {
      id: `${thread.id}-assistant`,
      role: 'assistant',
      content: 'Restored site-fit workspace. Continue from the current thread state.',
      createdAtIso: thread.updatedAt,
      artifacts: [],
    },
  ]
}
