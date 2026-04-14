import type { Annotation } from '../types'
import { inchesToFeetInches } from './architecturalFormat'

/**
 * When a wall's geometry changes, re-anchor and re-measure every dimension
 * annotation that references it.
 *
 * Mirrors the backend `compute_dimension_annotations` recompute step but
 * runs locally for instant feedback in the 2D editor. For locked dimensions
 * (user edited the value manually) we still update the span endpoints so the
 * cota visually follows the wall, but leave valueText untouched.
 *
 * This is intentionally simple — it only handles axis-aligned dimensions
 * (exterior + window_chain). Interior/diagonal dimensions are Phase 2.
 */
export function recomputeDimension(
  dim: Annotation,
  annotations: readonly Annotation[],
  scaleIpp: number,
): Annotation {
  if (dim.type !== 'dimension') return dim
  if (!dim.wallIds || dim.wallIds.length === 0) return dim

  const anchorWalls = dim.wallIds
    .map((id) => annotations.find((a) => a.id === id && a.type === 'wall'))
    .filter((w): w is Annotation => !!w)

  if (anchorWalls.length === 0) return dim

  // Rebuild the span from the anchor walls' current geometry, using the
  // dimension's orientation to decide which axis is the "along" and which
  // is the "coord" (perpendicular) axis.
  const orientation = dim.orientation ?? 'H'

  let coord: number
  let alongValues: number[]
  if (orientation === 'H') {
    // Horizontal wall: coord is the y of the wall, along is x.
    coord =
      anchorWalls.reduce((sum, w) => sum + (w.y1 + w.y2) / 2, 0) /
      anchorWalls.length
    alongValues = anchorWalls.flatMap((w) => [w.x1, w.x2])
  } else {
    coord =
      anchorWalls.reduce((sum, w) => sum + (w.x1 + w.x2) / 2, 0) /
      anchorWalls.length
    alongValues = anchorWalls.flatMap((w) => [w.y1, w.y2])
  }

  // For exterior dims we use the full span; for window_chain we keep the
  // original endpoints (which are tied to window centers, not walls) and
  // only adjust the perpendicular coord.
  let x1: number, y1: number, x2: number, y2: number

  if (dim.subtype === 'exterior') {
    const alongMin = Math.min(...alongValues)
    const alongMax = Math.max(...alongValues)
    if (orientation === 'H') {
      x1 = alongMin
      x2 = alongMax
      y1 = coord
      y2 = coord
    } else {
      x1 = coord
      x2 = coord
      y1 = alongMin
      y2 = alongMax
    }
  } else {
    // window_chain — preserve along-axis endpoints, update perpendicular.
    if (orientation === 'H') {
      x1 = dim.x1
      x2 = dim.x2
      y1 = coord
      y2 = coord
    } else {
      y1 = dim.y1
      y2 = dim.y2
      x1 = coord
      x2 = coord
    }
  }

  // Use Euclidean distance so diagonal dimensions measure correctly.
  const spanPx = Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
  const spanInches = spanPx * (scaleIpp || 0)

  const next: Annotation = {
    ...dim,
    x1,
    y1,
    x2,
    y2,
  }

  if (scaleIpp && scaleIpp > 0) {
    next.valueInches = spanInches
    if (!dim.locked) {
      next.valueText = inchesToFeetInches(spanInches)
    }
  }

  return next
}

/**
 * Run recompute across a full annotation list — typically called after any
 * wall edit. Non-dimension annotations pass through unchanged.
 */
export function recomputeDimensionsFor(
  annotations: Annotation[],
  scaleIpp: number,
): Annotation[] {
  if (!scaleIpp || scaleIpp <= 0) return annotations
  return annotations.map((a) =>
    a.type === 'dimension' ? recomputeDimension(a, annotations, scaleIpp) : a,
  )
}
