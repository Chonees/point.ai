import { describe, expect, it } from 'vitest'
import {
  filterOpeningAnnotations,
  getOpeningMoveHandle,
  getOpeningPreviewGeometry,
  getOpeningSwingOptions,
  getOpeningSwingTargetPoint,
  setOpeningSwing,
  translateOpeningAnnotation,
} from './openingsReview'

describe('openingsReview helpers', () => {
  it('keeps only door and window annotations', () => {
    const annotations = filterOpeningAnnotations([
      { type: 'door', x1: 10, y1: 20, x2: 10, y2: 40, swing: 'left' },
      { type: 'window', x1: 50, y1: 20, x2: 80, y2: 20, swing: 'down' },
      { type: 'wall', x1: 0, y1: 0, x2: 100, y2: 0 },
    ])

    expect(annotations).toEqual([
      { type: 'door', x1: 10, y1: 20, x2: 10, y2: 40, swing: 'left' },
      { type: 'window', x1: 50, y1: 20, x2: 80, y2: 20, swing: 'down' },
    ])
  })

  it('translates an opening freely on the plane', () => {
    const moved = translateOpeningAnnotation(
      { type: 'door', x1: 10, y1: 20, x2: 10, y2: 40, swing: 'left' },
      { dx: 15, dy: -5 },
    )

    expect(moved).toEqual({
      type: 'door',
      x1: 25,
      y1: 15,
      x2: 25,
      y2: 35,
      swing: 'left',
    })
  })

  it('returns horizontal directions for horizontal openings', () => {
    expect(getOpeningSwingOptions({
      type: 'window',
      x1: 10,
      y1: 20,
      x2: 50,
      y2: 20,
    })).toEqual(['up', 'down'])
  })

  it('returns vertical directions for vertical openings', () => {
    expect(getOpeningSwingOptions({
      type: 'door',
      x1: 10,
      y1: 20,
      x2: 10,
      y2: 60,
    })).toEqual(['left', 'right'])
  })

  it('updates the swing immutably without moving the opening', () => {
    const original = { type: 'door', x1: 10, y1: 20, x2: 10, y2: 60 } as const

    expect(setOpeningSwing(original, 'right')).toEqual({
      type: 'door',
      x1: 10,
      y1: 20,
      x2: 10,
      y2: 60,
      swing: 'right',
    })
    expect(original).toEqual({
      type: 'door',
      x1: 10,
      y1: 20,
      x2: 10,
      y2: 60,
    })
  })

  it('returns the center point as the move handle', () => {
    expect(getOpeningMoveHandle({
      type: 'door',
      x1: 10,
      y1: 20,
      x2: 10,
      y2: 60,
    })).toEqual({ x: 10, y: 40 })
  })

  it('builds DXF-like preview geometry for a left-swing door', () => {
    const preview = getOpeningPreviewGeometry({
      type: 'door',
      x1: 50,
      y1: 20,
      x2: 50,
      y2: 70,
    }, 'left')

    expect(preview.lines).toHaveLength(2)
    expect(preview.arc).not.toBeNull()
    expect(preview.lines[0].x2).toBeLessThan(50)
    expect(preview.arc?.endX).toBe(50)
    expect(preview.arc?.endY).toBe(70)
  })

  it('builds DXF-like preview geometry for a horizontal window', () => {
    const preview = getOpeningPreviewGeometry({
      type: 'window',
      x1: 20,
      y1: 40,
      x2: 80,
      y2: 40,
    }, 'up')

    expect(preview.arc).toBeNull()
    expect(preview.lines).toHaveLength(6)
    expect(preview.lines.at(-1)?.y1).toBeGreaterThan(40)
    expect(preview.lines.at(-1)?.y2).toBeGreaterThan(40)
  })

  it('pushes swing targets far enough away from the move handle to avoid overlap', () => {
    expect(getOpeningSwingTargetPoint({
      type: 'door',
      x1: 10,
      y1: 20,
      x2: 10,
      y2: 60,
    }, 'left')).toEqual({ x: -18, y: 40 })
  })
})
