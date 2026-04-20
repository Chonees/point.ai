import type { CadWorkspaceBBox, CadWorkspaceEntity, CadWorkspaceExtractResult, CadWorkspacePoint, CadWorkspaceView } from './types'

interface CadWorkspaceCanvasProps {
  result: CadWorkspaceExtractResult
}

interface Segment {
  start: CadWorkspacePoint
  end: CadWorkspacePoint
}

function formatMeasure(value?: number | null) {
  if (value == null) return '—'
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}

function formatFeetInches(value?: number | null) {
  if (value == null) return '—'
  const sign = value < 0 ? '-' : ''
  const absolute = Math.abs(value)
  let feet = Math.floor(absolute / 12)
  let remainder = absolute - (feet * 12)
  let wholeInches = Math.floor(remainder)
  let fraction = remainder - wholeInches
  let eighths = Math.round(fraction * 8)

  if (eighths === 8) {
    wholeInches += 1
    eighths = 0
  }
  if (wholeInches === 12) {
    feet += 1
    wholeInches = 0
  }

  const fractionMap: Record<number, string> = {
    1: '1/8',
    2: '1/4',
    3: '3/8',
    4: '1/2',
    5: '5/8',
    6: '3/4',
    7: '7/8',
  }
  const fractionText = fractionMap[eighths]
  if (fractionText) {
    return `${sign}${feet}'-${wholeInches} ${fractionText}"`
  }
  return `${sign}${feet}'-${wholeInches}"`
}

function formatArchitecturalMeasure(value?: number | null) {
  if (value == null) return '—'
  return `${formatFeetInches(value)} · ${formatMeasure(value)} in`
}

function resolveOverlayBBox(result: CadWorkspaceExtractResult): CadWorkspaceBBox | null {
  const floorBox = result.fit_summary?.footprint_bbox ?? result.floor_plan.bbox
  const buildableBox = result.fit_summary?.buildable_bbox
  if (!floorBox || !buildableBox) return null

  const x1 = buildableBox.x1 + ((buildableBox.width - floorBox.width) / 2)
  const y1 = buildableBox.y1 + ((buildableBox.height - floorBox.height) / 2)
  return {
    x1,
    y1,
    x2: x1 + floorBox.width,
    y2: y1 + floorBox.height,
    width: floorBox.width,
    height: floorBox.height,
  }
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

  return null
}

