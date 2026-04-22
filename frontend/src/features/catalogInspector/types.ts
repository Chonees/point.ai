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
  is_exterior_touching: boolean
  issues: string[]
}

export interface CatalogInspectorTopology {
  floor_plan_id: string
  name: string
  canonical_unit: string
  footprint_bbox: CatalogInspectorBBox
  rooms: CatalogInspectorRoom[]
  topology_readiness: {
    status: string
    issues: string[]
  }
  topology_issues: string[]
}
