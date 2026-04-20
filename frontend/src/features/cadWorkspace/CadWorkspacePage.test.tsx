import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CadWorkspacePage } from './CadWorkspacePage'

const mockFetch = vi.fn()
globalThis.fetch = mockFetch

describe('CadWorkspacePage', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  it('renders the separate CAD workspace copy', () => {
    render(<CadWorkspacePage />)

    expect(screen.getByText('DWG / DXF side-by-side extractor')).toBeInTheDocument()
    expect(screen.getByText(/separado del pipeline de imagen/i)).toBeInTheDocument()
  })

  it('shows extracted metadata and comparative canvas after upload', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        analysis_id: 'cad-123',
        source_name: 'dawson.dxf',
        source_format: 'dxf',
        canonical_unit: 'inch',
        conversion_status: 'native_dxf',
        conversion_note: null,
        floor_plan: {
          role: 'floor_plan',
          bbox: { x1: 0, y1: 0, x2: 600, y2: 300, width: 600, height: 300 },
          measurements: { width: 600, height: 300, source: 'dimensions' },
          summary: { entity_count: 4, line_count: 4, polyline_count: 0, text_count: 0 },
          entities: [
            {
              type: 'line',
              layer: 'A-WALL',
              start: { x: 0, y: 0 },
              end: { x: 600, y: 0 },
              points: [],
              text: null,
              position: null,
              bbox: { x1: 0, y1: 0, x2: 600, y2: 0, width: 600, height: 0 },
            },
          ],
        },
        site_plan: {
          role: 'site_plan',
          bbox: { x1: 0, y1: 0, x2: 480, y2: 700, width: 480, height: 700 },
          measurements: { width: 480, height: 700, source: 'geometry' },
          summary: { entity_count: 2, line_count: 0, polyline_count: 1, text_count: 1 },
          entities: [
            {
              type: 'polyline',
              layer: 'SITE',
              start: null,
              end: null,
              points: [{ x: 0, y: 0 }, { x: 480, y: 0 }, { x: 480, y: 700 }, { x: 0, y: 700 }, { x: 0, y: 0 }],
              text: null,
              position: null,
              bbox: { x1: 0, y1: 0, x2: 480, y2: 700, width: 480, height: 700 },
            },
          ],
        },
        side_by_side: { canonical_unit: 'inch', gap: 24, floor_width: 600, site_width: 480, max_height: 700 },
        fit_summary: {
          comparison_unit: 'inch',
          basis: 'bbox',
          footprint_bbox: { x1: 0, y1: 0, x2: 600, y2: 300, width: 600, height: 300 },
          property_bbox: { x1: 0, y1: 0, x2: 480, y2: 700, width: 480, height: 700 },
          buildable_bbox: { x1: 20, y1: 20, x2: 440, y2: 640, width: 420, height: 620 },
          width_delta: -180,
          height_delta: 320,
          fits_within_buildable_bbox: false,
        },
        warnings: ['Only one spatial view cluster was detected; site extraction may be incomplete.'],
      }),
    })

    render(<CadWorkspacePage />)

    const input = screen.getByLabelText('Archivo CAD') as HTMLInputElement
    const file = new File(['cad'], 'dawson.dxf', { type: 'application/dxf' })
    fireEvent.change(input, { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: /extraer floor \+ site/i }))

    await waitFor(() => {
      expect(screen.getByText('dawson.dxf')).toBeInTheDocument()
    })

    expect(screen.getByRole('img', { name: 'CAD side by side comparison' })).toBeInTheDocument()
    expect(screen.getByText(/floor plan \+ site plan a la misma escala/i)).toBeInTheDocument()
    expect(screen.getByText(/Only one spatial view cluster was detected/i)).toBeInTheDocument()
    expect(screen.getByText(/footprint exterior vs zona construible/i)).toBeInTheDocument()
    expect(screen.getByText(/el footprint excede el buildable por bbox/i)).toBeInTheDocument()
  })
})
