import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useGenerateDxf } from './useGenerateDxf'

const mockFetch = vi.fn()
globalThis.fetch = mockFetch

beforeEach(() => {
  mockFetch.mockReset()
})

function makeHookArgs(overrides: Record<string, unknown> = {}) {
  return {
    file: null as File | null,
    preview: null as string | null,
    onStructureChange: vi.fn(),
    reviewedAnnotations: [],
    useReviewedAnnotations: false,
    ...overrides,
  }
}

describe('useGenerateDxf', () => {
  it('starts in idle state with no result', () => {
    const { result } = renderHook(() => useGenerateDxf(makeHookArgs()))

    expect(result.current.status).toBe('idle')
    expect(result.current.result).toBeNull()
    expect(result.current.statusMsg).toBe('')
  })

  it('sets error when no file or preview', async () => {
    const { result } = renderHook(() => useGenerateDxf(makeHookArgs()))

    await act(async () => {
      await result.current.generate()
    })

    expect(result.current.status).toBe('error')
    expect(result.current.statusMsg).toBe('Upload a floor plan image first.')
  })

  it('sends only the image payload needed for DXF generation', async () => {
    const dxfResult = {
      dxf_url: '/downloads/test.dxf',
      preview_url: null,
      structure: { walls: [] },
      quality_metrics: {},
      review_flags: [],
      needs_review: false,
      scale_status: 'ok',
    }
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(dxfResult),
    })

    const args = makeHookArgs({
      preview: 'data:image/png;base64,AAAA',
    })

    const { result } = renderHook(() => useGenerateDxf(args))

    await act(async () => {
      await result.current.generate()
    })

    expect(mockFetch).toHaveBeenCalledTimes(1)
    const [url, opts] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/v2/generate-dxf')
    const body = JSON.parse(opts.body)
    expect(body.image).toBe('AAAA')
    expect(body.model_variant).toBe('ensemble')
    expect(body).not.toHaveProperty('total_sqft')
    expect(body).not.toHaveProperty('annotations')
    expect(result.current.status).toBe('done')
    expect(result.current.result).toBeTruthy()
  })

  it('handles API error response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: () => Promise.resolve({ detail: 'Inference failed' }),
    })

    const args = makeHookArgs({ preview: 'data:image/png;base64,CC' })
    const { result } = renderHook(() => useGenerateDxf(args))

    await act(async () => {
      await result.current.generate()
    })

    expect(result.current.status).toBe('error')
    expect(result.current.statusMsg).toBe('Inference failed')
  })

  it('sends reviewed opening annotations when the session has review state', async () => {
    const dxfResult = {
      dxf_url: '/downloads/test.dxf',
      preview_url: null,
      structure: { walls: [] },
      quality_metrics: {},
      review_flags: [],
      needs_review: false,
      scale_status: 'ok',
      auto_annotations: [],
    }
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(dxfResult),
    })

    const args = makeHookArgs({
      preview: 'data:image/png;base64,AAAA',
      reviewedAnnotations: [
        { type: 'door', x1: 50, y1: 60, x2: 50, y2: 90, swing: 'left' },
      ],
      useReviewedAnnotations: true,
    })

    const { result } = renderHook(() => useGenerateDxf(args))

    await act(async () => {
      await result.current.generate()
    })

    const [, opts] = mockFetch.mock.calls[0]
    const body = JSON.parse(opts.body)
    expect(body.annotations).toEqual([
      { type: 'door', x1: 50, y1: 60, x2: 50, y2: 90, swing: 'left' },
    ])
  })
})
