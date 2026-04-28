import type { PlanRow } from '../../lib/database.types'
import type { PlanData } from './project.types'

export function rowToPlan(row: PlanRow): PlanData {
  return {
    id: row.id,
    projectId: row.project_id,
    name: row.name,
    imageData: row.image_data,
    structure: row.structure,
    reviewedOpeningAnnotations: row.reviewed_opening_annotations ?? [],
    scene: {
      placedItems3d: row.placed_items_3d ?? [],
      floorMaterial: row.floor_material,
      wallMaterial: row.wall_material,
    },
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  }
}
