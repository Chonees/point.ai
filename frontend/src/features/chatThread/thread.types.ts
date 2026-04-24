import type { CadReviewArtifactData } from '../cad/contracts'
import type { SiteFitApplyArtifactData, SiteFitProposalArtifactData } from '../siteFit/contracts'

export type ThreadRole = 'system' | 'user' | 'assistant'

interface ThreadArtifactBase {
  id: string
  title: string
  description?: string
}

export interface ThreadSourceArtifact extends ThreadArtifactBase {
  kind: 'image-source' | 'cad-source'
}

export interface ThreadPreviewArtifact extends ThreadArtifactBase {
  kind: 'preview'
  href?: string
}

export interface ThreadExportArtifact extends ThreadArtifactBase {
  kind: 'export'
  href: string
}

export interface ThreadCadReviewArtifact extends ThreadArtifactBase {
  kind: 'cad-review'
  review: CadReviewArtifactData
}

export interface ThreadSiteFitProposalArtifact extends ThreadArtifactBase {
  kind: 'site-fit-proposal'
  proposal: SiteFitProposalArtifactData
}

export interface ThreadSiteFitApplyArtifact extends ThreadArtifactBase {
  kind: 'site-fit-apply'
  apply: SiteFitApplyArtifactData
}

export type ThreadArtifact =
  | ThreadSourceArtifact
  | ThreadPreviewArtifact
  | ThreadExportArtifact
  | ThreadCadReviewArtifact
  | ThreadSiteFitProposalArtifact
  | ThreadSiteFitApplyArtifact

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

export interface ThreadComposerSubmission {
  message: string
  attachment: File | null
}
