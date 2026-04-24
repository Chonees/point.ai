import type { CadReviewArtifactData, CadWorkspaceBBox, CadWorkspaceEntity, CadWorkspacePoint, CadWorkspaceRoom } from './contracts'
import {
  formatArchitecturalMeasure,
  formatRoomDimensions,
  resolveOverlayBBox,
  roomVisual,
  segmentOverflowFragments,
  transformedSegments,
} from './overlay'

interface CadOverlayCanvasProps {
  review: CadReviewArtifactData
}

function renderEntity(entity: CadWorkspaceEntity, key: string) {
  if (entity.type.toLowerCase() === 'line' && entity.start && entity.end) {
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

  if (entity.points.length > 1) {
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

  return null
}

function renderView(role: string, entities: CadWorkspaceEntity[], tx: number, ty: number, color: string) {
  return (
    <g transform={`translate(${tx} ${ty})`} className={color}>
      {entities.map((entity, index) => renderEntity(entity, `${role}-${index}`))}
    </g>
  )
}

function renderHorizontalDimension(box: CadWorkspaceBBox, label: string, y: number, color: string) {
  const centerX = box.x1 + (box.width / 2)
  return (
    <g className={color}>
      <line x1={box.x1} y1={y} x2={box.x2} y2={y} stroke="currentColor" strokeWidth={2} vectorEffect="non-scaling-stroke" />
      <line x1={box.x1} y1={y - 14} x2={box.x1} y2={y + 14} stroke="currentColor" strokeWidth={2} vectorEffect="non-scaling-stroke" />
      <line x1={box.x2} y1={y - 14} x2={box.x2} y2={y + 14} stroke="currentColor" strokeWidth={2} vectorEffect="non-scaling-stroke" />
      <text x={centerX} y={y - 10} textAnchor="middle" fill="currentColor" fontSize={26} fontWeight={700}>
        {label}
      </text>
    </g>
  )
}

function renderVerticalDimension(box: CadWorkspaceBBox, label: string, x: number, color: string) {
  const centerY = box.y1 + (box.height / 2)
  return (
    <g className={color}>
      <line x1={x} y1={box.y1} x2={x} y2={box.y2} stroke="currentColor" strokeWidth={2} vectorEffect="non-scaling-stroke" />
      <line x1={x - 14} y1={box.y1} x2={x + 14} y2={box.y1} stroke="currentColor" strokeWidth={2} vectorEffect="non-scaling-stroke" />
      <line x1={x - 14} y1={box.y2} x2={x + 14} y2={box.y2} stroke="currentColor" strokeWidth={2} vectorEffect="non-scaling-stroke" />
      <text
        x={x + 24}
        y={centerY}
        textAnchor="middle"
        fill="currentColor"
        fontSize={26}
        fontWeight={700}
        transform={`rotate(90 ${x + 24} ${centerY})`}
      >
        {label}
      </text>
    </g>
  )
}

function renderRoom(room: CadWorkspaceRoom) {
  if (room.polygon.length < 3) return null
  const visual = roomVisual(room.name, room.measurement_source)
  const points = room.polygon.map((point) => `${point.x},${point.y}`).join(' ')

  return (
    <g key={room.name}>
      <polygon
        points={points}
        fill={visual.fill}
        fillOpacity={visual.fillOpacity}
        stroke={visual.stroke}
        strokeWidth={2.5}
        strokeDasharray={visual.dash}
        vectorEffect="non-scaling-stroke"
      />
      <text
        x={room.centroid.x}
        y={room.centroid.y - 8}
        textAnchor="middle"
        fill="#f8fafc"
        fontSize={18}
        fontWeight={700}
        paintOrder="stroke"
        stroke="#020617"
        strokeWidth={4}
        strokeLinejoin="round"
      >
        {room.name}
      </text>
      <text
        x={room.centroid.x}
        y={room.centroid.y + 14}
        textAnchor="middle"
        fill="#e2e8f0"
        fontSize={14}
        fontWeight={600}
        paintOrder="stroke"
        stroke="#020617"
        strokeWidth={4}
        strokeLinejoin="round"
      >
        {formatRoomDimensions(room)}
      </text>
    </g>
  )
}

function renderRooms(rooms: CadWorkspaceRoom[], tx: number, ty: number) {
  if (rooms.length === 0) return null
  return (
    <g transform={`translate(${tx} ${ty})`} data-testid="floor-rooms">
      {rooms.map((room) => renderRoom(room))}
    </g>
  )
}

function renderOverflowFragments(entities: CadWorkspaceEntity[], dx: number, dy: number, polygon: CadWorkspacePoint[]) {
  const fragments = []
  for (const entity of entities) {
    for (const segment of transformedSegments(entity, dx, dy)) {
      fragments.push(...segmentOverflowFragments(segment, polygon))
    }
  }

  return (
    <g data-testid="overflow-fragments" className="text-red-400/90">
      {fragments.map((fragment, index) => (
        <line
          key={`overflow-${index}`}
          x1={fragment.start.x}
          y1={fragment.start.y}
          x2={fragment.end.x}
          y2={fragment.end.y}
          stroke="currentColor"
          strokeWidth={3}
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      ))}
    </g>
  )
}

export function CadOverlayCanvas({ review }: CadOverlayCanvasProps) {
  const siteBox = review.sitePlan.bbox
  const floorBox = review.floorPlan.bbox
  const overlayBox = resolveOverlayBBox(review)

  if (!siteBox && !floorBox) {
    return (
      <div className="rounded-[24px] border border-white/6 bg-black/20 px-5 py-6 text-sm text-zinc-400">
        No hay geometría suficiente para dibujar un overlay todavía.
      </div>
    )
  }

  const padding = 160
  const fallbackBox = overlayBox ?? floorBox
  const viewWidth = Math.max(siteBox?.width ?? 0, fallbackBox?.x2 ?? 0, 1) + (padding * 2)
  const viewHeight = Math.max(siteBox?.height ?? 0, fallbackBox?.y2 ?? 0, 1) + (padding * 2)
  const siteTranslateX = padding - (siteBox?.x1 ?? 0)
  const siteTranslateY = padding - (siteBox?.y1 ?? 0)
  const floorTranslateX = padding + ((overlayBox?.x1 ?? 0) - (floorBox?.x1 ?? 0))
  const floorTranslateY = padding + ((overlayBox?.y1 ?? 0) - (floorBox?.y1 ?? 0))

  const shiftedBuildable = review.fitSummary?.buildable_bbox
    ? {
        ...review.fitSummary.buildable_bbox,
        x1: review.fitSummary.buildable_bbox.x1 + padding,
        x2: review.fitSummary.buildable_bbox.x2 + padding,
        y1: review.fitSummary.buildable_bbox.y1 + padding,
        y2: review.fitSummary.buildable_bbox.y2 + padding,
      }
    : null

  const shiftedBuildablePolygon = review.fitSummary?.buildable_polygon?.length
    ? review.fitSummary.buildable_polygon.map((point) => ({
        x: point.x + padding,
        y: point.y + padding,
      }))
    : null

  const shiftedOverlay = overlayBox
    ? {
        ...overlayBox,
        x1: overlayBox.x1 + padding,
        x2: overlayBox.x2 + padding,
        y1: overlayBox.y1 + padding,
        y2: overlayBox.y2 + padding,
      }
    : null

  return (
    <section className="overflow-hidden rounded-[28px] border border-white/6 bg-zinc-950/80">
      <div className="border-b border-white/6 px-5 py-4">
        <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Overlay canvas</p>
        <h3 className="mt-2 text-lg font-semibold text-zinc-100">Overlay del footprint sobre el área construible</h3>
        <p className="mt-1 text-sm text-zinc-400">
          El site plan queda como base y el floor plan se ubica arriba en <span className="font-medium text-zinc-200">{review.canonicalUnit}</span>, con cotas visuales y rooms identificados para revisar el encaje real.
        </p>
        <p className="mt-2 text-sm text-zinc-500">
          Cian = footprint. Verde = polígono construible. <span className="font-medium text-red-300">Rojo marca lo que sobresale.</span>
        </p>
      </div>
      <div className="p-4">
        <svg
          role="img"
          aria-label="CAD overlay comparison"
          viewBox={`0 0 ${viewWidth} ${viewHeight}`}
          className="h-[520px] w-full rounded-[20px] bg-[#050505]"
          preserveAspectRatio="xMidYMid meet"
        >
          {siteBox && (
            <>
              <rect
                x={padding}
                y={padding}
                width={siteBox.width}
                height={siteBox.height}
                fill="rgba(24,24,27,0.15)"
                stroke="rgba(255,255,255,0.08)"
                strokeWidth={2}
              />
              {renderView(review.sitePlan.role, review.sitePlan.entities, siteTranslateX, siteTranslateY, 'text-emerald-300')}
            </>
          )}

          {shiftedBuildablePolygon && shiftedBuildable && (
            <>
              <polyline
                points={shiftedBuildablePolygon.map((point) => `${point.x},${point.y}`).join(' ')}
                fill="rgba(16,185,129,0.08)"
                stroke="rgba(16,185,129,0.55)"
                strokeWidth={4}
                vectorEffect="non-scaling-stroke"
              />
              {renderHorizontalDimension(shiftedBuildable, `Buildable ${formatArchitecturalMeasure(shiftedBuildable.width)}`, shiftedBuildable.y1 - 44, 'text-emerald-200')}
              {renderVerticalDimension(shiftedBuildable, `Buildable ${formatArchitecturalMeasure(shiftedBuildable.height)}`, shiftedBuildable.x2 + 44, 'text-emerald-200')}
            </>
          )}

          {floorBox && overlayBox && (
            <>
              {renderRooms(review.floorPlan.rooms, floorTranslateX, floorTranslateY)}
              {renderView(review.floorPlan.role, review.floorPlan.entities, floorTranslateX, floorTranslateY, 'text-cyan-300')}
              {shiftedBuildablePolygon && renderOverflowFragments(review.floorPlan.entities, floorTranslateX, floorTranslateY, shiftedBuildablePolygon)}
              {shiftedOverlay && (
                <>
                  <rect
                    x={shiftedOverlay.x1}
                    y={shiftedOverlay.y1}
                    width={shiftedOverlay.width}
                    height={shiftedOverlay.height}
                    fill="rgba(34,211,238,0.06)"
                    stroke="rgba(34,211,238,0.5)"
                    strokeDasharray="10 8"
                    strokeWidth={3}
                  />
                  {renderHorizontalDimension(shiftedOverlay, `Footprint ${formatArchitecturalMeasure(shiftedOverlay.width)}`, shiftedOverlay.y2 + 56, 'text-cyan-200')}
                  {renderVerticalDimension(shiftedOverlay, `Footprint ${formatArchitecturalMeasure(shiftedOverlay.height)}`, shiftedOverlay.x1 - 44, 'text-cyan-200')}
                </>
              )}
            </>
          )}

          <text x={padding} y={44} fill="#f4f4f5" fontSize={24} fontWeight={700}>
            SITE + BUILDABLE + FLOOR OVERLAY
          </text>
        </svg>
      </div>
    </section>
  )
}
