import { beforeEach, describe, expect, it, vi } from 'vitest'
import { runChatAgentTool } from './chatAgent'

const mockFetch = vi.fn()
globalThis.fetch = mockFetch

vi.mock('../../utils/fileToBase64', () => ({
  fileToBase64: vi.fn(async () => 'data:image/png;base64,AAAA'),
}))

describe('runChatAgentTool', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  it('uses the generate-from-image tool when the attachment is an image', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        dxf_url: '/downloads/generated.dxf',
        preview_url: '/artifacts/preview.png',
        structure: { rooms: [] },
        quality_metrics: {},
        review_flags: [],
        needs_review: false,
        scale_status: 'ok',
      }),
    })

    const file = new File(['image'], 'floor.png', { type: 'image/png' })
    const result = await runChatAgentTool({
      prompt: 'Generame el floor plan',
      attachment: file,
      planName: 'Fit Dawson',
    })

    expect(mockFetch).toHaveBeenCalledWith('/api/v2/generate-dxf', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    }))

    expect(result.assistantMessage.content).toMatch(/generé el floor plan/i)
    expect(result.assistantMessage.artifacts).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ kind: 'preview', title: 'Floor plan preview', href: '/artifacts/preview.png' }),
        expect.objectContaining({ kind: 'export', title: 'Download DXF', href: '/downloads/generated.dxf' }),
      ]),
    )
    expect(result.planUpdates).toEqual(expect.objectContaining({
      imageData: 'data:image/png;base64,AAAA',
      structure: { rooms: [] },
    }))
  })

  it('uses the CAD analysis tool when the attachment is a dxf or dwg', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        analysis_id: 'cad-123',
        source_name: 'dawson.dxf',
        source_format: 'dxf',
        canonical_unit: 'inch',
        conversion_status: 'native_dxf',
        floor_plan: {
          role: 'floor_plan',
          bbox: null,
          summary: { entity_count: 0, line_count: 0, polyline_count: 0, text_count: 0 },
          entities: [],
          rooms: [],
          measurements: { width: 468, height: 792, source: 'dimensions' },
        },
        site_plan: {
          role: 'site_plan',
          bbox: null,
          summary: { entity_count: 0, line_count: 0, polyline_count: 0, text_count: 0 },
          entities: [],
          rooms: [],
          measurements: { width: 765.77, height: 1010.71, source: 'buildable_bbox' },
        },
        side_by_side: { canonical_unit: 'inch', gap: 28.66, floor_width: 468, site_width: 765.77, max_height: 1010.71 },
        fit_summary: {
          comparison_unit: 'inch',
          basis: 'buildable_polygon',
          fits_within_buildable_polygon: false,
          fits_within_buildable_bbox: false,
          width_delta: -24,
          height_delta: 218,
        },
        warnings: [],
      }),
    })

    const file = new File(['cad'], 'dawson.dxf', { type: 'application/dxf' })
    const result = await runChatAgentTool({
      prompt: 'Analizá este site plan',
      attachment: file,
      planName: 'Fit Dawson',
    })

    expect(mockFetch).toHaveBeenCalledWith('/api/cad-workspace/extract', expect.objectContaining({
      method: 'POST',
      body: expect.any(FormData),
    }))
    expect(result.assistantMessage.content).toMatch(/analicé el cad/i)
    expect(result.assistantMessage.content).toMatch(/no entra/i)
    expect(result.assistantMessage.artifacts).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          kind: 'export',
          title: 'Download CAD overlay DXF',
          href: '/api/cad-workspace/export-overlay/cad-123',
        }),
      ]),
    )
  })

  it('asks for the required file when the prompt references a tool but no attachment was sent', async () => {
    const result = await runChatAgentTool({
      prompt: 'Analyze DXF/DWG',
      attachment: null,
      planName: 'Fit Dawson',
    })

    expect(mockFetch).not.toHaveBeenCalled()
    expect(result.assistantMessage.content).toMatch(/subime un \.dxf o \.dwg/i)
  })
})
