/**
 * Convert canonical structure JSON to 3D geometry descriptors.
 * Maps 2D floor plan (x, y) to 3D space (x, height, z) on the XZ plane.
 */

const WALL_HEIGHT = 96 // 8 ft in inches (or pixels — proportional)
const SLAB_ANGLES: Record<string, number> = { up: -Math.PI / 2, down: Math.PI / 2, left: Math.PI, right: 0 }

export interface Wall3D {
  id: string
  x: number; z: number  // center position
  width: number; depth: number  // XZ dimensions
  height: number
  isExterior: boolean
  orientation: 'horizontal' | 'vertical'
}

export interface Opening3D {
  kind: 'door' | 'window'
  x: number; z: number
  width: number; depth: number
  height: number
  windowHeight?: number  // bottom of window from floor
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
  const walls = (structure.walls as any[]) || []
  const openings = (structure.openings as any[]) || []

  // Also read annotations for doors/windows (ensemble mode has openings=[])
  const meta = (structure.structure_meta as any) || {}
  const regionPlan = meta.dxf_region_plan || {}
  const regions = regionPlan.regions || []

  const wall3Ds: Wall3D[] = []
  const opening3Ds: Opening3D[] = []

  // Bounding box for floor and centering
  let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity

  const updateBounds = (x: number, z: number) => {
    if (x < minX) minX = x
    if (x > maxX) maxX = x
    if (z < minZ) minZ = z
    if (z > maxZ) maxZ = z
  }

  // Process walls from structure
  if (walls.length > 0) {
    for (const wall of walls) {
      const poly = wall.polyline || []
      if (poly.length < 2) continue
      const p0 = poly[0], p1 = poly[1]
      const x0 = Number(p0.x), z0 = Number(p0.y)
      const x1 = Number(p1.x), z1 = Number(p1.y)
      const thickness = Number(wall.thickness || 4)

      updateBounds(x0, z0)
      updateBounds(x1, z1)

      const isH = wall.orientation === 'horizontal'
      const cx = (x0 + x1) / 2
      const cz = (z0 + z1) / 2
      const length = Math.sqrt((x1 - x0) ** 2 + (z1 - z0) ** 2)

      wall3Ds.push({
        id: wall.id || `wall-${wall3Ds.length}`,
        x: cx, z: cz,
        width: isH ? length : thickness,
        depth: isH ? thickness : length,
        height: WALL_HEIGHT,
        isExterior: Boolean(wall.is_exterior),
        orientation: isH ? 'horizontal' : 'vertical',
      })
    }
  } else if (regions.length > 0) {
    // Fallback: use mask_regions
    for (const region of regions) {
      const b = region.bounds || {}
      const x1 = Number(b.x1 || 0), z1 = Number(b.y1 || 0)
      const x2 = Number(b.x2 || 0), z2 = Number(b.y2 || 0)

      updateBounds(x1, z1)
      updateBounds(x2, z2)

      const cx = (x1 + x2) / 2
      const cz = (z1 + z2) / 2

      wall3Ds.push({
        id: region.id || `region-${wall3Ds.length}`,
        x: cx, z: cz,
        width: Math.abs(x2 - x1),
        depth: Math.abs(z2 - z1),
        height: WALL_HEIGHT,
        isExterior: Boolean(region.is_exterior),
        orientation: region.orientation || 'horizontal',
      })
    }
  }

  // Process openings
  for (const op of openings) {
    if (!op.position) continue
    const cx = Number(op.position.x)
    const cz = Number(op.position.y)
    const span = Number(op.span || 30)
    const isH = op.orientation === 'horizontal'

    if (op.kind === 'door') {
      opening3Ds.push({
        kind: 'door',
        x: cx, z: cz,
        width: isH ? span : 4,
        depth: isH ? 4 : span,
        height: 80, // 6'8" standard door height
      })
    } else {
      opening3Ds.push({
        kind: 'window',
        x: cx, z: cz,
        width: isH ? span : 4,
        depth: isH ? 4 : span,
        height: 36,
        windowHeight: 36, // starts at 3' from floor
      })
    }
  }

  // Floor
  if (minX === Infinity) {
    minX = 0; maxX = 200; minZ = 0; maxZ = 200
  }
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