function renderView(view: CadWorkspaceView, tx: number, ty: number, color: string) {
  return (
    <g transform={`translate(${tx} ${ty})`} className={color}>
      {view.entities.map((entity, index) => renderEntity(entity, `${view.role}-${index}`))}
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

function pointClose(left: CadWorkspacePoint, right: CadWorkspacePoint, tolerance = 1e-6) {
  return Math.abs(left.x - right.x) <= tolerance && Math.abs(left.y - right.y) <= tolerance
}

function distancePointToSegment(point: CadWorkspacePoint, start: CadWorkspacePoint, end: CadWorkspacePoint) {
  const dx = end.x - start.x
  const dy = end.y - start.y
  if (Math.abs(dx) < 1e-9 && Math.abs(dy) < 1e-9) {
    return Math.hypot(point.x - start.x, point.y - start.y)
  }
  const t = Math.max(0, Math.min(1, (((point.x - start.x) * dx) + ((point.y - start.y) * dy)) / ((dx * dx) + (dy * dy))))
  const closestX = start.x + (t * dx)
  const closestY = start.y + (t * dy)
  return Math.hypot(point.x - closestX, point.y - closestY)
}

function pointOnBoundary(point: CadWorkspacePoint, polygon: CadWorkspacePoint[], tolerance = 1e-3) {
  for (let index = 0; index < polygon.length - 1; index += 1) {
    if (distancePointToSegment(point, polygon[index], polygon[index + 1]) <= tolerance) {
      return true
    }
  }
  return false
}

function pointInPolygon(point: CadWorkspacePoint, polygon: CadWorkspacePoint[]) {
  let inside = false
  for (let index = 0; index < polygon.length - 1; index += 1) {
    const a = polygon[index]
    const b = polygon[index + 1]
    const intersects = ((a.y > point.y) !== (b.y > point.y))
      && (point.x < (((b.x - a.x) * (point.y - a.y)) / ((b.y - a.y) || 1e-9)) + a.x)
    if (intersects) inside = !inside
  }
  return inside || pointOnBoundary(point, polygon)
}

function segmentIntersectionParameter(segment: Segment, edge: Segment) {
  const r = { x: segment.end.x - segment.start.x, y: segment.end.y - segment.start.y }
  const s = { x: edge.end.x - edge.start.x, y: edge.end.y - edge.start.y }
  const denominator = (r.x * s.y) - (r.y * s.x)
  const qp = { x: edge.start.x - segment.start.x, y: edge.start.y - segment.start.y }
  const crossQPR = (qp.x * r.y) - (qp.y * r.x)

  if (Math.abs(denominator) < 1e-9) {
    if (Math.abs(crossQPR) < 1e-9) {
      return null
    }
    return null
  }

  const t = ((qp.x * s.y) - (qp.y * s.x)) / denominator
  const u = ((qp.x * r.y) - (qp.y * r.x)) / denominator
  if (t < -1e-6 || t > 1.000001 || u < -1e-6 || u > 1.000001) {
    return null
  }
  return Math.max(0, Math.min(1, t))
}

function interpolate(start: CadWorkspacePoint, end: CadWorkspacePoint, t: number): CadWorkspacePoint {
  return {
    x: start.x + ((end.x - start.x) * t),
    y: start.y + ((end.y - start.y) * t),
  }
}

function segmentOverflowFragments(segment: Segment, polygon: CadWorkspacePoint[]): Segment[] {
  const params = [0, 1]
  for (let index = 0; index < polygon.length - 1; index += 1) {
    const edge = { start: polygon[index], end: polygon[index + 1] }
    const t = segmentIntersectionParameter(segment, edge)
    if (t != null) params.push(t)
  }

  const ordered = params
    .map((value) => Number(value.toFixed(6)))
    .sort((left, right) => left - right)
    .filter((value, index, list) => index === 0 || Math.abs(value - list[index - 1]) > 1e-6)

  const fragments: Segment[] = []
  for (let index = 0; index < ordered.length - 1; index += 1) {
    const startT = ordered[index]
    const endT = ordered[index + 1]
    if (endT - startT < 1e-6) continue
    const mid = interpolate(segment.start, segment.end, (startT + endT) / 2)
    if (pointInPolygon(mid, polygon)) continue
    fragments.push({
      start: interpolate(segment.start, segment.end, startT),
      end: interpolate(segment.start, segment.end, endT),
    })
  }
  return fragments
}

function transformedSegments(entity: CadWorkspaceEntity, dx: number, dy: number): Segment[] {
  if (entity.type === 'line' && entity.start && entity.end) {
    return [{
      start: { x: entity.start.x + dx, y: entity.start.y + dy },
      end: { x: entity.end.x + dx, y: entity.end.y + dy },
    }]
  }

  if (entity.type === 'polyline' && entity.points.length > 1) {
    const points = entity.points.map((point) => ({ x: point.x + dx, y: point.y + dy }))
    const segments: Segment[] = []
    for (let index = 0; index < points.length - 1; index += 1) {
      segments.push({ start: points[index], end: points[index + 1] })
    }
    return segments
  }

  return []
}

function renderOverflowFragments(view: CadWorkspaceView, dx: number, dy: number, polygon: CadWorkspacePoint[]) {
  const fragments: Segment[] = []
  for (const entity of view.entities) {
    for (const segment of transformedSegments(entity, dx, dy)) {
      fragments.push(...segmentOverflowFragments(segment, polygon))
    }
  }

  return (
    <g className="text-red-400">
      {fragments.map((fragment, index) => (
        <line
          key={`overflow-${index}`}
          x1={fragment.start.x}
          y1={fragment.start.y}
          x2={fragment.end.x}
          y2={fragment.end.y}
          stroke="currentColor"
          strokeWidth={7}
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      ))}
    </g>
  )
}

export function CadWorkspaceCanvas({ result }: CadWorkspaceCanvasProps) {
  const siteBox = result.site_plan.bbox
  const floorBox = result.floor_plan.bbox
  const overlayBox = resolveOverlayBBox(result)

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

  const shiftedBuildable = result.fit_summary?.buildable_bbox
    ? {
        ...result.fit_summary.buildable_bbox,
        x1: result.fit_summary.buildable_bbox.x1 + padding,
        x2: result.fit_summary.buildable_bbox.x2 + padding,
        y1: result.fit_summary.buildable_bbox.y1 + padding,
        y2: result.fit_summary.buildable_bbox.y2 + padding,
      }
    : null

  const shiftedBuildablePolygon = result.fit_summary?.buildable_polygon?.length
    ? result.fit_summary.buildable_polygon.map((point) => ({
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
          El site plan queda como base y el floor plan se ubica arriba en <span className="font-medium text-zinc-200">{result.canonical_unit}</span>, con cotas visuales para leer rápido si entra o no.
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
              {renderView(result.site_plan, siteTranslateX, siteTranslateY, 'text-emerald-300')}
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
              {renderView(result.floor_plan, floorTranslateX, floorTranslateY, 'text-cyan-300')}
              {shiftedBuildablePolygon && renderOverflowFragments(result.floor_plan, floorTranslateX, floorTranslateY, shiftedBuildablePolygon)}
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
