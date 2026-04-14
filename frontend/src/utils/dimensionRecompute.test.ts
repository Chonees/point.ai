import { describe, it, expect } from 'vitest'
import type { Annotation } from '../types'
import { recomputeDimension, recomputeDimensionsFor } from './dimensionRecompute'

function makeWall(id: string, x1: number, y1: number, x2: number, y2: number): Annotation {
  return { id, type: 'wall', x1, y1, x2, y2 }
}

function makeExteriorDim(
  id: string,
  wallIds: string[],
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  overrides: Partial<Annotation> = {},
): Annotation {
  return {
    id,
    type: 'dimension',
    subtype: 'exterior',
    orientation: 'H',
    outward: 1,
    offsetPx: 40,
    x1, y1, x2, y2,
    valueInches: Math.abs(x2 - x1),
    valueText: `${Math.round(Math.abs(x2 - x1))}"`,
    wallIds,
    ...overrides,
  }
}

describe('recomputeDimension', () => {
  it('updates valueInches and valueText when the anchor wall moves', () => {
    const wall = makeWall('w-top', 20, 20, 120, 20)
    const dim = makeExteriorDim('d1', ['w-top'], 20, 20, 120, 20)

    // User moves the right end of the wall further out (+50px)
    const movedWall: Annotation = { ...wall, x2: 170 }
    const recomputed = recomputeDimension(dim, [movedWall, dim], 1.0)

    expect(recomputed.x2).toBe(170)
    expect(recomputed.valueInches).toBe(150)
    // 150" → 12'-6"
    expect(recomputed.valueText).toBe('12\'-6"')
  })

  it('respects locked: preserves valueText but still updates geometry', () => {
    const wall = makeWall('w-top', 20, 20, 120, 20)
    const dim = makeExteriorDim('d1', ['w-top'], 20, 20, 120, 20, {
      locked: true,
      valueText: "CUSTOM 10'-0\"",
    })
    const movedWall: Annotation = { ...wall, x2: 220 }

    const recomputed = recomputeDimension(dim, [movedWall, dim], 1.0)

    expect(recomputed.x2).toBe(220)
    expect(recomputed.valueInches).toBe(200)
    // Locked → valueText preserved
    expect(recomputed.valueText).toBe("CUSTOM 10'-0\"")
  })

  it('returns the dim unchanged when no anchor walls exist in the list', () => {
    const dim = makeExteriorDim('d1', ['ghost-wall'], 20, 20, 120, 20)
    const recomputed = recomputeDimension(dim, [dim], 1.0)
    expect(recomputed).toBe(dim)
  })

  it('returns non-dimension annotations untouched', () => {
    const wall = makeWall('w-top', 20, 20, 120, 20)
    const out = recomputeDimension(wall, [wall], 1.0)
    expect(out).toBe(wall)
  })

  it('handles vertical orientation correctly', () => {
    const wall = makeWall('w-left', 20, 20, 20, 120)
    const dim: Annotation = {
      id: 'd1',
      type: 'dimension',
      subtype: 'exterior',
      orientation: 'V',
      outward: -1,
      offsetPx: 40,
      x1: 20, y1: 20, x2: 20, y2: 120,
      valueInches: 100,
      valueText: '8\'-4"',
      wallIds: ['w-left'],
    }
    const movedWall: Annotation = { ...wall, y2: 180 }

    const recomputed = recomputeDimension(dim, [movedWall, dim], 1.0)

    expect(recomputed.y2).toBe(180)
    expect(recomputed.valueInches).toBe(160)
    expect(recomputed.valueText).toBe("13'-4\"")
  })
})

describe('recomputeDimensionsFor', () => {
  it('recomputes dims in a mixed annotation list, leaves others alone', () => {
    const wall = makeWall('w-top', 0, 0, 100, 0)
    const other = makeWall('w-bot', 0, 100, 100, 100)
    const dim = makeExteriorDim('d1', ['w-top'], 0, 0, 100, 0)
    const moved: Annotation = { ...wall, x2: 240 }

    const result = recomputeDimensionsFor([moved, other, dim], 1.0)

    expect(result[0]).toBe(moved)   // wall untouched
    expect(result[1]).toBe(other)   // unrelated wall untouched
    expect(result[2]).not.toBe(dim) // dim recomputed
    expect(result[2].valueInches).toBe(240)
  })

  it('no-ops when scaleIpp is zero or missing', () => {
    const wall = makeWall('w-top', 0, 0, 100, 0)
    const dim = makeExteriorDim('d1', ['w-top'], 0, 0, 100, 0)
    const list = [wall, dim]
    expect(recomputeDimensionsFor(list, 0)).toBe(list)
  })
})
