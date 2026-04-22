export interface CatalogInspectorPoint {
  x: number
  y: number
}

export interface CatalogInspectorBBox {
  x1: number
  y1: number
  x2: number
  y2: number
  width: number
  height: number
}

export interface CatalogInspectorRoom {
  room_id: string
  name: string
  category: string
  polygon: CatalogInspectorPoint[]
  bbox: CatalogInspectorBBox
  centroid: CatalogInspectorPoint
  width: number
  height: number
  area: number
  measurement_source: string
  adjacent_room_ids: string[]
  opening_adjacent_room_ids: string[]
  heuristic_adjacent_room_ids: string[]
  owned_wall_ids: string[]
  shared_wall_ids: string[]
  exterior_wall_ids: string[]
  is_exterior_touching: boolean
  isolation_status: string
  issues: string[]
}

export interface CatalogInspectorWall {
  wall_id: string
  start: CatalogInspectorPoint
  end: CatalogInspectorPoint
  orientation: 'horizontal' | 'vertical' | 'diagonal'
  length: number
  is_exterior: boolean
  room_ids: string[]
  boundary_kind: 'shared' | 'exterior' | string
  owner_room_ids: string[]
  provenance: string
  confidence: string
  trace_support_status: 'not_evaluated' | 'exact_trace_supported' | 'snapped_to_trace' | 'unsupported' | string
  trace_support_ids: string[]
  trace_support_gap?: number | null
  issues: string[]
}

export interface CatalogInspectorCadTrace {
  trace_id: string
  trace_kind: 'wall' | 'door' | 'window' | string
  type: 'line' | 'polyline' | string
  layer: string
  start?: CatalogInspectorPoint | null
  end?: CatalogInspectorPoint | null
  points: CatalogInspectorPoint[]
  bbox: CatalogInspectorBBox
}

export interface CatalogInspectorTopology {
  floor_plan_id: string
  name: string
  canonical_unit: string
  footprint_bbox: CatalogInspectorBBox
  rooms: CatalogInspectorRoom[]
  cad_traces?: CatalogInspectorCadTrace[]
  topology_readiness: {
    status: string
    issues: string[]
  }
  topology_issues: string[]
  walls: CatalogInspectorWall[]
  wall_graph_readiness: {
    status: string
    issues: string[]
  }
  wall_graph_issues: string[]
}
