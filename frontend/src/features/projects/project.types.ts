import type { PlacedItemDB } from '../../lib/database.types'

export interface ProjectData {
  id: string
  name: string
  createdAt: string
  updatedAt: string
  planCount: number
}

export interface PlanScene {
  placedItems3d: PlacedItemDB[]
  floorMaterial: string
  wallMaterial: string
}

export type ProjectScene = PlanScene

export interface PlanData {
  id: string
  projectId: string
  name: string
  imageData: string | null
  structure: Record<string, unknown> | null
  scene: PlanScene
  createdAt: string
  updatedAt: string
}
