import { beforeEach, describe, expect, it, vi } from 'vitest'
import { runChatAgentTool, runSiteFitApplyTool } from './chatAgent'

const mockFetch = vi.fn()
globalThis.fetch = mockFetch

describe('runChatAgentTool', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  it('rejects image attachments because this chat lane only supports site plan DXF/DWG', async () => {
    const file = new File(['image'], 'floor.png', { type: 'image/png' })
    const result = await runChatAgentTool({
      prompt: 'Fit Seminole 2000 on this site plan',
      attachment: file,
    })

    expect(mockFetch).not.toHaveBeenCalled()
    expect(result.assistantMessage.content).toMatch(/solo.*site plan.*\.dxf\/\.dwg/i)
    expect(result.assistantMessage.artifacts).toEqual([])
    expect(result.planUpdates).toBeUndefined()
  })

  it('returns an inline CAD diagnostic artifact and keeps overlay export explicitly diagnostic', async () => {
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
    })

    expect(mockFetch).toHaveBeenCalledWith('/api/cad-workspace/extract', expect.objectContaining({
      method: 'POST',
      body: expect.any(FormData),
    }))
    expect(result.assistantMessage.content).toMatch(/diagnostic/i)
    expect(result.assistantMessage.content).toMatch(/no entra/i)
    expect(result.assistantMessage.artifacts).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          kind: 'cad-review',
          title: 'CAD diagnostic review',
          description: expect.stringMatching(/diagnostic/i),
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
      prompt: 'Fit Seminole 2000 on this site plan',
      attachment: null,
    })

    expect(mockFetch).not.toHaveBeenCalled()
    expect(result.assistantMessage.content).toMatch(/site plan.*\.dxf o \.dwg/i)
    expect(result.assistantMessage.content).toMatch(/seminole|diagnostic/i)
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
            floor_width: 468,
            site_width: 765.77,
            max_height: 1010.71,
          },
          fit_summary: {
            comparison_unit: 'inch',
            basis: 'buildable_polygon',
            footprint_bbox: { x1: 0, y1: 0, x2: 468, y2: 792, width: 468, height: 792 },
            buildable_bbox: { x1: 100, y1: 100, x2: 865.77, y2: 1110.71, width: 765.77, height: 1010.71 },
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
    })

    expect(mockFetch).toHaveBeenCalledWith('/api/v2/site-fit/bridge/propose', expect.objectContaining({
      method: 'POST',
      body: expect.any(FormData),
    }))
    expect(result.assistantMessage.content).toMatch(/site-fit.*SEMINOLE2000/i)
    expect(result.assistantMessage.content).not.toMatch(/bridge/i)
    expect(result.assistantMessage.artifacts).toEqual(expect.arrayContaining([
      expect.objectContaining({
        kind: 'cad-review',
        title: expect.stringMatching(/diagnostic/i),
        review: expect.objectContaining({
          export: expect.objectContaining({
            ready: false,
            href: undefined,
            reason: expect.stringMatching(/diagnostic|apply|resultado/i),
          }),
        }),
      }),
      expect.objectContaining({
        kind: 'site-fit-proposal',
        proposal: expect.objectContaining({
          cadAnalysisId: 'cad-123',
        }),
      }),
    ]))
  })

  it('calls the bridge apply endpoint with cad analysis id and returns the real export artifact href', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        pipeline: 'site_fit_bridge_mvp_v1',
        scope: 'seminole-2000-only',
        plan_id: 'seminole-2000',
        plan_name: 'SEMINOLE2000',
        apply_id: 'apply-123',
        export_url: '/api/v2/site-fit/bridge/export/apply-123',
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
      cadAnalysisId: 'cad-123',
      siteConstraints: { unit: 'inch' },
    })

    expect(mockFetch).toHaveBeenCalledWith('/api/v2/site-fit/bridge/apply', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        plan_id: 'seminole-2000',
        site_constraints: { unit: 'inch' },
        candidate_id: 'baseline_preserved',
        cad_analysis_id: 'cad-123',
      }),
    }))
    expect(result.assistantMessage.artifacts).toEqual(expect.arrayContaining([
      expect.objectContaining({
        kind: 'site-fit-apply',
        apply: expect.objectContaining({
          applyId: 'apply-123',
          href: '/api/v2/site-fit/bridge/export/apply-123',
          exportUrl: '/api/v2/site-fit/bridge/export/apply-123',
        }),
      }),
    ]))
  })

  it('rejects unsupported attachments with the site-fit-lane-only message', async () => {
    const file = new File(['text'], 'notes.txt', { type: 'text/plain' })
    const result = await runChatAgentTool({
      prompt: 'Run CAD diagnostic',
      attachment: file,
    })

    expect(mockFetch).not.toHaveBeenCalled()
    expect(result.assistantMessage.content).toMatch(/solo.*site plan.*\.dxf\/\.dwg/i)
  })
})
