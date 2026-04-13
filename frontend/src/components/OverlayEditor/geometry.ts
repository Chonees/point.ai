import type { Annotation } from '../../types'

const SLAB_ANGLES: Record<string, number> = { up: -Math.PI / 2, down: Math.PI / 2, left: Math.PI, right: 0 }

export function distToSeg(px: number, py: number, x1: number, y1: number, x2: number, y2: number): number {
  const dx = x2 - x1, dy = y2 - y1
  const lenSq = dx * dx + dy * dy
  if (lenSq < 1) return Math.sqrt((px - x1) ** 2 + (py - y1) ** 2)
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lenSq))
  return Math.sqrt((px - (x1 + t * dx)) ** 2 + (py - (y1 + t * dy)) ** 2)
}

export function angleInArc(angle: number, sA: number, oA: number): boolean {
  const norm = (a: number) => ((a % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI)
  const a = norm(angle), s = norm(sA), o = norm(oA)
  const cw = ((o - s) + 2 * Math.PI) % (2 * Math.PI)
  if (cw <= Math.PI) {
    return ((a - s) + 2 * Math.PI) % (2 * Math.PI) <= cw
  }
  const ccw = 2 * Math.PI - cw
  return ((s - a) + 2 * Math.PI) % (2 * Math.PI) <= ccw
}

const isCoarse = typeof window !== 'undefined' && window.matchMedia?.('(pointer: coarse)')?.matches

export function hitTestAnnotation(wx: number, wy: number, annotations: Annotation[], scale: number): number {
  const threshold = (isCoarse ? 24 : 12) / scale
  for (let i = annotations.length - 1; i >= 0; i--) {
    const a = annotations[i]
    if (a.type === 'door' && a.swing) {
      const hx = a.x1, hy = a.y1
      const openingW = Math.sqrt((a.x2 - a.x1) ** 2 + (a.y2 - a.y1) ** 2)
      const arcR = a.arcRadius ?? openingW
      const sA = SLAB_ANGLES[a.swing]
      const tipX = hx + Math.cos(sA) * arcR, tipY = hy + Math.sin(sA) * arcR

      if (distToSeg(wx, wy, hx, hy, tipX, tipY) < threshold) return i
      if (distToSeg(wx, wy, a.x1, a.y1, a.x2, a.y2) < threshold) return i

      const distFromHinge = Math.sqrt((wx - hx) ** 2 + (wy - hy) ** 2)
      if (Math.abs(distFromHinge - arcR) < threshold) {
        const ptAngle = Math.atan2(wy - hy, wx - hx)
        const oA = Math.atan2(a.y2 - a.y1, a.x2 - a.x1)
        if (angleInArc(ptAngle, sA, oA)) return i
      }
    } else {
      const dx = a.x2 - a.x1, dy = a.y2 - a.y1
      const lenSq = dx * dx + dy * dy
      if (lenSq < 1) continue
      const t = Math.max(0, Math.min(1, ((wx - a.x1) * dx + (wy - a.y1) * dy) / lenSq))
      const px = a.x1 + t * dx, py = a.y1 + t * dy
      const dist = Math.sqrt((wx - px) ** 2 + (wy - py) ** 2)
      if (dist < threshold) return i
    }
  }
  return -1
}

export function hitTestEndpoint(wx: number, wy: number, annotations: Annotation[], scale: number): { idx: number; endpoint: 'start' | 'end' | 'arc' } | null {
  const threshold = (isCoarse ? 20 : 10) / scale
  for (let i = annotations.length - 1; i >= 0; i--) {
    const a = annotations[i]
    if (a.type === 'door' && a.swing) {
      const arcR = a.arcRadius ?? Math.sqrt((a.x2 - a.x1) ** 2 + (a.y2 - a.y1) ** 2)
      const sA = SLAB_ANGLES[a.swing]
      const tipX = a.x1 + Math.cos(sA) * arcR
      const tipY = a.y1 + Math.sin(sA) * arcR
      const dt = Math.sqrt((wx - tipX) ** 2 + (wy - tipY) ** 2)
      if (dt < threshold) return { idx: i, endpoint: 'arc' }
    }
    const d1 = Math.sqrt((wx - a.x1) ** 2 + (wy - a.y1) ** 2)
    if (d1 < threshold) return { idx: i, endpoint: 'start' }
    const d2 = Math.sqrt((wx - a.x2) ** 2 + (wy - a.y2) ** 2)
    if (d2 < threshold) return { idx: i, endpoint: 'end' }
  }
  return null
}

export function snapToEndpoint(wx: number, wy: number, annotations: Annotation[], scale: number, skipIdx: number = -1): { x: number; y: number; snapped: boolean } {
  const threshold = (isCoarse ? 24 : 14) / scale
  let bestDist = threshold
  let snap = { x: wx, y: wy, snapped: false }
  for (let i = 0; i < annotations.length; i++) {
    if (i === skipIdx) continue
    const a = annotations[i]
    // Endpoints first (higher priority — tighter snap wins)
    for (const [px, py] of [[a.x1, a.y1], [a.x2, a.y2]] as [number, number][]) {
      const d = Math.sqrt((wx - px) ** 2 + (wy - py) ** 2)
      if (d < bestDist) {
        bestDist = d
        snap = { x: px, y: py, snapped: true }
      }
    }
    // Perpendicular projection onto segment (walls, windows, separators)
    // For walls: snap to the EDGE (half line width offset), not the centerline
    if (a.type === 'wall' || a.type === 'window' || (a.type as string) === 'separator') {
      const dx = a.x2 - a.x1, dy = a.y2 - a.y1
      const lenSq = dx * dx + dy * dy
      if (lenSq < 1) continue
      const len = Math.sqrt(lenSq)
      const t = Math.max(0, Math.min(1, ((wx - a.x1) * dx + (wy - a.y1) * dy) / lenSq))
      const cx = a.x1 + t * dx, cy = a.y1 + t * dy // centerline point

      // Offset to wall edge for walls (perpendicular normal × half line width)
      let sx = cx, sy = cy
      if (a.type === 'wall') {
        const halfLw = (a.thickness === 6 ? 8 : 4) / 2
        // Perpendicular unit normal: (-dy, dx) / len
        const nx = -dy / len, ny = dx / len
        // Which side is the cursor on?
        const side = (wx - cx) * nx + (wy - cy) * ny
        sx = cx + (side >= 0 ? 1 : -1) * nx * halfLw
        sy = cy + (side >= 0 ? 1 : -1) * ny * halfLw
      }

      const d = Math.sqrt((wx - sx) ** 2 + (wy - sy) ** 2)
      if (d < bestDist) {
        bestDist = d
        snap = { x: sx, y: sy, snapped: true }
      }
    }
  }
  return snap
}

/**
 * Post-process auto-generated annotations so that wall endpoints
 * that land on another wall's centerline get pushed to the edge instead.
 *
 * For each wall endpoint, if it's near a perpendicular wall's centerline,
 * offset it outward by half that wall's visual line width.
 */
export function snapEndpointsToWallEdges(annotations: Annotation[]): Annotation[] {
  const walls = annotations.filter(a => a.type === 'wall')
  if (walls.length < 2) return annotations

  const NEAR = 6 // max distance (px) from centerline to consider "on the wall"

  return annotations.map(ann => {
    if (ann.type !== 'wall') return ann

    let { x1, y1, x2, y2 } = ann
    // Try to adjust each endpoint
    ;([
      { px: x1, py: y1, isStart: true },
      { px: x2, py: y2, isStart: false },
    ] as const).forEach(({ px, py, isStart }) => {
      for (const other of walls) {
        if (other === ann) continue
        const dx = other.x2 - other.x1, dy = other.y2 - other.y1
        const lenSq = dx * dx + dy * dy
        if (lenSq < 1) continue
        const len = Math.sqrt(lenSq)

        // Project endpoint onto other wall's centerline
        const t = ((px - other.x1) * dx + (py - other.y1) * dy) / lenSq
        if (t < -0.01 || t > 1.01) continue // not within the segment

        const cx = other.x1 + t * dx, cy = other.y1 + t * dy
        const dist = Math.sqrt((px - cx) ** 2 + (py - cy) ** 2)

        if (dist > NEAR) continue // not close to this wall's centerline

        // Endpoint is on the centerline — push to edge
        const halfLw = (other.thickness === 6 ? 8 : 4) / 2
        const nx = -dy / len, ny = dx / len

        // Direction from centerline toward the body of `ann`
        const otherEnd = isStart ? { x: ann.x2, y: ann.y2 } : { x: ann.x1, y: ann.y1 }
        const side = (otherEnd.x - cx) * nx + (otherEnd.y - cy) * ny
        const sign = side >= 0 ? 1 : -1

        if (isStart) {
          x1 = cx + sign * nx * halfLw
          y1 = cy + sign * ny * halfLw
        } else {
          x2 = cx + sign * nx * halfLw
          y2 = cy + sign * ny * halfLw
        }
        break // only adjust to the first matching wall
      }
    })

    if (x1 === ann.x1 && y1 === ann.y1 && x2 === ann.x2 && y2 === ann.y2) return ann
    return { ...ann, x1, y1, x2, y2 }
  })
}
