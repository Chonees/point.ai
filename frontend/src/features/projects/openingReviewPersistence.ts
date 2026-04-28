import type { OpeningAnnotation } from '../../types'

export function sanitizeReviewedOpeningAnnotations(
  annotations: OpeningAnnotation[],
): OpeningAnnotation[] {
  return annotations.map(({ _source, ...annotation }) => annotation)
}

export function hasPersistedOpeningReview(
  structure: Record<string, unknown> | null | undefined,
): boolean {
  const meta = getStructureMeta(structure)
  return meta.reviewed_opening_annotations_saved === true
}

export function markStructureWithPersistedOpeningReview(
  structure: Record<string, unknown> | null | undefined,
): Record<string, unknown> | null | undefined {
  if (!structure) return structure

  return {
    ...structure,
    structure_meta: {
      ...getStructureMeta(structure),
      reviewed_opening_annotations_saved: true,
    },
  }
}

function getStructureMeta(
  structure: Record<string, unknown> | null | undefined,
): Record<string, unknown> {
  if (!structure) return {}
  const candidate = structure.structure_meta
  return isRecord(candidate) ? candidate : {}
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
