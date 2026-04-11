import type * as THREE from 'three'
import type { FurnitureItem } from './catalog'

export interface FloorBounds {
  x: number; z: number; w: number; d: number
}

export interface PlacedFurniture {
  item: FurnitureItem
  x: number
  y: number
  z: number
  rotation: number
  scaleW: number
  scaleD: number
  scaleH: number
  tintColor?: string
}

export interface SurfaceHit {
  x: number; y: number; z: number
  normal: THREE.Vector3 | null
}

export interface PlacementSurface {
  selectedItem: FurnitureItem | null
  onPointerMove: (hit: SurfaceHit) => void
  onPointerLeave: () => void
}
