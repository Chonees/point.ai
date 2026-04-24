import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ThreadMessageList } from './ThreadMessageList'
import type { ThreadMessage } from '../thread.types'

describe('ThreadMessageList', () => {
  it('lets cad-review artifacts span the full message width instead of the shared two-column grid', () => {
    const messages: ThreadMessage[] = [{
      id: 'm-1',
      role: 'assistant',
      content: 'Revision lista.',
      createdAtIso: '2026-04-21T17:00:00.000Z',
      artifacts: [
        {
          id: 'cad-source-1',
          kind: 'cad-source',
          title: 'lolo.dxf',
          description: 'Adjunto enviado al agente desde el chat.',
        },
        {
          id: 'cad-review-1',
          kind: 'cad-review',
          title: 'CAD fit review',
          review: {
            analysisId: 'analysis-1',
            sourceName: 'lolo.dxf',
            canonicalUnit: 'inch',
            floorPlan: {
              role: 'floor_plan',
              bbox: { x1: 0, y1: 0, x2: 468, y2: 792, width: 468, height: 792 },
              summary: { entity_count: 1, line_count: 0, polyline_count: 1, text_count: 0 },
              entities: [{
                type: 'polyline',
                layer: 'WALLS',
                points: [
                  { x: 0, y: 0 },
                  { x: 468, y: 0 },
                  { x: 468, y: 792 },
                  { x: 0, y: 792 },
                  { x: 0, y: 0 },
                ],
                bbox: { x1: 0, y1: 0, x2: 468, y2: 792, width: 468, height: 792 },
              }],
              rooms: [],
              measurements: { width: 468, height: 792, source: 'dimensions' },
            },
            sitePlan: {
              role: 'site_plan',
              bbox: { x1: 100, y1: 100, x2: 865.77, y2: 1110.71, width: 765.77, height: 1010.71 },
              summary: { entity_count: 1, line_count: 0, polyline_count: 1, text_count: 0 },
              entities: [{
                type: 'polyline',
                layer: 'SETBACKS',
                points: [
                  { x: 160, y: 100 },
                  { x: 780, y: 100 },
                  { x: 865.77, y: 1110.71 },
                  { x: 100, y: 1110.71 },
                  { x: 160, y: 100 },
                ],
                bbox: { x1: 100, y1: 100, x2: 865.77, y2: 1110.71, width: 765.77, height: 1010.71 },
              }],
              rooms: [],
              measurements: { width: 765.77, height: 1010.71, source: 'buildable_bbox' },
            },
            fitSummary: {
              comparison_unit: 'inch',
              basis: 'buildable_polygon',
              footprint_bbox: { x1: 0, y1: 0, x2: 468, y2: 792, width: 468, height: 792 },
              buildable_bbox: { x1: 100, y1: 100, x2: 865.77, y2: 1110.71, width: 765.77, height: 1010.71 },
              buildable_polygon: [
                { x: 160, y: 100 },
                { x: 780, y: 100 },
                { x: 865.77, y: 1110.71 },
                { x: 100, y: 1110.71 },
                { x: 160, y: 100 },
              ],
              fits_within_buildable_bbox: true,
              fits_within_buildable_polygon: false,
            },
            warnings: [],
            export: { ready: false, reason: 'blocked' },
          },
        },
      ],
    }]

    const { container } = render(<ThreadMessageList messages={messages} />)

    const fullWidthWrapper = container.querySelector('[data-artifact-kind="cad-review"]')
    expect(fullWidthWrapper).toHaveClass('md:col-span-2')
    expect(screen.getByText('CAD fit review')).toBeInTheDocument()
  })

  it('renders site-fit proposal artifacts full-width and exposes the apply action', () => {
    const onApply = vi.fn()
    const messages: ThreadMessage[] = [{
      id: 'm-1',
      role: 'assistant',
      content: 'Te dejo la propuesta.',
      createdAtIso: '2026-04-24T18:00:00.000Z',
      artifacts: [{
        id: 'proposal-1',
        kind: 'site-fit-proposal',
        title: 'SEMINOLE2000 proposal',
        proposal: {
          planId: 'seminole-2000',
          planName: 'SEMINOLE2000',
          candidateId: 'baseline_preserved',
          cadAnalysisId: 'cad-123',
          siteConstraints: { unit: 'inch' },
          summary: 'Keep the current plan unchanged.',
          fitStatus: 'fit_ready',
          changeCount: 0,
          candidateStrategy: 'preserve_existing_layout',
          footprint: {
            current: { x1: 0, y1: 0, x2: 468, y2: 792, width: 468, height: 792 },
            projected: { x1: 0, y1: 0, x2: 468, y2: 792, width: 468, height: 792 },
            buildable: { x1: 3180, y1: 180, x2: 3900, y2: 1260, width: 720, height: 1080 },
            widthDelta: 252,
            heightDelta: 288,
          },
          violationMessages: [],
          blockerMessages: [],
          mutationHintCount: 0,
          changedRoomIds: [],
          warnings: [],
        },
      }],
    }]

    const { container } = render(<ThreadMessageList messages={messages} onApplySiteFitProposal={onApply} />)

    expect(container.querySelector('[data-artifact-kind="site-fit-proposal"]')).toHaveClass('md:col-span-2')
    expect(screen.getByText(/footprint actual/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /apply proposal/i }))
    expect(onApply).toHaveBeenCalledWith(expect.objectContaining({ candidateId: 'baseline_preserved' }))
  })

  it('renders site-fit apply artifacts full-width', () => {
    const messages: ThreadMessage[] = [{
      id: 'm-2',
      role: 'assistant',
      content: 'Aplique la propuesta.',
      createdAtIso: '2026-04-24T18:01:00.000Z',
      artifacts: [{
        id: 'apply-1',
        kind: 'site-fit-apply',
        title: 'Applied site-fit result',
        apply: {
          planId: 'seminole-2000',
          planName: 'SEMINOLE2000',
          candidateId: 'baseline_preserved',
          applyId: 'apply-123',
          applyStatus: 'applied',
          complianceStatus: 'pass',
          changeCount: 1,
          changedRoomIds: ['BEDROOM_2'],
          beforeFootprint: { x1: 0, y1: 0, x2: 480, y2: 792, width: 480, height: 792 },
          afterFootprint: { x1: 0, y1: 0, x2: 468, y2: 792, width: 468, height: 792 },
          href: '/api/v2/site-fit/bridge/export/apply-123',
          exportUrl: '/api/v2/site-fit/bridge/export/apply-123',
          preview: {
            analysisId: 'apply-123',
            sourceName: 'SEMINOLE2000 applied',
            canonicalUnit: 'inch',
            floorPlan: {
              role: 'floor_plan',
              bbox: { x1: 0, y1: 0, x2: 468, y2: 792, width: 468, height: 792 },
              summary: { entity_count: 1, line_count: 1, polyline_count: 0, text_count: 0 },
              entities: [{
                type: 'line',
                layer: 'BRIDGE_APPLY_PLAN',
                start: { x: 0, y: 0 },
                end: { x: 468, y: 0 },
                points: [],
                bbox: { x1: 0, y1: 0, x2: 468, y2: 0, width: 468, height: 0 },
              }],
              rooms: [{
                name: 'BEDROOM 2',
                polygon: [
                  { x: 0, y: 0 },
                  { x: 120, y: 0 },
                  { x: 120, y: 120 },
                  { x: 0, y: 120 },
                  { x: 0, y: 0 },
                ],
                bbox: { x1: 0, y1: 0, x2: 120, y2: 120, width: 120, height: 120 },
                centroid: { x: 60, y: 60 },
                width: 120,
                height: 120,
                area: 14400,
                measurement_source: 'catalog',
              }],
              measurements: { width: 468, height: 792, source: 'dimensions' },
            },
            sitePlan: {
              role: 'site_plan',
              bbox: { x1: 3180, y1: 180, x2: 3900, y2: 1260, width: 720, height: 1080 },
              summary: { entity_count: 1, line_count: 0, polyline_count: 1, text_count: 0 },
              entities: [{
                type: 'polyline',
                layer: 'SETBACKS',
                points: [
                  { x: 3180, y: 180 },
                  { x: 3900, y: 180 },
                  { x: 3900, y: 1260 },
                  { x: 3180, y: 1260 },
                  { x: 3180, y: 180 },
                ],
                bbox: { x1: 3180, y1: 180, x2: 3900, y2: 1260, width: 720, height: 1080 },
              }],
              rooms: [],
              measurements: { width: 720, height: 1080, source: 'buildable_bbox' },
            },
            fitSummary: {
              comparison_unit: 'inch',
              basis: 'buildable_polygon',
              footprint_bbox: { x1: 0, y1: 0, x2: 468, y2: 792, width: 468, height: 792 },
              registered_footprint_bbox: { x1: 3180, y1: 180, x2: 3648, y2: 972, width: 468, height: 792 },
              buildable_bbox: { x1: 3180, y1: 180, x2: 3900, y2: 1260, width: 720, height: 1080 },
              buildable_polygon: [
                { x: 3180, y: 180 },
                { x: 3900, y: 180 },
                { x: 3900, y: 1260 },
                { x: 3180, y: 1260 },
                { x: 3180, y: 180 },
              ],
              fits_within_buildable_bbox: true,
              fits_within_buildable_polygon: true,
            },
            warnings: [],
            export: { ready: false, reason: 'preview only' },
          },
          rooms: [{
            name: 'BEDROOM 2',
            width: 120,
            height: 120,
            area: 14400,
          }],
          warnings: [],
        },
      }],
    }]

    const { container } = render(<ThreadMessageList messages={messages} />)

    expect(container.querySelector('[data-artifact-kind="site-fit-apply"]')).toHaveClass('md:col-span-2')
    expect(screen.getByText('Applied site-fit result')).toBeInTheDocument()
    expect(screen.getByText(/medidas nuevas por room/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /download applied dxf/i })).toHaveAttribute(
      'href',
      '/api/v2/site-fit/bridge/export/apply-123',
    )
    expect(screen.getByRole('img', { name: /cad overlay comparison/i })).toBeInTheDocument()
  })
})
