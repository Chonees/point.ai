import type { Annotation, Visibility } from '../types'

/** Mirrors the PlacedFurniture interface from FloorPlan3D */
export type PlacedItemDB = {
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

export type ProjectRow = {
  id: string
  user_id: string
  name: string
  created_at: string
  updated_at: string
}

export type PlanRow = {
  id: string
  project_id: string
  name: string
  image_data: string | null
  structure: Record<string, unknown> | null
  annotations_2d: Annotation[]
  placed_items_3d: PlacedItemDB[]
  floor_material: string
  wall_material: string
  editor_visibility: Visibility
  total_sqft: number | null
  created_at: string
  updated_at: string
}

export type Database = {
  public: {
    Tables: {
      projects: {
        Row: ProjectRow
        Insert: {
          user_id: string
          name: string
        }
        Update: {
          name?: string
          updated_at?: string
        }
        Relationships: []
      }
      plans: {
        Row: PlanRow
        Insert: {
          project_id: string
          name: string
          image_data: string | null
          structure: Record<string, unknown> | null
          annotations_2d: Annotation[]
          placed_items_3d: PlacedItemDB[]
          floor_material: string
          wall_material: string
          editor_visibility?: Visibility
          total_sqft?: number | null
        }
        Update: {
          name?: string
          image_data?: string | null
          structure?: Record<string, unknown> | null
          annotations_2d?: Annotation[]
          placed_items_3d?: PlacedItemDB[]
          floor_material?: string
          wall_material?: string
          editor_visibility?: Visibility
          total_sqft?: number | null
          updated_at?: string
        }
        Relationships: []
      }
    }
    Views: Record<string, never>
    Functions: Record<string, never>
    Enums: Record<string, never>
    CompositeTypes: Record<string, never>
  }
}
