import type { CadReviewArtifactData, CadWorkspacePoint } from './contracts'
import {
  computeOverlayScene,
  formatArchitecturalMeasure,
  getFitVerdictText,
} from './review'

interface CadReviewPreviewProps {
  review: CadReviewArtifactData
}

export function CadReviewPreview({ review }: CadReviewPreviewProps) {
  const scene = computeOverlayScene(review)
  const footprint = review.fitSummary?.footprint_bbox ?? review.floorPlan.bbox ?? null
  const buildable = review.fitSummary?.buildable_bbox ?? null
  const verdict = getFitVerdictText(review.fitSummary)

  return (
    <div className="mt-3 space-y-3">
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

      <div className="overflow-hidden rounded-2xl border border-white/8 bg-[#070707] p-3">
        <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Overlay review</p>
        <svg viewBox={scene.viewBox} className="mt-3 h-[280px] w-full rounded-xl bg-black/30">
          {scene.buildablePolygon.length >= 3 && (
            <polygon
              points={toSvgPoints(scene.buildablePolygon)}
              fill="rgba(34,197,94,0.12)"
              stroke="#4ade80"
              strokeWidth={6}
            />
          )}
          {scene.buildableBBox && (
            <rect
              x={scene.buildableBBox.x1}
              y={scene.buildableBBox.y1}
              width={scene.buildableBBox.width}
              height={scene.buildableBBox.height}
              fill="none"
              stroke="#4ade80"
              strokeDasharray="18 14"
              strokeWidth={4}
            />
          )}
          {scene.sitePolylines.map((points, index) => (
            <polyline
              key={`site-${index}`}
              points={toSvgPoints(points)}
              fill="none"
              stroke="#6ee7b7"
              strokeWidth={5}
            />
          ))}
          {scene.floorPolylines.map((points, index) => (
            <polyline
              key={`floor-${index}`}
              points={toSvgPoints(points)}
              fill="none"
              stroke="#67e8f9"
              strokeWidth={4}
            />
          ))}
        </svg>
      </div>
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

function toSvgPoints(points: CadWorkspacePoint[]) {
  return points.map((point) => `${point.x},${point.y}`).join(' ')
}
