import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { usePlanSave } from './usePlanSave'

const { eqMock, updateMock, fromMock } = vi.hoisted(() => {
  const eqMock = vi.fn().mockResolvedValue({ data: null, error: null })
  const updateMock = vi.fn(() => ({ eq: eqMock }))
  const fromMock = vi.fn(() => ({ update: updateMock }))
  return { eqMock, updateMock, fromMock }
})

vi.mock('../../lib/supabase', () => ({
  supabase: {
    from: fromMock,
  },
  isSupabaseConfigured: true,
}))

describe('usePlanSave', () => {
  beforeEach(() => {
    eqMock.mockClear()
    updateMock.mockClear()
    fromMock.mockClear()
  })

  it('persists reviewed opening annotations without transient _source metadata', async () => {
    const { result } = renderHook(() => usePlanSave('plan-1'))

    await act(async () => {
      await result.current.saveNow({
        reviewedOpeningAnnotations: [
          { type: 'door', x1: 50, y1: 60, x2: 50, y2: 90, swing: 'left', _source: 'review' },
        ],
      })
    })

    expect(fromMock).toHaveBeenCalledWith('plans')
    expect(updateMock).toHaveBeenCalledWith({
      reviewed_opening_annotations: [
        { type: 'door', x1: 50, y1: 60, x2: 50, y2: 90, swing: 'left' },
      ],
    })
    expect(eqMock).toHaveBeenCalledWith('id', 'plan-1')
  })
})
