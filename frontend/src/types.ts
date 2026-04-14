export type Status = 'idle' | 'loading' | 'done' | 'error'
export type ModelVariant = 'baseline' | 'mitunet' | 'ensemble'
export type AnnotationType = 'select' | 'wall' | 'door' | 'window' | 'label' | 'paint' | 'separator' | 'dimension' | 'measure'
export type SwingDir = 'up' | 'down' | 'left' | 'right'
export type DimensionSubtype = 'exterior' | 'window_chain' | 'interior'
export type DimensionOrientation = 'H' | 'V'

export interface Annotation {
  /** Stable identifier. Generated server-side on auto-annotations and
   *  client-side (crypto.randomUUID) when annotations arrive without one. */
  id: string
  type: AnnotationType
  x1: number
  y1: number
  x2: number
  y2: number
  // Shared optional fields
  swing?: SwingDir
  _source?: string
  arcRadius?: number
  roomName?: string
  sqft?: number
  thickness?: number
  labelScale?: number
  labelRotation?: number
  // Dimension-specific fields
  subtype?: DimensionSubtype
  offsetPx?: number
  orientation?: DimensionOrientation
  outward?: 1 | -1
  valueInches?: number
  valueText?: string
  wallIds?: string[]
  windowIds?: string[]
  /** When true, the user has manually edited valueText and dynamic
   *  recompute must preserve it (only the geometry updates). */
  locked?: boolean
}

/** Per-plan visibility toggles controlled from the 2D editor's "Hide" panel. */
export interface Visibility {
  bg: boolean
  regions: boolean
  walls: boolean
  doors: boolean
  windows: boolean
  labels: boolean
  separators: boolean
  dimensions: boolean
}

export const DEFAULT_VISIBILITY: Visibility = {
  bg: true,
  regions: true,
  walls: true,
  doors: true,
  windows: true,
  labels: true,
  separators: true,
  dimensions: true,
}

export interface V2Result {
  dxf_url: string
  preview_url: string | null
  structure: Record<string, unknown>
  quality_metrics: Record<string, unknown>
  review_flags: string[]
  needs_review: boolean
  scale_status: string
  auto_annotations?: Array<{
    id?: string
    type: string
    x1: number
    y1: number
    x2: number
    y2: number
    swing?: string
    _source?: string
    thickness?: number
    // Dimension fields arriving from backend use snake_case
    subtype?: DimensionSubtype
    offset_px?: number
    orientation?: DimensionOrientation
    outward?: 1 | -1
    value_inches?: number
    value_text?: string
    wall_ids?: string[]
    window_ids?: string[]
  }>
  computed_rooms?: { roomName: string; sqft: number; x1: number; y1: number }[]
  region_overlay?: string
  scale_ipp?: number
}
