import type { Annotation, AnnotationType } from '../../types'
import { COLORS } from './constants'

interface View { offsetX: number; offsetY: number; scale: number }
interface DrawingState {
  active: boolean
  start: { x: number; y: number } | null
  cursor: { x: number; y: number } | null
  tool: AnnotationType
}
interface SnapState { x: number; y: number; snapped: boolean }

const SLAB_ANGLES: Record<string, number> = { up: -Math.PI / 2, down: Math.PI / 2, left: Math.PI, right: 0 }

export function renderCanvas(
  canvas: HTMLCanvasElement,
  img: HTMLImageElement,
  v: View,
  anns: Annotation[],
  hoveredIdx: number,
  snap: SnapState,
  drawing: DrawingState,
  regionOverlay?: HTMLImageElement | HTMLCanvasElement | null,
): void {
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  // Clear in screen space
  ctx.setTransform(1, 0, 0, 1, 0, 0)
  ctx.clearRect(0, 0, canvas.width, canvas.height)

  // Dotted grid background
  ctx.fillStyle = '#111111'
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  const dotSpacing = 20
  ctx.fillStyle = '#2a2a2a'
  for (let dx = (v.offsetX % dotSpacing + dotSpacing) % dotSpacing; dx < canvas.width; dx += dotSpacing) {
    for (let dy = (v.offsetY % dotSpacing + dotSpacing) % dotSpacing; dy < canvas.height; dy += dotSpacing) {
      ctx.beginPath()
      ctx.arc(dx, dy, 1, 0, Math.PI * 2)
      ctx.fill()
    }
  }

  // Apply pan+zoom
  ctx.setTransform(v.scale, 0, 0, v.scale, v.offsetX, v.offsetY)

  // Draw image at origin in world space
  ctx.drawImage(img, 0, 0)

  // Draw region overlay (colored room zones from flood-fill)
  if (regionOverlay) {
    ctx.drawImage(regionOverlay, 0, 0)
  }

  // Draw committed annotations
  for (const ann of anns) {
    const isAuto = ann._source === 'ensemble_cubicasa'
    if (ann.type === 'eraser') {
      ctx.fillStyle = 'rgba(0, 0, 0, 0.7)'
      ctx.fillRect(ann.x1, ann.y1, ann.x2 - ann.x1, ann.y2 - ann.y1)
      ctx.strokeStyle = '#ff4444'
      ctx.lineWidth = 1 / v.scale
      ctx.setLineDash([3 / v.scale, 3 / v.scale])
      ctx.strokeRect(ann.x1, ann.y1, ann.x2 - ann.x1, ann.y2 - ann.y1)
      ctx.setLineDash([])
    } else if (ann.type === 'label') {
      // Room label: name + sqft centered at point — world-space (scales with zoom)
      const lx = ann.x1, ly = ann.y1
      const name = ann.roomName || 'ROOM'
      const sqft = ann.sqft ? `${ann.sqft} SQ FT` : ''

      const nameSize = 32
      const sqftSize = 22
      const pad = 12

      // White background for readability
      const bw = Math.max(name.length, sqft.length) * nameSize * 0.6 + pad * 2
      const bh = (sqft ? nameSize + sqftSize + pad : nameSize) + pad * 2
      const bx = lx - bw / 2, by = ly - bh / 2
      ctx.fillStyle = 'rgba(255, 255, 255, 0.85)'
      ctx.strokeStyle = '#333333'
      ctx.lineWidth = 3
      ctx.beginPath()
      ctx.roundRect(bx, by, bw, bh, 6)
      ctx.fill()
      ctx.stroke()

      // Room name — black
      ctx.fillStyle = '#000000'
      ctx.font = `bold ${nameSize}px sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(name.toUpperCase(), lx, sqft ? ly - sqftSize * 0.4 : ly)

      // Sqft — dark gray
      if (sqft) {
        ctx.fillStyle = '#444444'
        ctx.font = `${sqftSize}px sans-serif`
        ctx.fillText(sqft, lx, ly + nameSize * 0.5)
      }

      ctx.textAlign = 'start'
      ctx.textBaseline = 'alphabetic'
    } else {
      // AI-detected annotations: dashed + slightly transparent
      if (isAuto) {
        ctx.setLineDash([12, 8])
        ctx.globalAlpha = 0.8
      }
      // Separator lines: white, same thickness as doors/windows
      const isSeparator = (ann.type as string) === 'separator'
      // Wall colors: 4" = cyan, 6" = gray
      const isWall6 = ann.type === 'wall' && ann.thickness === 6
      // Doors/windows without direction = yellow (needs attention), with = green (done)
      const color = isSeparator
        ? '#33ff66'
        : ann.type === 'wall'
          ? (isWall6 ? '#999999' : '#00ccff')
          : (ann.type === 'door' || ann.type === 'window')
            ? (ann.swing ? '#33ff66' : '#ffcc00')
            : COLORS[ann.type]
      const lw = ann.type === 'wall' ? (isWall6 ? 12 : 6) : 3
      ctx.strokeStyle = color
      ctx.lineWidth = lw

      if (ann.type === 'door' && ann.swing) {
        // Draw door: slab (2 parallel lines) + bezier arc
        const openingW = Math.sqrt((ann.x2 - ann.x1) ** 2 + (ann.y2 - ann.y1) ** 2)
        const arcR = ann.arcRadius ?? openingW
        const hx = ann.x1, hy = ann.y1
        const ds = 3

        const sA = SLAB_ANGLES[ann.swing]
        const oA = Math.atan2(ann.y2 - ann.y1, ann.x2 - ann.x1)

        const tipX = hx + Math.cos(sA) * arcR, tipY = hy + Math.sin(sA) * arcR
        const odx = Math.cos(oA) * ds, ody = Math.sin(oA) * ds

        // Slab: 2 parallel lines from hinge to tip
        ctx.beginPath()
        ctx.moveTo(hx, hy); ctx.lineTo(tipX, tipY)
        ctx.moveTo(hx + odx, hy + ody); ctx.lineTo(tipX + odx, tipY + ody)
        ctx.stroke()

        // Arc: bezier curve from slab tip to opening endpoint
        const cpX = tipX + (ann.x2 - hx), cpY = tipY + (ann.y2 - hy)
        ctx.beginPath()
        ctx.moveTo(tipX, tipY)
        ctx.quadraticCurveTo(cpX, cpY, ann.x2, ann.y2)
        ctx.stroke()
      } else if (ann.type === 'window') {
        // Draw window: 3 parallel lines centered on wall + end caps + sill
        const adx = Math.abs(ann.x2 - ann.x1)
        const ady = Math.abs(ann.y2 - ann.y1)
        const sp = 4
        const sillDist = 16
        // swing indicates exterior direction
        const ext = ann.swing ?? 'up'
        if (adx >= ady) {
          const xLo = Math.min(ann.x1, ann.x2), xHi = Math.max(ann.x1, ann.x2)
          const yM = (ann.y1 + ann.y2) / 2
          // 3 lines centered
          for (const off of [-sp, 0, sp]) {
            ctx.beginPath(); ctx.moveTo(xLo, yM + off); ctx.lineTo(xHi, yM + off); ctx.stroke()
          }
          // End caps
          ctx.beginPath()
          ctx.moveTo(xLo, yM - sp); ctx.lineTo(xLo, yM + sp)
          ctx.moveTo(xHi, yM - sp); ctx.lineTo(xHi, yM + sp)
          ctx.stroke()
          // Sill toward exterior
          const sillY = ext === 'up' ? yM + sillDist : yM - sillDist
          ctx.beginPath(); ctx.moveTo(xLo, sillY); ctx.lineTo(xHi, sillY); ctx.stroke()
        } else {
          const yLo = Math.min(ann.y1, ann.y2), yHi = Math.max(ann.y1, ann.y2)
          const xM = (ann.x1 + ann.x2) / 2
          // 3 lines centered
          for (const off of [-sp, 0, sp]) {
            ctx.beginPath(); ctx.moveTo(xM + off, yLo); ctx.lineTo(xM + off, yHi); ctx.stroke()
          }
          // End caps
          ctx.beginPath()
          ctx.moveTo(xM - sp, yLo); ctx.lineTo(xM + sp, yLo)
          ctx.moveTo(xM - sp, yHi); ctx.lineTo(xM + sp, yHi)
          ctx.stroke()
          // Sill toward exterior
          const sillX = ext === 'left' ? xM + sillDist : xM - sillDist
          ctx.beginPath(); ctx.moveTo(sillX, yLo); ctx.lineTo(sillX, yHi); ctx.stroke()
        }
      } else if (ann.type === 'wall') {
        // Walls: black border + colored fill
        ctx.beginPath()
        ctx.moveTo(ann.x1, ann.y1)
        ctx.lineTo(ann.x2, ann.y2)
        // Black border (wider)
        ctx.strokeStyle = '#000000'
        ctx.lineWidth = lw + 6
        ctx.stroke()
        // Colored fill (original width)
        ctx.strokeStyle = color
        ctx.lineWidth = lw
        ctx.beginPath()
        ctx.moveTo(ann.x1, ann.y1)
        ctx.lineTo(ann.x2, ann.y2)
        ctx.stroke()
      } else {
        // Doors without swing: simple line
        ctx.beginPath()
        ctx.moveTo(ann.x1, ann.y1)
        ctx.lineTo(ann.x2, ann.y2)
        ctx.stroke()
      }

      ctx.fillStyle = color
      ctx.font = `bold 22px monospace`
      const label = ann.type === 'wall' && ann.thickness ? `${ann.thickness}"` : ann.type[0].toUpperCase()
      ctx.fillText(label, Math.min(ann.x1, ann.x2) - 28, (ann.y1 + ann.y2) / 2 + 8)

      // Endpoint handles on hovered annotation
      if (hoveredIdx === anns.indexOf(ann)) {
        const er = 4 / v.scale
        const handles: [number, number][] = [[ann.x1, ann.y1], [ann.x2, ann.y2]]
        if (ann.type === 'door' && ann.swing) {
          const arcR = ann.arcRadius ?? Math.sqrt((ann.x2 - ann.x1) ** 2 + (ann.y2 - ann.y1) ** 2)
          const sA = SLAB_ANGLES[ann.swing]
          handles.push([ann.x1 + Math.cos(sA) * arcR, ann.y1 + Math.sin(sA) * arcR])
        }
        for (const [px, py] of handles) {
          ctx.fillStyle = '#ffffff'
          ctx.strokeStyle = color
          ctx.lineWidth = 1.5 / v.scale
          ctx.setLineDash([])
          ctx.beginPath()
          ctx.arc(px, py, er, 0, Math.PI * 2)
          ctx.fill()
          ctx.stroke()
        }
      }

      // Reset dash and alpha
      if (isAuto) {
        ctx.setLineDash([])
        ctx.globalAlpha = 1.0
      }
    }
  }

  // Fill junction gaps where 2+ walls share an endpoint
  const wallAnns = anns.filter(a => a.type === 'wall')
  if (wallAnns.length > 1) {
    const snapDist = 4
    const seen = new Set<string>()
    for (const w of wallAnns) {
      const wLw = w.thickness === 6 ? 12 : 6
      for (const [px, py] of [[w.x1, w.y1], [w.x2, w.y2]] as [number, number][]) {
        const key = `${Math.round(px)},${Math.round(py)}`
        if (seen.has(key)) continue
        let count = 0
        for (const other of wallAnns) {
          if (other === w) continue
          for (const [ox, oy] of [[other.x1, other.y1], [other.x2, other.y2]] as [number, number][]) {
            if (Math.abs(px - ox) <= snapDist && Math.abs(py - oy) <= snapDist) { count++; break }
          }
          if (count > 0) break
        }
        if (count > 0) {
          ctx.fillStyle = w.thickness === 6 ? '#999999' : '#00ccff'
          ctx.beginPath()
          ctx.arc(px, py, wLw / 2, 0, Math.PI * 2)
          ctx.fill()
          seen.add(key)
        }
      }
    }
  }

  // Hover delete indicator: draw × on hovered annotation
  if (hoveredIdx >= 0 && hoveredIdx < anns.length) {
    const ha = anns[hoveredIdx]
    const cx = (ha.x1 + ha.x2) / 2
    const cy = (ha.y1 + ha.y2) / 2
    const r = 8 / v.scale
    ctx.fillStyle = 'rgba(220, 40, 40, 0.9)'
    ctx.beginPath()
    ctx.arc(cx, cy, r, 0, Math.PI * 2)
    ctx.fill()
    ctx.strokeStyle = '#ffffff'
    ctx.lineWidth = 1.5 / v.scale
    ctx.setLineDash([])
    const d = r * 0.5
    ctx.beginPath()
    ctx.moveTo(cx - d, cy - d)
    ctx.lineTo(cx + d, cy + d)
    ctx.moveTo(cx + d, cy - d)
    ctx.lineTo(cx - d, cy + d)
    ctx.stroke()
  }

  // Snap indicator
  if (snap.snapped) {
    ctx.strokeStyle = '#44aaff'
    ctx.fillStyle = 'rgba(68, 170, 255, 0.3)'
    ctx.lineWidth = 1.5 / v.scale
    ctx.setLineDash([])
    ctx.beginPath()
    ctx.arc(snap.x, snap.y, 6 / v.scale, 0, Math.PI * 2)
    ctx.fill()
    ctx.stroke()
  }

  // Live preview overlay while dragging
  if (drawing.active && drawing.start && drawing.cursor) {
    const sp = drawing.start
    const cp = drawing.cursor
    ctx.setTransform(v.scale, 0, 0, v.scale, v.offsetX, v.offsetY)

    if (drawing.tool === 'eraser') {
      const rx1 = Math.min(sp.x, cp.x)
      const ry1 = Math.min(sp.y, cp.y)
      const rw = Math.abs(cp.x - sp.x)
      const rh = Math.abs(cp.y - sp.y)
      ctx.strokeStyle = '#ff4444'
      ctx.lineWidth = 1 / v.scale
      ctx.setLineDash([4 / v.scale, 4 / v.scale])
      ctx.strokeRect(rx1, ry1, rw, rh)
      ctx.fillStyle = 'rgba(255, 0, 0, 0.1)'
      ctx.fillRect(rx1, ry1, rw, rh)
      ctx.setLineDash([])
    } else if (drawing.tool === 'paint') {
      // Separator preview: green dashed line
      ctx.strokeStyle = '#33ff66'
      ctx.lineWidth = 4 / v.scale
      ctx.globalAlpha = 0.8
      ctx.setLineDash([6 / v.scale, 4 / v.scale])
      ctx.beginPath()
      ctx.moveTo(sp.x, sp.y)
      ctx.lineTo(cp.x, cp.y)
      ctx.stroke()
      ctx.setLineDash([])
      ctx.globalAlpha = 1.0

      const dotR = 4 / v.scale
      ctx.fillStyle = '#33ff66'
      ctx.beginPath()
      ctx.arc(sp.x, sp.y, dotR, 0, Math.PI * 2)
      ctx.fill()
      ctx.beginPath()
      ctx.arc(cp.x, cp.y, dotR, 0, Math.PI * 2)
      ctx.fill()
    } else {
      ctx.strokeStyle = COLORS[drawing.tool]
      ctx.lineWidth = (drawing.tool === 'wall' ? 6 : 4) / v.scale
      ctx.globalAlpha = 0.6
      ctx.beginPath()
      ctx.moveTo(sp.x, sp.y)
      ctx.lineTo(cp.x, cp.y)
      ctx.stroke()
      ctx.globalAlpha = 1.0

      const dotR = 3 / v.scale
      ctx.fillStyle = COLORS[drawing.tool]
      ctx.beginPath()
      ctx.arc(sp.x, sp.y, dotR, 0, Math.PI * 2)
      ctx.fill()
      ctx.beginPath()
      ctx.arc(cp.x, cp.y, dotR, 0, Math.PI * 2)
      ctx.fill()

      const lenPx = Math.round(Math.sqrt((cp.x - sp.x) ** 2 + (cp.y - sp.y) ** 2))
      ctx.fillStyle = '#ffffff'
      ctx.font = `bold ${11 / v.scale}px monospace`
      ctx.fillText(`${lenPx}px`, (sp.x + cp.x) / 2 + 6 / v.scale, (sp.y + cp.y) / 2 - 6 / v.scale)
    }
  }
}
