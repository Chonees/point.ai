import type { SiteFitProposalArtifactData } from '../../siteFit/contracts'
import type { ThreadSiteFitProposalArtifact } from '../thread.types'

interface SiteFitProposalArtifactCardProps {
  artifact: ThreadSiteFitProposalArtifact
  onApplySiteFitProposal?: (proposal: SiteFitProposalArtifactData) => void | Promise<void>
}

export function SiteFitProposalArtifactCard({
  artifact,
  onApplySiteFitProposal,
}: SiteFitProposalArtifactCardProps) {
  const { proposal } = artifact

  return (
    <article className="rounded-2xl border border-emerald-500/20 bg-[#0c1511] p-4 shadow-[0_0_0_1px_rgba(16,185,129,0.05)]">
      <p className="text-[11px] uppercase tracking-[0.22em] text-emerald-200/70">site-fit-proposal</p>
      <h4 className="mt-2 text-sm font-medium text-zinc-100">{artifact.title}</h4>
      <dl className="mt-3 grid gap-3 sm:grid-cols-2">
        <div>
          <dt className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Plan</dt>
          <dd className="mt-1 text-sm text-zinc-100">{proposal.planName}</dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Fit status</dt>
          <dd className="mt-1 text-sm text-zinc-100">{proposal.fitStatus}</dd>
        </div>
      </dl>
      <p className="mt-3 text-sm leading-6 text-zinc-300">{proposal.summary}</p>

      {proposal.warnings.length > 0 && (
        <ul className="mt-3 space-y-1 text-xs text-amber-300">
          {proposal.warnings.map((warning) => (
            <li key={warning}>• {warning}</li>
          ))}
        </ul>
      )}

      {proposal.candidateId && proposal.cadAnalysisId && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={!onApplySiteFitProposal}
            onClick={() => onApplySiteFitProposal?.(proposal)}
            className="inline-flex rounded-xl border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-xs font-medium text-emerald-100 transition-colors hover:bg-emerald-400/15 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Apply proposal
          </button>
          <span className="text-xs text-zinc-500">Candidate: {proposal.candidateId}</span>
        </div>
      )}
    </article>
  )
}
