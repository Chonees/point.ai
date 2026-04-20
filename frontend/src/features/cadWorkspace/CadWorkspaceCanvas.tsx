import type { CadWorkspaceEntity, CadWorkspaceExtractResult, CadWorkspaceView } from './types'

interface CadWorkspaceCanvasProps {
  result: CadWorkspaceExtractResult
}

function renderEntity(entity: CadWorkspaceEntity, key: string) {
  if (entity.type === 'line' && entity.start && entity.end) {
    return (
      <line
        key={key}
        x1={entity.start.x}
        y1={entity.start.y}
        x2={entity.end.x}
        y2={entity.end.y}
        stroke="currentColor"
        strokeWidth={4}
        vectorEffect="non-scaling-stroke"
      />
    )
  }

  if (entity.type === 'polyline' && entity.points.length > 1) {
    const points = entity.points.map((point) => `${point.x},${point.y}`).join(' ')
    return (
      <polyline
        key={key}
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth={4}
        vectorEffect="non-scaling-stroke"
      />
    )
  }

  if (entity.type === 'text' && entity.position && entity.text) {
    return (
      <text
        key={key}
        x={entity.position.x}
        y={entity.position.y}
        fill="currentColor"
        fontSize={24}
        fontWeight={600}
      >
        {entity.text}
      </text>
    )
  }

  return null
}

function renderView(view: CadWorkspaceView, tx: number, ty: number, color: string) {
  return (
    <g transform={`translate(${tx} ${ty})`} className={color}>
      {view.entities.map((entity, index) => renderEntity(entity, `${view.role}-${index}`))}
    </g>
  )
}

export function CadWorkspaceCanvas({ result }: CadWorkspaceCanvasProps) {
  const floorBox = result.floor_plan.bbox
  const siteBox = result.site_plan.bbox

  if (!floorBox && !siteBox) {
    return (
      <div className="rounded-[24px] border border-white/6 bg-black/20 px-5 py-6 text-sm text-zinc-400">
        No hay geometría suficiente para dibujar una vista comparativa todavía.
      </div>
    )
  }

  const gap = result.side_by_side.gap || 24
  const floorWidth = floorBox?.width || 0
  const siteWidth = siteBox?.width || 0
  const totalWidth = Math.max(floorWidth + siteWidth + gap, 1)
  const totalHeight = Math.max(floorBox?.height || 0, siteBox?.height || 0, 1)
  const floorTranslateX = floorBox ? -floorBox.x1 : 0
  const floorTranslateY = floorBox ? -floorBox.y1 : 0
  const siteTranslateX = siteBox ? floorWidth + gap - siteBox.x1 : 0
  const siteTranslateY = siteBox ? -siteBox.y1 : 0

  return (
    <section className="overflow-hidden rounded-[28px] border border-white/6 bg-zinc-950/80">
      <div className="border-b border-white/6 px-5 py-4">
        <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Comparative canvas</p>
        <h3 className="mt-2 text-lg font-semibold text-zinc-100">Floor plan + site plan a la misma escala</h3>
        <p className="mt-1 text-sm text-zinc-400">
          Ambos views se dibujan en <span className="font-medium text-zinc-200">{result.canonical_unit}</span> y se acomodan lado a lado sin reescalar.
        </p>
      </div>
      <div className="p-4">
        <svg
          role="img"
          aria-label="CAD side by side comparison"
          viewBox={`0 0 ${totalWidth} ${totalHeight}`}
          className="h-[420px] w-full rounded-[20px] bg-[#050505]"
          preserveAspectRatio="xMinYMin meet"
        >
          {floorBox && (
            <>
              <rect
                x={0}
                y={0}
                width={floorBox.width}
                height={totalHeight}
                fill="rgba(24,24,27,0.35)"
                stroke="rgba(255,255,255,0.08)"
                strokeWidth={2}
              />
              <text x={18} y={28} fill="#f4f4f5" fontSize={22} fontWeight={700}>
                FLOOR PLAN
              </text>
              {renderView(result.floor_plan, floorTranslateX, floorTranslateY, 'text-cyan-300')}
            </>
          )}
          {siteBox && (
            <>
              <rect
                x={floorWidth + gap}
                y={0}
                width={siteBox.width}
                height={totalHeight}
                fill="rgba(24,24,27,0.35)"
                stroke="rgba(255,255,255,0.08)"
                strokeWidth={2}
              />
              <text x={floorWidth + gap + 18} y={28} fill="#f4f4f5" fontSize={22} fontWeight={700}>
                SITE PLAN
              </text>
              {renderView(result.site_plan, siteTranslateX, siteTranslateY, 'text-emerald-300')}
            </>
          )}
        </svg>
      </div>
    </section>
  )
}
