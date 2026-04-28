import type { OpeningAnnotation } from '../types'

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

export type ReviewedOpeningAnnotationRow = Omit<OpeningAnnotation, '_source'>

export type PlanRow = {
  id: string
  project_id: string
  name: string
  image_data: string | null
  structure: Record<string, unknown> | null
  reviewed_opening_annotations: ReviewedOpeningAnnotationRow[]
  placed_items_3d: PlacedItemDB[]
  floor_material: string
  wall_material: string
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
          reviewed_opening_annotations?: ReviewedOpeningAnnotationRow[]
          placed_items_3d: PlacedItemDB[]
          floor_material: string
          wall_material: string
        }
        Update: {
          name?: string
          image_data?: string | null
          structure?: Record<string, unknown> | null
          reviewed_opening_annotations?: ReviewedOpeningAnnotationRow[]
          placed_items_3d?: PlacedItemDB[]
          floor_material?: string
          wall_material?: string
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
