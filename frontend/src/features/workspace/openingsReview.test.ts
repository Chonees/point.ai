import { describe, expect, it } from 'vitest'
import { filterOpeningAnnotations, translateOpeningAnnotation } from './openingsReview'

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
})
