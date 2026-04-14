import type { PlanRow } from '../../lib/database.types'
import type { Annotation } from '../../types'
import { DEFAULT_VISIBILITY } from '../../types'
import { newAnnotationId } from '../../utils/annotationId'
import type { PlanData } from './project.types'

/**
 * Backfill `id` on legacy annotations persisted before we required one.
 * Generating fresh ids on load is safe — older plans had no cross-annotation
 * references to preserve (dimensions didn't exist yet).
 */
function _ensureAnnotationIds(anns: Annotation[] | null | undefined): Annotation[] {
  if (!anns) return []
  return anns.map((a) => (a.id ? a : { ...a, id: newAnnotationId() }))
}

export function rowToPlan(row: PlanRow): PlanData {
  return {
    id: row.id,
    projectId: row.project_id,
    name: row.name,
    imageData: row.image_data,
    structure: row.structure,
    scene: {
      annotations2d: _ensureAnnotationIds(row.annotations_2d),
      placedItems3d: row.placed_items_3d ?? [],
      floorMaterial: row.floor_material,
      wallMaterial: row.wall_material,
      // Merge with DEFAULT_VISIBILITY so legacy rows (missing newer keys like
      // `dimensions`) get sensible defaults without a destructive migration.
      visibility: { ...DEFAULT_VISIBILITY, ...(row.editor_visibility ?? {}) },
    },
    totalSqft: row.total_sqft ?? null,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  }
}
