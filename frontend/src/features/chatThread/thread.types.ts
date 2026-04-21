export type ThreadRole = 'system' | 'user' | 'assistant'

export interface ThreadArtifact {
  id: string
  kind: 'image-source' | 'cad-source' | 'preview' | 'export'
  title: string
  description?: string
  href?: string
}

export interface ThreadMessage {
  id: string
  role: ThreadRole
  content: string
  createdAtIso: string
  artifacts: ThreadArtifact[]
}

export interface ThreadSummary {
  id: string
  projectId: string
  title: string
  lastActivityIso: string
  preview: string
}
