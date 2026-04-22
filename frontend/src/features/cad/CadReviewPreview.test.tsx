import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CadReviewPreview } from './CadReviewPreview'
import type { CadReviewArtifactData } from './contracts'

function makeReview(): CadReviewArtifactData {
  return {
    analysisId: 'analysis-1',
    sourceName: 'dawson.dxf',
    canonicalUnit: 'inch',
    floorPlan: {
      role: 'floor_plan',
      bbox: { x1: 0, y1: 0, x2: 468, y2: 792, width: 468, height: 792 },
      summary: { entity_count: 2, line_count: 0, polyline_count: 2, text_count: 0 },
      entities: [
        {
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
        },
      ],
      rooms: [
        {
          name: 'BEDROOM 2',
          polygon: [
            { x: 0, y: 0 },
            { x: 160, y: 0 },
            { x: 160, y: 192 },
            { x: 0, y: 192 },
            { x: 0, y: 0 },
          ],
          bbox: { x1: 0, y1: 0, x2: 160, y2: 192, width: 160, height: 192 },
          centroid: { x: 80, y: 96 },
          width: 160,
          height: 192,
          area: 30720,
          measurement_source: 'room_region',
        },
        {
          name: 'LIVING ROOM',
          polygon: [
            { x: 160, y: 0 },
            { x: 468, y: 0 },
            { x: 468, y: 264 },
            { x: 160, y: 264 },
            { x: 160, y: 0 },
          ],
          bbox: { x1: 160, y1: 0, x2: 468, y2: 264, width: 308, height: 264 },
          centroid: { x: 314, y: 132 },
          width: 308,
          height: 264,
          area: 81312,
          measurement_source: 'label_region_partition',
        },
      ],
      measurements: { width: 468, height: 792, source: 'dimensions' },
    },
    sitePlan: {
      role: 'site_plan',
      bbox: { x1: 100, y1: 100, x2: 650, y2: 980, width: 550, height: 880 },
      summary: { entity_count: 1, line_count: 0, polyline_count: 1, text_count: 0 },
      entities: [
        {
          type: 'polyline',
          layer: 'SETBACKS',
          points: [
            { x: 100, y: 100 },
            { x: 650, y: 100 },
            { x: 620, y: 980 },
            { x: 130, y: 980 },
            { x: 100, y: 100 },
          ],
          bbox: { x1: 100, y1: 100, x2: 650, y2: 980, width: 550, height: 880 },
        },
      ],
      rooms: [],
      measurements: { width: 550, height: 880, source: 'geometry' },
    },
    fitSummary: {
      comparison_unit: 'inch',
      basis: 'buildable_polygon',
      footprint_bbox: { x1: 0, y1: 0, x2: 468, y2: 792, width: 468, height: 792 },
      buildable_bbox: { x1: 130, y1: 120, x2: 680, y2: 1000, width: 550, height: 880 },
      buildable_polygon: [
        { x: 210, y: 120 },
        { x: 600, y: 120 },
        { x: 680, y: 1000 },
        { x: 130, y: 1000 },
        { x: 210, y: 120 },
      ],
      width_delta: 82,
      height_delta: 88,
      fits_within_buildable_bbox: true,
      fits_within_buildable_polygon: false,
    },
    warnings: [],
    export: {
      ready: true,
      href: '/api/cad-workspace/export-overlay/analysis-1',
    },
  }
}

describe('CadReviewPreview', () => {
  it('renders the precise overlay labels, room ids, and overflow fragments', () => {
    const { container } = render(<CadReviewPreview review={makeReview()} />)

    expect(screen.getByText("Buildable 45'-10\" · 550 in")).toBeInTheDocument()
    expect(screen.getByText("Buildable 73'-4\" · 880 in")).toBeInTheDocument()
    expect(screen.getByText("Footprint 39'-0\" · 468 in")).toBeInTheDocument()
    expect(screen.getByText("Footprint 66'-0\" · 792 in")).toBeInTheDocument()

    expect(screen.getByText('BEDROOM 2')).toBeInTheDocument()
    expect(screen.getByText("13'-4\" × 16'-0\"")).toBeInTheDocument()
    expect(screen.getByText('LIVING ROOM')).toBeInTheDocument()

    const overflow = container.querySelector('[data-testid="overflow-fragments"]')
    expect(overflow).not.toBeNull()
    expect(overflow?.querySelectorAll('line').length ?? 0).toBeGreaterThan(0)
  })

  it('collapses to a compact diagnostic when the exact overlay is not available yet', () => {
    const review = makeReview()
    review.fitSummary = {
      comparison_unit: 'inch',
      basis: 'unavailable',
      fits_within_buildable_bbox: null,
      fits_within_buildable_polygon: null,
      width_delta: null,
      height_delta: null,
    }
    review.warnings = ['No pude identificar un buildable real todavia.']

    render(<CadReviewPreview review={review} />)

    expect(screen.getByText(/preview exacto no disponible todav/i)).toBeInTheDocument()
    expect(screen.getAllByText(/no pude identificar un buildable real todavia/i).length).toBeGreaterThan(0)
    expect(screen.queryByLabelText(/cad overlay comparison/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/^Footprint$/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/^Area construible$/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Overlay del footprint sobre el área construible/i)).not.toBeInTheDocument()
  })
})
