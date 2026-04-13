import type { Annotation, Visibility } from '../../types'
import type { PlacedItemDB } from '../../lib/database.types'

export interface ProjectData {
  id: string
  name: string
  createdAt: string
  updatedAt: string
  planCount: number
}

export interface PlanScene {
  annotations2d: Annotation[]
  placedItems3d: PlacedItemDB[]
  floorMaterial: string
  wallMaterial: string
  visibility: Visibility
}

export type ProjectScene = PlanScene

export interface PlanData {
  id: string
  projectId: string
  name: string
  imageData: string | null
  structure: Record<string, unknown> | null
  scene: PlanScene
  totalSqft: number | null
  createdAt: string
  updatedAt: string
}
