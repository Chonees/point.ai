import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ThreadWorkspacePage } from './ThreadWorkspacePage'

describe('ThreadWorkspacePage', () => {
  it('renders thread list, transcript, and composer in a single shell', () => {
    const onSelectThread = vi.fn()

    render(
      <ThreadWorkspacePage
        projectName="Pointe Homes"
        threads={[
          {
            id: 'thread-1',
            projectId: 'project-1',
            title: 'Fit Dawson',
            lastActivityIso: '2026-04-20T11:00:00.000Z',
            preview: 'Site-fit workspace ready',
          },
        ]}
        selectedThreadId="thread-1"
        messages={[
          {
            id: 'm-1',
            role: 'assistant',
            content: 'Listo para continuar.',
            createdAtIso: '2026-04-20T11:00:00.000Z',
            artifacts: [],
          },
        ]}
        onSelectThread={onSelectThread}
        onSubmitMessage={vi.fn()}
      />,
    )

    expect(screen.getByText('Pointe Homes')).toBeInTheDocument()
    expect(screen.getAllByText('Fit Dawson').length).toBe(2)
    expect(screen.getByText('Listo para continuar.')).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/site plan dxf\/dwg/i)).toBeInTheDocument()
  })

  it('submits the composer content', () => {
    const onSubmitMessage = vi.fn()

    render(
      <ThreadWorkspacePage
        projectName="Pointe Homes"
        threads={[]}
        selectedThreadId={null}
        messages={[]}
        onSelectThread={vi.fn()}
        onSubmitMessage={onSubmitMessage}
      />,
    )

    fireEvent.change(screen.getByPlaceholderText(/site plan dxf\/dwg/i), {
      target: { value: 'Generame un floor plan' },
    })
    fireEvent.click(screen.getByRole('button', { name: /enviar/i }))

    expect(onSubmitMessage).toHaveBeenCalledWith({
      message: 'Generame un floor plan',
      attachment: null,
    })
  })

  it('submits the selected attachment together with the chat prompt', () => {
    const onSubmitMessage = vi.fn()

    render(
      <ThreadWorkspacePage
        projectName="Pointe Homes"
        threads={[]}
        selectedThreadId={null}
        messages={[]}
        onSelectThread={vi.fn()}
        onSubmitMessage={onSubmitMessage}
      />,
    )

    const input = screen.getByLabelText(/adjuntar archivo/i) as HTMLInputElement
    const file = new File(['cad'], 'dawson.dxf', { type: 'application/dxf' })

    fireEvent.change(input, { target: { files: [file] } })
    fireEvent.change(screen.getByPlaceholderText(/site plan dxf\/dwg/i), {
      target: { value: 'Fit Seminole 2000 on this site plan' },
    })
    fireEvent.click(screen.getByRole('button', { name: /enviar/i }))

    expect(onSubmitMessage).toHaveBeenCalledWith({
      message: 'Fit Seminole 2000 on this site plan',
      attachment: file,
    })
  })

  it('renders the CAD review inline inside the transcript and keeps export inside the card', () => {
    render(
      <ThreadWorkspacePage
        projectName="Pointe Homes"
        threads={[
          {
            id: 'thread-1',
            projectId: 'project-1',
            title: 'Fit Dawson',
            lastActivityIso: '2026-04-20T11:00:00.000Z',
            preview: 'Site-fit workspace ready',
          },
        ]}
        selectedThreadId="thread-1"
        messages={[
          {
            id: 'm-1',
            role: 'assistant',
            content: 'Abramos el ultimo overlay.',
            createdAtIso: '2026-04-20T11:00:00.000Z',
            artifacts: [
              {
                id: 'cad-review-1',
                kind: 'cad-review',
                title: 'CAD diagnostic review',
                review: {
                  analysisId: 'demo',
                  sourceName: 'dawson.dxf',
                  canonicalUnit: 'inch',
                  floorPlan: {
                    role: 'floor_plan',
                    bbox: { x1: 0, y1: 0, x2: 468, y2: 792, width: 468, height: 792 },
                    summary: { entity_count: 0, line_count: 0, polyline_count: 0, text_count: 0 },
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
                    ],
                    measurements: { width: 468, height: 792, source: 'dimensions' },
                  },
                  sitePlan: {
                    role: 'site_plan',
                    bbox: { x1: 100, y1: 100, x2: 865.77, y2: 1110.71, width: 765.77, height: 1010.71 },
                    summary: { entity_count: 0, line_count: 0, polyline_count: 0, text_count: 0 },
                    entities: [
                      {
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
                      },
                    ],
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
                    width_delta: 297.77,
                    height_delta: 218.71,
                  },
                  warnings: [],
                  export: {
                    ready: true,
                    href: '/api/cad-workspace/export-overlay/demo',
                  },
                },
              },
            ],
          },
        ]}
        onSelectThread={vi.fn()}
        onSubmitMessage={vi.fn()}
      />,
    )

    expect(screen.getByText('Fit Seminole 2000 on this site plan')).toBeInTheDocument()
    expect(screen.getByText('Run CAD diagnostic')).toBeInTheDocument()
    expect(screen.getAllByText(/Footprint/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Area construible/i).length).toBeGreaterThan(0)
    expect(screen.getByText("Buildable 63'-9 3/4\" · 765.77 in")).toBeInTheDocument()
    expect(screen.getByText('BEDROOM 2')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /download diagnostic overlay dxf/i })).toHaveAttribute('href', '/api/cad-workspace/export-overlay/demo')
  })

  it('restricts the hidden file input to site plan DXF/DWG attachments', () => {
    render(
      <ThreadWorkspacePage
        projectName="Pointe Homes"
        threads={[]}
        selectedThreadId={null}
        messages={[]}
        onSelectThread={vi.fn()}
        onSubmitMessage={vi.fn()}
      />,
    )

    expect(screen.getByLabelText(/adjuntar archivo/i)).toHaveAttribute('accept', '.dxf,.dwg')
    expect(screen.queryByText('Generate from image')).not.toBeInTheDocument()
  })
})
