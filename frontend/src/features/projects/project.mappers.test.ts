import { describe, it, expect } from 'vitest'
import { rowToPlan } from './project.mappers'
import type { PlanRow } from '../../lib/database.types'
import { DEFAULT_VISIBILITY } from '../../types'

const makeRow = (overrides: Partial<PlanRow> = {}): PlanRow => ({
  id: 'plan-1',
  project_id: 'proj-1',
  name: 'Main Floor',
  image_data: null,
  structure: null,
  annotations_2d: [],
  placed_items_3d: [],
  floor_material: 'hardwood',
  wall_material: 'white-paint',
  editor_visibility: DEFAULT_VISIBILITY,
  total_sqft: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
  ...overrides,
})

describe('rowToPlan', () => {
  it('maps snake_case DB row to camelCase PlanData', () => {
    const plan = rowToPlan(makeRow())

    expect(plan.id).toBe('plan-1')
    expect(plan.projectId).toBe('proj-1')
    expect(plan.name).toBe('Main Floor')
    expect(plan.imageData).toBeNull()
    expect(plan.structure).toBeNull()
    expect(plan.createdAt).toBe('2026-01-01T00:00:00Z')
    expect(plan.updatedAt).toBe('2026-01-02T00:00:00Z')
  })

  it('maps scene fields correctly', () => {
    const annotations = [
      { id: 'w-1', type: 'wall' as const, x1: 0, y1: 0, x2: 10, y2: 10 },
    ]
    const plan = rowToPlan(makeRow({
      annotations_2d: annotations,
      floor_material: 'marble',
      wall_material: 'brick',
    }))

    expect(plan.scene.annotations2d).toEqual(annotations)
    expect(plan.scene.placedItems3d).toEqual([])
    expect(plan.scene.floorMaterial).toBe('marble')
    expect(plan.scene.wallMaterial).toBe('brick')
  })

  it('backfills missing ids on legacy annotations', () => {
    const legacy = [{ type: 'wall' as const, x1: 0, y1: 0, x2: 10, y2: 10 }] as any
    const plan = rowToPlan(makeRow({ annotations_2d: legacy }))
    expect(plan.scene.annotations2d).toHaveLength(1)
    expect(plan.scene.annotations2d[0].id).toBeTruthy()
    expect(typeof plan.scene.annotations2d[0].id).toBe('string')
  })

  it('merges legacy editor_visibility with defaults for newly added keys', () => {
    // Legacy row has no `dimensions` key
    const legacyVisibility = {
      bg: true, regions: true, walls: true, doors: true,
      windows: true, labels: true, separators: true,
    } as any
    const plan = rowToPlan(makeRow({ editor_visibility: legacyVisibility }))
    expect(plan.scene.visibility.dimensions).toBe(true)
  })

  it('defaults annotations to empty array when null', () => {
    const plan = rowToPlan(makeRow({
      annotations_2d: null as any,
      placed_items_3d: null as any,
    }))

    expect(plan.scene.annotations2d).toEqual([])
    expect(plan.scene.placedItems3d).toEqual([])
  })
})
