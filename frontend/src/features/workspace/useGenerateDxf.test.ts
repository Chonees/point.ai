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
    annotations: [] as any[],
    autoLoaded: false,
    totalSqft: '',
    onStructureChange: vi.fn(),
    onAnnotationsUpdate: vi.fn(),
    onAutoLoaded: vi.fn(),
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

  it('sends correct request body with image and sqft', async () => {
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
      totalSqft: '2000',
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
    expect(body.total_sqft).toBe(2000)
    expect(result.current.status).toBe('done')
    expect(result.current.result).toBeTruthy()
  })

  it('includes annotations when autoLoaded', async () => {
    const annotations = [{ type: 'wall', x1: 0, y1: 0, x2: 10, y2: 10, _source: 'test' }]
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        dxf_url: '/downloads/test.dxf',
        preview_url: null,
        structure: {},
        quality_metrics: {},
        review_flags: [],
        needs_review: false,
        scale_status: 'ok',
      }),
    })

    const args = makeHookArgs({
      preview: 'data:image/png;base64,BBBB',
      annotations,
      autoLoaded: true,
    })

    const { result } = renderHook(() => useGenerateDxf(args))

    await act(async () => {
      await result.current.generate()
    })

    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.annotations).toHaveLength(1)
    expect(body.annotations[0]._source).toBeUndefined()
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
})
