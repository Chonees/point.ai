import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useCadWorkspace } from './useCadWorkspace'

const mockFetch = vi.fn()
globalThis.fetch = mockFetch

describe('useCadWorkspace', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  it('starts idle with no selected file', () => {
    const { result } = renderHook(() => useCadWorkspace())

    expect(result.current.status).toBe('idle')
    expect(result.current.file).toBeNull()
    expect(result.current.result).toBeNull()
    expect(result.current.canExtract).toBe(false)
  })

  it('rejects extraction when no file was selected', async () => {
    const { result } = renderHook(() => useCadWorkspace())

    await act(async () => {
      await result.current.extract()
    })

    expect(result.current.status).toBe('error')
    expect(result.current.statusMsg).toBe('Primero subí un .dxf o .dwg.')
  })

  it('posts form-data to the CAD endpoint and stores the result', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        analysis_id: 'cad-123',
        source_name: 'sample.dxf',
        source_format: 'dxf',
        canonical_unit: 'inch',
        conversion_status: 'native_dxf',
        conversion_note: null,
        floor_plan: {
          role: 'floor_plan',
          bbox: { x1: 0, y1: 0, x2: 600, y2: 300, width: 600, height: 300 },
          summary: { entity_count: 4, line_count: 4, polyline_count: 0, text_count: 0 },
          entities: [],
        },
        site_plan: {
          role: 'site_plan',
          bbox: { x1: 0, y1: 0, x2: 480, y2: 700, width: 480, height: 700 },
          summary: { entity_count: 2, line_count: 0, polyline_count: 2, text_count: 0 },
          entities: [],
        },
        side_by_side: { canonical_unit: 'inch', gap: 24, floor_width: 600, site_width: 480, max_height: 700 },
        warnings: [],
      }),
    })

    const file = new File(['cad'], 'sample.dxf', { type: 'application/dxf' })
    const { result } = renderHook(() => useCadWorkspace())

    act(() => {
      result.current.selectFile(file)
    })

    await act(async () => {
      await result.current.extract()
    })

    expect(mockFetch).toHaveBeenCalledTimes(1)
    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/cad-workspace/extract')
    expect(options.method).toBe('POST')
    expect(options.body).toBeInstanceOf(FormData)
    expect(result.current.status).toBe('done')
    expect(result.current.result?.source_name).toBe('sample.dxf')
  })
})
