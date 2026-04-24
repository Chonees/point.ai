import { CadReviewPreview } from '../../cad/CadReviewPreview'
import { formatArchitecturalMeasure } from '../../cad/overlay'
import type { ThreadSiteFitApplyArtifact } from '../thread.types'

interface SiteFitApplyArtifactCardProps {
  artifact: ThreadSiteFitApplyArtifact
}

export function SiteFitApplyArtifactCard({ artifact }: SiteFitApplyArtifactCardProps) {
  const { apply } = artifact
  const beforeFootprint = apply.beforeFootprint ?? null
  const afterFootprint = apply.afterFootprint ?? null
  const rooms = apply.rooms ?? []
  const changedRoomIds = apply.changedRoomIds ?? []
  const warnings = apply.warnings ?? []
  const widthDelta = (afterFootprint?.width ?? 0) - (beforeFootprint?.width ?? 0)
  const heightDelta = (afterFootprint?.height ?? 0) - (beforeFootprint?.height ?? 0)

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

      <div className="mt-4 grid gap-3 lg:grid-cols-4">
        <MetricCard
          label="Antes"
          primary={formatArchitecturalMeasure(beforeFootprint?.width)}
          secondary={formatArchitecturalMeasure(beforeFootprint?.height)}
        />
        <MetricCard
          label="Después"
          primary={formatArchitecturalMeasure(afterFootprint?.width)}
          secondary={formatArchitecturalMeasure(afterFootprint?.height)}
        />
        <MetricCard
          label="Delta neto"
          primary={`W ${formatSignedMeasure(widthDelta)}`}
          secondary={`H ${formatSignedMeasure(heightDelta)}`}
        />
        <MetricCard
          label="Candidate"
          primary={apply.candidateId}
          secondary={`${apply.changeCount ?? 0} cambios`}
        />
      </div>

      <div className="mt-3 space-y-1 text-xs text-zinc-500">
        <p>Apply ID: {apply.applyId}</p>
        {changedRoomIds.length > 0 && (
          <p>Rooms tocados: {changedRoomIds.join(', ')}</p>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {apply.href ? (
          <a
            href={apply.href}
            className="inline-flex rounded-xl border border-sky-400/30 bg-sky-400/10 px-3 py-2 text-xs font-medium text-sky-100 transition-colors hover:bg-sky-400/15"
          >
            Download applied DXF
          </a>
        ) : (
          <span className="inline-flex rounded-xl border border-white/10 px-3 py-2 text-xs text-zinc-500">
            Export pendiente
          </span>
        )}
      </div>

      {rooms.length > 0 && (
        <div className="mt-4 rounded-2xl border border-white/8 bg-black/10 p-3">
          <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Medidas nuevas por room</p>
          <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {rooms.map((room) => (
              <div key={room.name} className="rounded-xl border border-white/8 bg-white/[0.03] px-3 py-3">
                <p className="text-xs font-medium text-zinc-100">{room.name}</p>
                <p className="mt-2 text-xs text-zinc-300">
                  {formatArchitecturalMeasure(room.width)} × {formatArchitecturalMeasure(room.height)}
                </p>
                <p className="mt-1 text-[11px] text-zinc-500">Área: {formatArea(room.area)}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {apply.preview && <CadReviewPreview review={apply.preview} />}

      {warnings.length > 0 && (
        <ul className="mt-3 space-y-1 text-xs text-amber-300">
          {warnings.map((warning) => (
            <li key={warning}>• {warning}</li>
          ))}
        </ul>
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
  if (value == null || Number.isNaN(value)) return 'N/D'
  const sign = value > 0 ? '+' : ''
  return `${sign}${formatArchitecturalMeasure(value)}`
}

function formatArea(value?: number | null) {
  if (value == null || Number.isNaN(value)) return 'N/D'
  const sqft = value / 144
  return `${sqft.toFixed(1)} sqft · ${value.toFixed(0)} in²`
}
