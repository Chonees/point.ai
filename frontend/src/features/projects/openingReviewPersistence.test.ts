import { describe, expect, it } from 'vitest'
import {
  hasPersistedOpeningReview,
  markStructureWithPersistedOpeningReview,
  sanitizeReviewedOpeningAnnotations,
} from './openingReviewPersistence'

describe('openingReviewPersistence', () => {
  it('strips transient annotation metadata before persistence', () => {
    expect(sanitizeReviewedOpeningAnnotations([
      { type: 'door', x1: 1, y1: 2, x2: 3, y2: 4, swing: 'left', _source: 'review' },
    ])).toEqual([
      { type: 'door', x1: 1, y1: 2, x2: 3, y2: 4, swing: 'left' },
    ])
  })

  it('marks structure metadata so an empty reviewed set still counts as a saved review', () => {
    const structure = { walls: [], structure_meta: { image_size: { width: 100, height: 80 } } }

    const marked = markStructureWithPersistedOpeningReview(structure)

    expect(marked).toEqual({
      walls: [],
      structure_meta: {
        image_size: { width: 100, height: 80 },
        reviewed_opening_annotations_saved: true,
      },
    })
    expect(hasPersistedOpeningReview(marked)).toBe(true)
  })
})
