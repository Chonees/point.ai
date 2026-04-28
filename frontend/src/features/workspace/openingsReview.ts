import type { OpeningAnnotation, SwingDir } from '../../types'

type UnknownAnnotation = Partial<OpeningAnnotation> & { type?: string }

export interface OpeningPreviewLine {
  x1: number
  y1: number
  x2: number
  y2: number
}

export interface OpeningPreviewArc {
  startX: number
  startY: number
  controlX: number
  controlY: number
  endX: number
  endY: number
}

export interface OpeningPreviewGeometry {
  lines: OpeningPreviewLine[]
  arc: OpeningPreviewArc | null
}

const SLAB_ANGLES: Record<SwingDir, number> = {
  up: -Math.PI / 2,
  down: Math.PI / 2,
  left: Math.PI,
  right: 0,
}

export function filterOpeningAnnotations(
  annotations: UnknownAnnotation[] | undefined | null,
): OpeningAnnotation[] {
  return (annotations ?? []).filter(isOpeningAnnotation).map((annotation) => ({
    type: annotation.type,
    x1: Number(annotation.x1),
    y1: Number(annotation.y1),
    x2: Number(annotation.x2),
    y2: Number(annotation.y2),
    swing: annotation.swing,
    _source: annotation._source,
  }))
}

export function translateOpeningAnnotation(
  annotation: OpeningAnnotation,
  delta: { dx: number; dy: number },
): OpeningAnnotation {
  return {
    ...annotation,
    x1: annotation.x1 + delta.dx,
    y1: annotation.y1 + delta.dy,
    x2: annotation.x2 + delta.dx,
    y2: annotation.y2 + delta.dy,
  }
}

export function getOpeningSwingOptions(annotation: OpeningAnnotation): SwingDir[] {
  const adx = Math.abs(annotation.x2 - annotation.x1)
  const ady = Math.abs(annotation.y2 - annotation.y1)
  return ady >= adx ? ['left', 'right'] : ['up', 'down']
}

export function setOpeningSwing(
  annotation: OpeningAnnotation,
  swing: SwingDir,
): OpeningAnnotation {
  return {
    ...annotation,
    swing,
  }
}

export function getOpeningMoveHandle(annotation: OpeningAnnotation): { x: number; y: number } {
  return {
    x: (annotation.x1 + annotation.x2) / 2,
    y: (annotation.y1 + annotation.y2) / 2,
  }
}

export function getOpeningSwingTargetPoint(
  annotation: OpeningAnnotation,
  swing: SwingDir,
): { x: number; y: number } {
  const center = getOpeningMoveHandle(annotation)
  const length = Math.max(
    28,
    Math.sqrt(((annotation.x2 - annotation.x1) ** 2) + ((annotation.y2 - annotation.y1) ** 2)) * 0.55,
  )

  if (swing === 'left') return { x: center.x - length, y: center.y }
  if (swing === 'right') return { x: center.x + length, y: center.y }
  if (swing === 'up') return { x: center.x, y: center.y - length }
  return { x: center.x, y: center.y + length }
}

export function getOpeningPreviewGeometry(
  annotation: OpeningAnnotation,
  swing: SwingDir,
): OpeningPreviewGeometry {
  if (annotation.type === 'door') {
    return getDoorPreviewGeometry(annotation, swing)
  }
  return getWindowPreviewGeometry(annotation, swing)
}

function getDoorPreviewGeometry(
  annotation: OpeningAnnotation,
  swing: SwingDir,
): OpeningPreviewGeometry {
  const openingWidth = Math.sqrt(((annotation.x2 - annotation.x1) ** 2) + ((annotation.y2 - annotation.y1) ** 2))
  const arcRadius = openingWidth
  const hingeX = annotation.x1
  const hingeY = annotation.y1
  const slabOffset = 3

  const swingAngle = SLAB_ANGLES[swing]
  const openingAngle = Math.atan2(annotation.y2 - annotation.y1, annotation.x2 - annotation.x1)
  const tipX = hingeX + Math.cos(swingAngle) * arcRadius
  const tipY = hingeY + Math.sin(swingAngle) * arcRadius
  const offsetX = Math.cos(openingAngle) * slabOffset
  const offsetY = Math.sin(openingAngle) * slabOffset

  return {
    lines: [
      { x1: hingeX, y1: hingeY, x2: tipX, y2: tipY },
      { x1: hingeX + offsetX, y1: hingeY + offsetY, x2: tipX + offsetX, y2: tipY + offsetY },
    ],
    arc: {
      startX: tipX,
      startY: tipY,
      controlX: tipX + (annotation.x2 - hingeX),
      controlY: tipY + (annotation.y2 - hingeY),
      endX: annotation.x2,
      endY: annotation.y2,
    },
  }
}

function getWindowPreviewGeometry(
  annotation: OpeningAnnotation,
  swing: SwingDir,
): OpeningPreviewGeometry {
  const adx = Math.abs(annotation.x2 - annotation.x1)
  const ady = Math.abs(annotation.y2 - annotation.y1)
  const spacer = 4
  const sillDistance = 16

  if (adx >= ady) {
    const xLo = Math.min(annotation.x1, annotation.x2)
    const xHi = Math.max(annotation.x1, annotation.x2)
    const yMid = (annotation.y1 + annotation.y2) / 2
    const sillY = swing === 'up' ? yMid + sillDistance : yMid - sillDistance

    return {
      lines: [
        { x1: xLo, y1: yMid - spacer, x2: xHi, y2: yMid - spacer },
        { x1: xLo, y1: yMid, x2: xHi, y2: yMid },
        { x1: xLo, y1: yMid + spacer, x2: xHi, y2: yMid + spacer },
        { x1: xLo, y1: yMid - spacer, x2: xLo, y2: yMid + spacer },
        { x1: xHi, y1: yMid - spacer, x2: xHi, y2: yMid + spacer },
        { x1: xLo, y1: sillY, x2: xHi, y2: sillY },
      ],
      arc: null,
    }
  }

  const yLo = Math.min(annotation.y1, annotation.y2)
  const yHi = Math.max(annotation.y1, annotation.y2)
  const xMid = (annotation.x1 + annotation.x2) / 2
  const sillX = swing === 'left' ? xMid + sillDistance : xMid - sillDistance

  return {
    lines: [
      { x1: xMid - spacer, y1: yLo, x2: xMid - spacer, y2: yHi },
      { x1: xMid, y1: yLo, x2: xMid, y2: yHi },
      { x1: xMid + spacer, y1: yLo, x2: xMid + spacer, y2: yHi },
      { x1: xMid - spacer, y1: yLo, x2: xMid + spacer, y2: yLo },
      { x1: xMid - spacer, y1: yHi, x2: xMid + spacer, y2: yHi },
      { x1: sillX, y1: yLo, x2: sillX, y2: yHi },
    ],
    arc: null,
  }
}

export function isOpeningAnnotation(annotation: UnknownAnnotation): annotation is OpeningAnnotation {
  return (
    (annotation.type === 'door' || annotation.type === 'window')
    && typeof annotation.x1 === 'number'
    && typeof annotation.y1 === 'number'
    && typeof annotation.x2 === 'number'
    && typeof annotation.y2 === 'number'
  )
}
