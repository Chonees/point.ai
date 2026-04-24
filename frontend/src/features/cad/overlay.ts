import type {
  CadReviewArtifactData,
  CadWorkspaceBBox,
  CadWorkspaceEntity,
  CadWorkspaceFitSummary,
  CadWorkspacePoint,
  CadWorkspaceRoom,
} from './contracts'

export interface CadOverlaySegment {
  start: CadWorkspacePoint
  end: CadWorkspacePoint
}

export function formatMeasure(value?: number | null) {
  if (value == null) return 'N/D'
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}

export function formatFeetInches(value?: number | null) {
  if (value == null) return 'N/D'
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

export function formatArchitecturalMeasure(value?: number | null) {
  if (value == null) return 'N/D'
  return `${formatFeetInches(value)} · ${formatMeasure(value)} in`
}

export function formatRoomDimensions(room: CadWorkspaceRoom) {
  return `${formatFeetInches(room.width)} × ${formatFeetInches(room.height)}`
}

export function getFitVerdictText(fit: CadWorkspaceFitSummary | null) {
  if (!fit) return 'Review sin veredicto'
  if (fit.basis === 'buildable_polygon') {
    return fit.fits_within_buildable_polygon ? 'Entra en poligono construible' : 'No entra en poligono construible'
  }
  if (fit.fits_within_buildable_bbox === true) return 'Entra por bbox'
  if (fit.fits_within_buildable_bbox === false) return 'No entra por bbox'
  return 'Review sin veredicto'
}

export function resolveOverlayBBox(review: CadReviewArtifactData): CadWorkspaceBBox | null {
  const registeredFloorBox = review.fitSummary?.registered_footprint_bbox
  if (registeredFloorBox) return registeredFloorBox

  const floorBox = review.fitSummary?.footprint_bbox ?? review.floorPlan.bbox
  const buildableBox = review.fitSummary?.buildable_bbox
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

export function translatePoints(points: CadWorkspacePoint[], dx: number, dy: number): CadWorkspacePoint[] {
  return points.map((point) => ({
    x: point.x + dx,
    y: point.y + dy,
  }))
}

export function translateEntityPoints(entity: CadWorkspaceEntity, dx: number, dy: number): CadWorkspacePoint[] {
  if (entity.type.toLowerCase() === 'line' && entity.start && entity.end) {
    return [
      { x: entity.start.x + dx, y: entity.start.y + dy },
      { x: entity.end.x + dx, y: entity.end.y + dy },
    ]
  }

  return translatePoints(entity.points ?? [], dx, dy)
}

export function transformedSegments(entity: CadWorkspaceEntity, dx: number, dy: number): CadOverlaySegment[] {
  if (entity.type.toLowerCase() === 'line' && entity.start && entity.end) {
    return [{
      start: { x: entity.start.x + dx, y: entity.start.y + dy },
      end: { x: entity.end.x + dx, y: entity.end.y + dy },
    }]
  }

  if (entity.points.length > 1) {
    const points = translatePoints(entity.points, dx, dy)
    const segments: CadOverlaySegment[] = []
    for (let index = 0; index < points.length - 1; index += 1) {
      segments.push({ start: points[index], end: points[index + 1] })
    }
    return segments
  }

  return []
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

function segmentIntersectionParameter(segment: CadOverlaySegment, edge: CadOverlaySegment) {
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

export function segmentOverflowFragments(segment: CadOverlaySegment, polygon: CadWorkspacePoint[]): CadOverlaySegment[] {
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

  const fragments: CadOverlaySegment[] = []
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

export function roomVisual(roomName: string, measurementSource: string) {
  const palette = [
    { fill: 'rgba(34,211,238,0.16)', stroke: '#67e8f9' },
    { fill: 'rgba(168,85,247,0.16)', stroke: '#c084fc' },
    { fill: 'rgba(250,204,21,0.16)', stroke: '#fde047' },
    { fill: 'rgba(52,211,153,0.16)', stroke: '#6ee7b7' },
    { fill: 'rgba(251,146,60,0.16)', stroke: '#fdba74' },
    { fill: 'rgba(244,114,182,0.16)', stroke: '#f9a8d4' },
  ]

  const hash = roomName.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0)
  const base = palette[hash % palette.length]
  const approximate = measurementSource !== 'room_region'

  return {
    ...base,
    fillOpacity: approximate ? 0.11 : 0.18,
    dash: approximate ? '12 8' : undefined,
  }
}
