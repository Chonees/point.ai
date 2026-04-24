import { CadReviewArtifactCard } from './CadReviewArtifactCard'
import { SiteFitApplyArtifactCard } from './SiteFitApplyArtifactCard'
import { SiteFitProposalArtifactCard } from './SiteFitProposalArtifactCard'
import type { SiteFitProposalArtifactData } from '../../siteFit/contracts'
import type { ThreadArtifact } from '../thread.types'

interface ArtifactCardProps {
  artifact: ThreadArtifact
  onApplySiteFitProposal?: (proposal: SiteFitProposalArtifactData) => void | Promise<void>
}

export function ArtifactCard({ artifact, onApplySiteFitProposal }: ArtifactCardProps) {
  if (artifact.kind === 'cad-review') {
    return <CadReviewArtifactCard artifact={artifact} />
  }

  if (artifact.kind === 'site-fit-proposal') {
    return (
      <SiteFitProposalArtifactCard
        artifact={artifact}
        onApplySiteFitProposal={onApplySiteFitProposal}
      />
    )
  }

  if (artifact.kind === 'site-fit-apply') {
    return <SiteFitApplyArtifactCard artifact={artifact} />
  }

  const href = 'href' in artifact ? artifact.href : undefined

  return (
    <article className="rounded-2xl border border-white/8 bg-white/[0.03] p-3">
      <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">{artifact.kind}</p>
      <h4 className="mt-2 text-sm font-medium text-zinc-100">{artifact.title}</h4>
      {artifact.description && <p className="mt-2 text-sm text-zinc-400">{artifact.description}</p>}
      {href && (
        <a
          href={href}
          className="mt-3 inline-flex rounded-xl border border-white/10 px-3 py-2 text-xs text-zinc-100"
        >
          Open
        </a>
      )}
    </article>
  )
}
