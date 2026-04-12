import { useMemo } from 'react'
import type { Wall3D, Opening3D } from '../structureTo3D'
import type { FloorBounds } from '../types'
import type { Annotation } from '../../../types'

const WALL_HEIGHT = 96

export function useAnnotationGeometry(
  structure: Record<string, unknown>,
  annotations: Annotation[],
): {
  walls3D: Wall3D[]
  openings3D: Opening3D[]
  floorBounds: FloorBounds
  center: { x: number; z: number }
} {
  return useMemo(() => {
    const meta = (structure.structure_meta as Record<string, any>) || {}
    const regionPlan = meta.dxf_region_plan || {}
    const regionMeta = regionPlan.meta || {}
    const transform = regionMeta.transform || {}
    const imageShape = regionMeta.image_shape || {}
    const imageHeight = Number(imageShape.height || 0)
    const scale = Number(transform.scale || 1)
    const offsetX = Number(transform.offset_x || 0)
    const offsetY = Number(transform.offset_y || 0)

    const toDxf = (imageX: number, imageY: number) => ({
      x: imageX * scale + offsetX,
      y: (imageHeight - imageY) * scale + offsetY,
    })

    const walls: Wall3D[] = []
    const openings: Opening3D[] = []
    let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity

    const track = (x: number, z: number) => {
      if (x < minX) minX = x
      if (x > maxX) maxX = x
      if (z < minZ) minZ = z
      if (z > maxZ) maxZ = z
    }

    for (const annotation of annotations) {
      const p1 = toDxf(annotation.x1, annotation.y1)
      const p2 = toDxf(annotation.x2, annotation.y2)
      const centerX = (p1.x + p2.x) / 2
      const centerZ = -(p1.y + p2.y) / 2
      const absDx = Math.abs(p2.x - p1.x)
      const absDy = Math.abs(p2.y - p1.y)
      const isHorizontal = absDx >= absDy
      const span = Math.sqrt(absDx * absDx + absDy * absDy)

      if (annotation.type === 'wall') {
        const thickness = 4 * scale
        const width = isHorizontal ? span : thickness
        const depth = isHorizontal ? thickness : span
        track(centerX - width / 2, centerZ - depth / 2)
        track(centerX + width / 2, centerZ + depth / 2)
        walls.push({ id: `w-${walls.length}`, x: centerX, z: centerZ, width, depth, height: WALL_HEIGHT, isExterior: false })
      }
    }

    if (minX === Infinity) { minX = -100; maxX = 100; minZ = -100; maxZ = 100 }
    const pad = 30
    const floorX = (minX + maxX) / 2
    const floorZ = (minZ + maxZ) / 2
    return {
      walls3D: walls,
      openings3D: openings,
      floorBounds: { x: floorX, z: floorZ, w: maxX - minX + pad * 2, d: maxZ - minZ + pad * 2 } as FloorBounds,
      center: { x: floorX, z: floorZ },
    }
  }, [annotations, structure])
}
