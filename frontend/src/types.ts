export type Status = 'idle' | 'loading' | 'done' | 'error'
export type ModelVariant = 'baseline' | 'mitunet' | 'ensemble'
export type SwingDir = 'up' | 'down' | 'left' | 'right'
export type OpeningAnnotationType = 'door' | 'window'

export interface OpeningAnnotation {
  type: OpeningAnnotationType
  x1: number
  y1: number
  x2: number
  y2: number
  swing?: SwingDir
  _source?: string
}

export interface V2Result {
  dxf_url: string
  preview_url: string | null
  structure: Record<string, unknown>
  quality_metrics: Record<string, unknown>
  review_flags: string[]
  needs_review: boolean
  scale_status: string
  auto_annotations?: OpeningAnnotation[]
}
