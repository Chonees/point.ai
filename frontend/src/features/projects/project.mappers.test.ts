import { describe, it, expect } from 'vitest'
import { rowToPlan } from './project.mappers'
import type { PlanRow } from '../../lib/database.types'

const makeRow = (overrides: Partial<PlanRow> = {}): PlanRow => ({
  id: 'plan-1',
  project_id: 'proj-1',
  name: 'Main Floor',
  image_data: null,
  structure: null,
  reviewed_opening_annotations: [],
  placed_items_3d: [],
  floor_material: 'hardwood',
  wall_material: 'white-paint',
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
    expect(plan.reviewedOpeningAnnotations).toEqual([])
    expect(plan.scene).toEqual({
      placedItems3d: [],
      floorMaterial: 'hardwood',
      wallMaterial: 'white-paint',
    })
    expect(plan.createdAt).toBe('2026-01-01T00:00:00Z')
    expect(plan.updatedAt).toBe('2026-01-02T00:00:00Z')
  })

  it('maps scene fields correctly', () => {
    const plan = rowToPlan(makeRow({
      placed_items_3d: [{
        itemId: 'chair-1',
        x: 10,
        y: 0,
        z: 20,
        rotation: 0,
        scaleW: 1,
        scaleD: 1,
        scaleH: 1,
      }],
      floor_material: 'marble',
      wall_material: 'brick',
    }))

    expect(plan.scene.placedItems3d).toHaveLength(1)
    expect(plan.scene.floorMaterial).toBe('marble')
    expect(plan.scene.wallMaterial).toBe('brick')
  })

  it('maps reviewed opening annotations and falls back to an empty list', () => {
    const withAnnotations = rowToPlan(makeRow({
      reviewed_opening_annotations: [
        { type: 'door', x1: 50, y1: 60, x2: 50, y2: 90, swing: 'left' },
      ],
    }))

    expect(withAnnotations.reviewedOpeningAnnotations).toEqual([
      { type: 'door', x1: 50, y1: 60, x2: 50, y2: 90, swing: 'left' },
    ])

    const withoutAnnotations = rowToPlan(makeRow({
      reviewed_opening_annotations: undefined as never,
    }))

    expect(withoutAnnotations.reviewedOpeningAnnotations).toEqual([])
  })
})
