export type Status = 'idle' | 'loading' | 'done' | 'error'
export type ModelVariant = 'baseline' | 'mitunet' | 'ensemble'
export type AnnotationType = 'wall' | 'door' | 'window' | 'eraser'
export type SwingDir = 'up' | 'down' | 'left' | 'right'
export interface Annotation { type: AnnotationType; x1: number; y1: number; x2: number; y2: number; swing?: SwingDir; _source?: string; arcRadius?: number }

export interface BOMSummary {
  total_wall_length_ft: number
  exterior_wall_length_ft: number
  interior_wall_length_ft: number
  total_wall_area_sqft: number
  wall_count: number
  total_doors: number
  normal_doors: number
  garage_doors: number
  sliding_doors: number
  total_windows: number
  unit: string
}

export interface BOMData {
  summary: BOMSummary
  walls: { id: string; orientation: string; is_exterior: boolean; length_ft: number }[]
  materials: { item: string; qty: number; unit: string }[]
}

export interface V2Result {
  dxf_url: string
  preview_url: string | null
  structure: Record<string, unknown>
  quality_metrics: Record<string, unknown>
  review_flags: string[]
  needs_review: boolean
  scale_status: string
  auto_annotations?: { type: string; x1: number; y1: number; x2: number; y2: number; swing?: string; _source?: string }[]
  bom?: BOMData
}
