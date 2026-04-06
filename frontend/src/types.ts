export type Status = 'idle' | 'loading' | 'done' | 'error'
export type ModelVariant = 'baseline' | 'mitunet' | 'ensemble'
export type AnnotationType = 'select' | 'wall' | 'door' | 'window' | 'eraser' | 'label' | 'paint'
export type SwingDir = 'up' | 'down' | 'left' | 'right'
export interface Annotation { type: AnnotationType; x1: number; y1: number; x2: number; y2: number; swing?: SwingDir; _source?: string; arcRadius?: number; roomName?: string; sqft?: number }

export interface V2Result {
  dxf_url: string
  preview_url: string | null
  structure: Record<string, unknown>
  quality_metrics: Record<string, unknown>
  review_flags: string[]
  needs_review: boolean
  scale_status: string
  auto_annotations?: { type: string; x1: number; y1: number; x2: number; y2: number; swing?: string; _source?: string }[]
  computed_rooms?: { roomName: string; sqft: number; x1: number; y1: number }[]
  region_overlay?: string
}
