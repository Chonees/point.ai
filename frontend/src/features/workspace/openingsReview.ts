import type { OpeningAnnotation } from '../../types'

type UnknownAnnotation = Partial<OpeningAnnotation> & { type?: string }

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

export function isOpeningAnnotation(annotation: UnknownAnnotation): annotation is OpeningAnnotation {
  return (
    (annotation.type === 'door' || annotation.type === 'window')
    && typeof annotation.x1 === 'number'
    && typeof annotation.y1 === 'number'
    && typeof annotation.x2 === 'number'
    && typeof annotation.y2 === 'number'
  )
}
