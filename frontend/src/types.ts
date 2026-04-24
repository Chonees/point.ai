export type Status = 'idle' | 'loading' | 'done' | 'error'
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
  wall_id?: string
  side?: 'bottom' | 'top' | 'left' | 'right'
  door_type?: string
  polygon?: Array<{ x: number; y: number }>
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

