import { beforeEach, describe, expect, it, vi } from 'vitest'
import { runChatAgentTool, runSiteFitApplyTool } from './chatAgent'

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

    expect(result.assistantMessage.content).toMatch(/gener/i)
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

  it('returns an inline CAD review artifact and enables DXF export when overlay data is complete', async () => {
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
          bbox: { x1: 0, y1: 0, x2: 468, y2: 792, width: 468, height: 792 },
          summary: { entity_count: 0, line_count: 0, polyline_count: 0, text_count: 0 },
          entities: [],
          rooms: [],
          measurements: { width: 468, height: 792, source: 'dimensions' },
        },
        site_plan: {
          role: 'site_plan',
          bbox: { x1: 100, y1: 100, x2: 865.77, y2: 1110.71, width: 765.77, height: 1010.71 },
          summary: { entity_count: 0, line_count: 0, polyline_count: 0, text_count: 0 },
          entities: [],
          rooms: [],
          measurements: { width: 765.77, height: 1010.71, source: 'buildable_bbox' },
        },
        side_by_side: { canonical_unit: 'inch', gap: 28.66, floor_width: 468, site_width: 765.77, max_height: 1010.71 },
        fit_summary: {
          comparison_unit: 'inch',
          basis: 'buildable_polygon',
          footprint_bbox: { x1: 0, y1: 0, x2: 468, y2: 792, width: 468, height: 792 },
          buildable_bbox: { x1: 100, y1: 100, x2: 865.77, y2: 1110.71, width: 765.77, height: 1010.71 },
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
      prompt: 'Analiza este site plan',
      attachment: file,
      planName: 'Fit Dawson',
    })

    expect(mockFetch).toHaveBeenCalledWith('/api/cad-workspace/extract', expect.objectContaining({
      method: 'POST',
      body: expect.any(FormData),
    }))
    expect(result.assistantMessage.content).toMatch(/analic/i)
    expect(result.assistantMessage.content).toMatch(/no entra/i)
    expect(result.assistantMessage.artifacts).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          kind: 'cad-review',
          title: 'CAD fit review',
          review: expect.objectContaining({
            export: {
              ready: true,
              href: '/api/cad-workspace/export-overlay/cad-123',
            },
          }),
        }),
      ]),
    )
  })

  it('keeps the CAD review inside chat and blocks export when overlay data is incomplete', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        analysis_id: 'cad-456',
        source_name: 'site-only.dxf',
        source_format: 'dxf',
        canonical_unit: 'inch',
        conversion_status: 'native_dxf',
        floor_plan: {
          role: 'floor_plan',
          bbox: null,
          summary: { entity_count: 0, line_count: 0, polyline_count: 0, text_count: 0 },
          entities: [],
          rooms: [],
          measurements: null,
        },
        site_plan: {
          role: 'site_plan',
          bbox: null,
          summary: { entity_count: 0, line_count: 0, polyline_count: 0, text_count: 0 },
          entities: [],
          rooms: [],
          measurements: null,
        },
        side_by_side: { canonical_unit: 'inch', gap: 28.66, floor_width: 0, site_width: 0, max_height: 0 },
        fit_summary: {
          comparison_unit: 'inch',
          basis: 'unavailable',
          fits_within_buildable_polygon: null,
          fits_within_buildable_bbox: null,
          width_delta: null,
          height_delta: null,
        },
        warnings: ['Missing buildable geometry'],
      }),
    })

    const file = new File(['cad'], 'site-only.dxf', { type: 'application/dxf' })
    const result = await runChatAgentTool({
      prompt: 'Analiza este site plan',
      attachment: file,
      planName: 'Fit Dawson',
    })

    expect(result.assistantMessage.artifacts).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          kind: 'cad-review',
          review: expect.objectContaining({
            export: expect.objectContaining({
              ready: false,
              reason: expect.stringMatching(/area construible|footprint/i),
            }),
          }),
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

  it('routes CAD + Seminole prompts through the bridge propose endpoint', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        pipeline: 'site_fit_bridge_mvp_v1',
        scope: 'seminole-2000-only',
        plan_id: 'seminole-2000',
        plan_name: 'SEMINOLE2000',
        cad_analysis: {
          analysis_id: 'cad-123',
          source_name: 'site.dxf',
          source_format: 'dxf',
          canonical_unit: 'inch',
          conversion_status: 'native_dxf',
          floor_plan: {
            role: 'floor_plan',
            bbox: null,
            summary: { entity_count: 0, line_count: 0, polyline_count: 0, text_count: 0 },
            entities: [],
            rooms: [],
            measurements: null,
          },
          site_plan: {
            role: 'site_plan',
            bbox: null,
            summary: { entity_count: 0, line_count: 0, polyline_count: 0, text_count: 0 },
            entities: [],
            rooms: [],
            measurements: null,
          },
          side_by_side: {
            canonical_unit: 'inch',
            gap: 0,
            floor_width: 0,
            site_width: 0,
            max_height: 0,
          },
          fit_summary: {
            comparison_unit: 'inch',
            basis: 'buildable_polygon',
            fits_within_buildable_polygon: true,
            fits_within_buildable_bbox: true,
          },
          warnings: [],
        },
        site_constraints: { unit: 'inch' },
        proposal: {
          status: 'fit_ready',
          candidates: [{
            candidate_id: 'baseline_preserved',
            strategy: 'preserve_existing_layout',
            summary: 'Keep the current plan unchanged.',
            fit_status: 'fit_ready',
            change_count: 0,
          }],
          warnings: [],
        },
        warnings: [],
      }),
    })

    const file = new File(['cad'], 'site.dxf', { type: 'application/dxf' })
    const result = await runChatAgentTool({
      prompt: 'Fit Seminole 2000 on this site plan',
      attachment: file,
      planName: 'Fit Dawson',
    })

    expect(mockFetch).toHaveBeenCalledWith('/api/v2/site-fit/bridge/propose', expect.objectContaining({
      method: 'POST',
      body: expect.any(FormData),
    }))
    expect(result.assistantMessage.artifacts).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: 'cad-review' }),
      expect.objectContaining({ kind: 'site-fit-proposal' }),
    ]))
  })

  it('calls the bridge apply endpoint and returns an apply artifact', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        pipeline: 'site_fit_bridge_mvp_v1',
        scope: 'seminole-2000-only',
        plan_id: 'seminole-2000',
        plan_name: 'SEMINOLE2000',
        apply: {
          candidate_id: 'baseline_preserved',
          apply_status: 'applied',
          compliance_summary: { status: 'pass' },
          warnings: [],
        },
        warnings: [],
      }),
    })

    const result = await runSiteFitApplyTool({
      planId: 'seminole-2000',
      planName: 'SEMINOLE2000',
      candidateId: 'baseline_preserved',
      siteConstraints: { unit: 'inch' },
    })

    expect(mockFetch).toHaveBeenCalledWith('/api/v2/site-fit/bridge/apply', expect.objectContaining({
      method: 'POST',
    }))
    expect(result.assistantMessage.artifacts).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: 'site-fit-apply' }),
    ]))
  })
})
