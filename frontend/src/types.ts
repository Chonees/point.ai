export type Status = 'idle' | 'loading' | 'done' | 'error'
export type ModelVariant = 'baseline' | 'mitunet' | 'ensemble'

export interface V2Result {
  dxf_url: string
  preview_url: string | null
  structure: Record<string, unknown>
  quality_metrics: Record<string, unknown>
  review_flags: string[]
  needs_review: boolean
  scale_status: string
}
