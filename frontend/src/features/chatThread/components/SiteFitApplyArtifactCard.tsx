import type { ThreadSiteFitApplyArtifact } from '../thread.types'

interface SiteFitApplyArtifactCardProps {
  artifact: ThreadSiteFitApplyArtifact
}

export function SiteFitApplyArtifactCard({ artifact }: SiteFitApplyArtifactCardProps) {
  const { apply } = artifact

  return (
    <article className="rounded-2xl border border-sky-500/20 bg-[#0b1216] p-4 shadow-[0_0_0_1px_rgba(56,189,248,0.05)]">
      <p className="text-[11px] uppercase tracking-[0.22em] text-sky-200/70">site-fit-apply</p>
      <h4 className="mt-2 text-sm font-medium text-zinc-100">{artifact.title}</h4>
      <dl className="mt-3 grid gap-3 sm:grid-cols-3">
        <div>
          <dt className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Plan</dt>
          <dd className="mt-1 text-sm text-zinc-100">{apply.planName}</dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Apply status</dt>
          <dd className="mt-1 text-sm text-zinc-100">{apply.applyStatus}</dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Compliance</dt>
          <dd className="mt-1 text-sm text-zinc-100">{apply.complianceStatus}</dd>
        </div>
      </dl>
      <p className="mt-3 text-xs text-zinc-500">Candidate: {apply.candidateId}</p>

      {apply.warnings.length > 0 && (
        <ul className="mt-3 space-y-1 text-xs text-amber-300">
          {apply.warnings.map((warning) => (
            <li key={warning}>• {warning}</li>
          ))}
        </ul>
      )}
    </article>
  )
}
