export type CadWorkspaceStatus = 'idle' | 'loading' | 'done' | 'error'

export interface CadWorkspacePoint {
  x: number
  y: number
}

export interface CadWorkspaceBBox {
  x1: number
  y1: number
  x2: number
  y2: number
  width: number
  height: number
}

export interface CadWorkspaceEntity {
  type: string
  layer: string
  start?: CadWorkspacePoint | null
  end?: CadWorkspacePoint | null
  points: CadWorkspacePoint[]
  text?: string | null
  position?: CadWorkspacePoint | null
  bbox: CadWorkspaceBBox
}

export interface CadWorkspaceView {
  role: string
  bbox: CadWorkspaceBBox | null
  summary: {
    entity_count: number
    line_count: number
    polyline_count: number
    text_count: number
  }
  entities: CadWorkspaceEntity[]
  measurements?: {
    width: number
    height: number
    source: string
  } | null
}

export interface CadWorkspaceExtractResult {
  analysis_id: string
  source_name: string
  source_format: string
  canonical_unit: string
  conversion_status: string
  conversion_note?: string | null
  floor_plan: CadWorkspaceView
  site_plan: CadWorkspaceView
  side_by_side: {
    canonical_unit: string
    gap: number
    floor_width: number
    site_width: number
    max_height: number
  }
  fit_summary?: {
    comparison_unit: string
    basis: string
    footprint_bbox?: CadWorkspaceBBox | null
    property_bbox?: CadWorkspaceBBox | null
    buildable_bbox?: CadWorkspaceBBox | null
    buildable_polygon?: CadWorkspacePoint[]
    width_delta?: number | null
    height_delta?: number | null
    fits_within_buildable_bbox?: boolean | null
    fits_within_buildable_polygon?: boolean | null
  } | null
  warnings: string[]
}
