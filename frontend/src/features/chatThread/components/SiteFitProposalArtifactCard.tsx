import { CadReviewPreview } from '../../cad/CadReviewPreview'
import { formatArchitecturalMeasure } from '../../cad/overlay'
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
  const footprint = proposal.footprint ?? {}
  const changedRoomIds = proposal.changedRoomIds ?? []
  const violationMessages = proposal.violationMessages ?? []
  const blockerMessages = proposal.blockerMessages ?? []
  const mutationHintCount = proposal.mutationHintCount ?? 0
  const warnings = proposal.warnings ?? []
  const hasCandidate = Boolean(proposal.candidateId && proposal.cadAnalysisId)

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

      <div className="mt-4 grid gap-3 lg:grid-cols-4">
        <MetricCard
          label="Footprint actual"
          primary={formatArchitecturalMeasure(footprint.current?.width)}
          secondary={formatArchitecturalMeasure(footprint.current?.height)}
        />
        <MetricCard
          label="Envelope construible"
          primary={formatArchitecturalMeasure(footprint.buildable?.width)}
          secondary={formatArchitecturalMeasure(footprint.buildable?.height)}
        />
        <MetricCard
          label={hasCandidate ? 'Cómo quedaría' : 'Estado actual'}
          primary={hasCandidate ? formatArchitecturalMeasure(footprint.projected?.width) : 'Sin candidate'}
          secondary={hasCandidate
            ? formatArchitecturalMeasure(footprint.projected?.height)
            : 'No hay mutación ejecutable todavía'}
        />
        <MetricCard
          label="Delta contra envelope"
          primary={`W ${formatSignedMeasure(footprint.widthDelta)}`}
          secondary={`H ${formatSignedMeasure(footprint.heightDelta)}`}
        />
      </div>

      {proposal.preview && (
        <div className="mt-4 rounded-2xl border border-white/8 bg-black/10 p-3">
          <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Preview 1:1</p>
          <p className="mt-2 text-xs leading-5 text-zinc-400">
            Así queda la Seminole 2000 registrada hoy contra el site plan antes de aplicar cualquier cambio.
          </p>
          <CadReviewPreview review={proposal.preview} />
        </div>
      )}

      {changedRoomIds.length > 0 && (
        <div className="mt-4">
          <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Rooms tocados por el candidate</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {changedRoomIds.map((roomId) => (
              <span
                key={roomId}
                className="inline-flex rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2.5 py-1 text-[11px] text-emerald-100"
              >
                {roomId}
              </span>
            ))}
          </div>
        </div>
      )}

      {violationMessages.length > 0 && (
        <div className="mt-4 rounded-2xl border border-amber-500/20 bg-[#1b1406] p-3">
          <p className="text-[11px] uppercase tracking-[0.22em] text-amber-200/70">Violaciones detectadas</p>
          <ul className="mt-2 space-y-1 text-xs text-amber-100/90">
            {violationMessages.map((message) => (
              <li key={message}>• {message}</li>
            ))}
          </ul>
        </div>
      )}

      {!hasCandidate && blockerMessages.length > 0 && (
        <div className="mt-4 rounded-2xl border border-rose-500/20 bg-[#190d10] p-3">
          <p className="text-[11px] uppercase tracking-[0.22em] text-rose-200/70">Por qué no salió candidate</p>
          <ul className="mt-2 space-y-1 text-xs text-rose-100/90">
            {blockerMessages.map((message) => (
              <li key={message}>• {message}</li>
            ))}
          </ul>
          <p className="mt-3 text-[11px] text-rose-200/70">
            Mutation hints disponibles: {mutationHintCount}
          </p>
        </div>
      )}

      {warnings.length > 0 && (
        <ul className="mt-3 space-y-1 text-xs text-amber-300">
          {warnings.map((warning) => (
            <li key={warning}>• {warning}</li>
          ))}
        </ul>
      )}

      {hasCandidate && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={!onApplySiteFitProposal}
            onClick={() => onApplySiteFitProposal?.(proposal)}
            className="inline-flex rounded-xl border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-xs font-medium text-emerald-100 transition-colors hover:bg-emerald-400/15 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Apply proposal
          </button>
          <span className="text-xs text-zinc-500">
            Candidate: {proposal.candidateId} · {proposal.candidateStrategy ?? 'strategy desconocida'} · {proposal.changeCount ?? 0} cambios
          </span>
        </div>
      )}
    </article>
  )
}

function MetricCard({
  label,
  primary,
  secondary,
}: {
  label: string
  primary: string
  secondary: string
}) {
  return (
    <div className="rounded-2xl border border-white/8 bg-white/[0.03] px-3 py-3">
      <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">{label}</p>
      <p className="mt-2 text-sm font-medium text-zinc-100">{primary}</p>
      <p className="mt-1 text-xs text-zinc-400">{secondary}</p>
    </div>
  )
}

function formatSignedMeasure(value?: number | null) {
  if (value == null) return 'N/D'
  const sign = value > 0 ? '+' : ''
  return `${sign}${formatArchitecturalMeasure(value)}`
}
