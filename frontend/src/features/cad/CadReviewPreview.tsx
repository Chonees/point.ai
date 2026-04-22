import type { CadReviewArtifactData } from './contracts'
import { CadOverlayCanvas } from './CadOverlayCanvas'
import { formatArchitecturalMeasure, getFitVerdictText } from './overlay'

interface CadReviewPreviewProps {
  review: CadReviewArtifactData
}

export function CadReviewPreview({ review }: CadReviewPreviewProps) {
  const footprint = review.fitSummary?.footprint_bbox ?? review.floorPlan.bbox ?? null
  const buildable = review.fitSummary?.buildable_bbox ?? null
  const verdict = getFitVerdictText(review.fitSummary)
  const hasPreciseOverlay = Boolean(
    review.fitSummary?.footprint_bbox
    && review.fitSummary?.buildable_bbox
    && review.fitSummary?.buildable_polygon?.length
    && review.floorPlan.entities.length > 0
    && review.sitePlan.entities.length > 0,
  )
  const hasBlockedOverlay = !hasPreciseOverlay

  return (
    <div className="mt-3 space-y-3">
      {!hasBlockedOverlay && (
        <div className="grid gap-2 sm:grid-cols-3">
          <MetricCard
            label="Footprint"
            primary={formatArchitecturalMeasure(footprint?.width)}
            secondary={formatArchitecturalMeasure(footprint?.height)}
          />
          <MetricCard
            label="Area construible"
            primary={formatArchitecturalMeasure(buildable?.width)}
            secondary={formatArchitecturalMeasure(buildable?.height)}
          />
          <MetricCard
            label="Veredicto"
            primary={verdict}
            secondary={review.warnings[0] ?? `Unidad comun: ${review.canonicalUnit}`}
          />
        </div>
      )}

      {hasPreciseOverlay ? (
        <CadOverlayCanvas review={review} />
      ) : (
        <div className="rounded-2xl border border-amber-500/20 bg-[#17120a] px-4 py-4">
          <p className="text-[11px] uppercase tracking-[0.22em] text-amber-200/70">Preview bloqueado</p>
          <p className="mt-2 text-sm font-medium text-amber-50">Preview exacto no disponible todavía</p>
          <p className="mt-2 text-sm leading-6 text-amber-100/80">
            {review.warnings[0] ?? 'Todavía falta footprint o área construible real para renderizar el overlay preciso dentro del chat.'}
          </p>
        </div>
      )}
    </div>
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
