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

export function hitTestAnnotation(wx: number, wy: number, annotations: Annotation[], scale: number): number {
  const threshold = 12 / scale
  for (let i = annotations.length - 1; i >= 0; i--) {
    const a = annotations[i]
    if (a.type === 'eraser') {
      const rx1 = Math.min(a.x1, a.x2), ry1 = Math.min(a.y1, a.y2)
      const rx2 = Math.max(a.x1, a.x2), ry2 = Math.max(a.y1, a.y2)
      if (wx >= rx1 - threshold && wx <= rx2 + threshold && wy >= ry1 - threshold && wy <= ry2 + threshold) return i
    } else if (a.type === 'door' && a.swing) {
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
  const threshold = 10 / scale
  for (let i = annotations.length - 1; i >= 0; i--) {
    const a = annotations[i]
    if (a.type === 'eraser') continue
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
  const threshold = 8 / scale
  let bestDist = threshold
  let snap = { x: wx, y: wy, snapped: false }
  for (let i = 0; i < annotations.length; i++) {
    if (i === skipIdx) continue
    const a = annotations[i]
    if (a.type === 'eraser') continue
    for (const [px, py] of [[a.x1, a.y1], [a.x2, a.y2]] as [number, number][]) {
      const d = Math.sqrt((wx - px) ** 2 + (wy - py) ** 2)
      if (d < bestDist) {
        bestDist = d
        snap = { x: px, y: py, snapped: true }
      }
    }
  }
  return snap
}
