import type { Annotation } from '../types'

/** Mirrors the PlacedFurniture interface from FloorPlan3D */
export interface PlacedItemDB {
  itemId: string
  x: number
  y: number
  z: number
  rotation: number
  scaleW: number
  scaleD: number
  scaleH: number
  tintColor?: string
}

export interface ProjectRow {
  id: string
  user_id: string
  name: string
  created_at: string
  updated_at: string
}

export interface PlanRow {
  id: string
  project_id: string
  name: string
  image_data: string | null
  structure: Record<string, unknown> | null
  annotations_2d: Annotation[]
  placed_items_3d: PlacedItemDB[]
  floor_material: string
  wall_material: string
  created_at: string
  updated_at: string
}

export interface Database {
  public: {
    Tables: {
      projects: {
        Row: ProjectRow
        Insert: Omit<ProjectRow, 'id' | 'created_at' | 'updated_at'>
        Update: Partial<Omit<ProjectRow, 'id' | 'user_id' | 'created_at'>>
      }
      plans: {
        Row: PlanRow
        Insert: Omit<PlanRow, 'id' | 'created_at' | 'updated_at'>
        Update: Partial<Omit<PlanRow, 'id' | 'project_id' | 'created_at'>>
      }
    }
  }
}
