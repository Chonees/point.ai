import { CadReviewPreview } from '../../cad/CadReviewPreview'
import type { ThreadCadReviewArtifact } from '../thread.types'

interface CadReviewArtifactCardProps {
  artifact: ThreadCadReviewArtifact
}

export function CadReviewArtifactCard({ artifact }: CadReviewArtifactCardProps) {
  const { review } = artifact

  return (
    <article className="rounded-2xl border border-cyan-500/20 bg-cyan-500/[0.04] p-3">
      <p className="text-[11px] uppercase tracking-[0.22em] text-cyan-200/70">cad-review</p>
      <h4 className="mt-2 text-sm font-medium text-zinc-100">{artifact.title}</h4>
      <p className="mt-2 text-xs text-zinc-400">Unidad comun: {review.canonicalUnit}</p>
      {review.warnings.length > 0 && (
        <p className="mt-1 text-xs text-amber-300">{review.warnings[0]}</p>
      )}

      <CadReviewPreview review={review} />

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {review.export.ready && review.export.href ? (
          <a
            href={review.export.href}
            className="inline-flex rounded-xl border border-white/10 px-3 py-2 text-xs text-zinc-100"
          >
            Download DXF
          </a>
        ) : (
          <span className="inline-flex rounded-xl border border-white/10 px-3 py-2 text-xs text-zinc-500">
            DXF bloqueado: {review.export.reason}
          </span>
        )}
      </div>
    </article>
  )
}
