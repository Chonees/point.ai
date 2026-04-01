/**
 * Convert canonical structure JSON to 3D geometry descriptors.
 *
 * PRIORITY: uses region_plan.regions (same source as DXF) when available,
 * falls back to structure.walls only if no region_plan exists.
 *
 * Coordinates: DXF space (Y-up) → Three.js (X=X, Y=height, Z=-DXF_Y)
 * The Z negation flips so the 3D view matches the 2D layout orientation.
 */

const WALL_HEIGHT = 96 // 8 ft

export interface Wall3D {
  id: string
  x: number; z: number
  width: number; depth: number
  height: number
  isExterior: boolean
}

export interface Opening3D {
  kind: 'door' | 'window'
  x: number; z: number
  width: number; depth: number
  height: number
  windowHeight?: number
}

export interface Floor3D {
  x: number; z: number
  width: number; depth: number
}

export interface Scene3D {
  walls: Wall3D[]
  openings: Opening3D[]
  floor: Floor3D
  center: { x: number; z: number }
}

export function structureTo3D(structure: Record<string, unknown>): Scene3D {
  const meta = (structure.structure_meta as any) || {}
  const regionPlan = meta.dxf_region_plan || {}
  const regions = (regionPlan.regions || []) as any[]
  const structWalls = (structure.walls as any[]) || []

  const wall3Ds: Wall3D[] = []
  const opening3Ds: Opening3D[] = []

  let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity
  const track = (x: number, z: number) => {
    if (x < minX) minX = x
    if (x > maxX) maxX = x
    if (z < minZ) minZ = z
    if (z > maxZ) maxZ = z
  }

  if (regions.length > 0) {
    // USE REGION PLAN — same data source as DXF generation
    for (const region of regions) {
      const b = region.bounds || {}
      const x1 = Number(b.x1 || 0), y1 = Number(b.y1 || 0)
      const x2 = Number(b.x2 || 0), y2 = Number(b.y2 || 0)
      if (Math.abs(x2 - x1) < 1 && Math.abs(y2 - y1) < 1) continue

      // DXF coords → 3D: X stays, Z = -DXF_Y (flip for correct orientation)
      const cx = (x1 + x2) / 2
      const cz = -(y1 + y2) / 2
      const w = Math.abs(x2 - x1)
      const d = Math.abs(y2 - y1)

      track(cx - w / 2, cz - d / 2)
      track(cx + w / 2, cz + d / 2)

      wall3Ds.push({
        id: region.id || `r-${wall3Ds.length}`,
        x: cx, z: cz,
        width: w, depth: d,
        height: WALL_HEIGHT,
        isExterior: Boolean(region.is_exterior),
      })
    }
  } else if (structWalls.length > 0) {
    // FALLBACK: use structure.walls (structural mode, no region plan)
    for (const wall of structWalls) {
      const poly = wall.polyline || []
      if (poly.length < 2) continue
      const p0 = poly[0], p1 = poly[1]
      const x0 = Number(p0.x), y0 = Number(p0.y)
      const x1 = Number(p1.x), y1 = Number(p1.y)
      const thickness = Number(wall.thickness || 4)
      const isH = wall.orientation === 'horizontal'
      const length = Math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)

      const cx = (x0 + x1) / 2
      const cz = -(y0 + y1) / 2

      track(cx - (isH ? length : thickness) / 2, cz - (isH ? thickness : length) / 2)
      track(cx + (isH ? length : thickness) / 2, cz + (isH ? thickness : length) / 2)

      wall3Ds.push({
        id: wall.id || `w-${wall3Ds.length}`,
        x: cx, z: cz,
        width: isH ? length : thickness,
        depth: isH ? thickness : length,
        height: WALL_HEIGHT,
        isExterior: Boolean(wall.is_exterior),
      })
    }
  }

  // Floor
  if (minX === Infinity) { minX = 0; maxX = 200; minZ = -200; maxZ = 0 }
  const pad = 20
  const floor: Floor3D = {
    x: (minX + maxX) / 2,
    z: (minZ + maxZ) / 2,
    width: maxX - minX + pad * 2,
    depth: maxZ - minZ + pad * 2,
  }

  return {
    walls: wall3Ds,
    openings: opening3Ds,
    floor,
    center: { x: floor.x, z: floor.z },
  }
}
