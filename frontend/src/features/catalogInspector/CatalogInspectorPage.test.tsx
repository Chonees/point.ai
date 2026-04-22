import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import fixture from './catalogInspector.fixture.json'
import { CatalogInspectorPage } from './CatalogInspectorPage'

const kitchenRoom = fixture.rooms.find((room) => room.name === 'KITCHEN')!
const bedroom2Room = fixture.rooms.find((room) => room.name === 'BEDROOM 2')!
const rawWallTraceCount = fixture.cad_traces.filter((trace) => trace.trace_kind === 'wall').length
const rawDoorTraceCount = fixture.cad_traces.filter((trace) => trace.trace_kind === 'door').length
const rawWindowTraceCount = fixture.cad_traces.filter((trace) => trace.trace_kind === 'window').length
const hostedOpeningCount = fixture.openings?.length ?? 0
const snappedSharedWallCount = fixture.walls.filter(
  (wall) => !wall.is_exterior && wall.trace_support_status === 'snapped_to_trace',
).length
const unsupportedSharedWallCount = fixture.walls.filter(
  (wall) => !wall.is_exterior && wall.trace_support_status === 'unsupported',
).length

const topologyWithoutKitchen = {
  ...fixture,
  rooms: fixture.rooms.filter((room) => room.room_id !== kitchenRoom.room_id),
}

describe('CatalogInspectorPage', () => {
  it('moves selection with keyboard and updates the sidebar for a different room', () => {
    render(<CatalogInspectorPage topology={fixture} />)

    fireEvent.click(screen.getByRole('button', { name: /select kitchen/i }))
    expect(screen.getByRole('heading', { name: 'KITCHEN' })).toBeInTheDocument()

    const bedroom2Button = screen.getByRole('button', { name: /select bedroom 2/i })
    bedroom2Button.focus()
    fireEvent.keyDown(bedroom2Button, { key: 'Enter', code: 'Enter' })

    expect(screen.getByRole('heading', { name: 'BEDROOM 2' })).toBeInTheDocument()
    expect(screen.getByTestId('selected-room-id')).toHaveTextContent(bedroom2Room.room_id)
  })

  it('drops a stale selected room when the topology changes', () => {
    const { rerender } = render(<CatalogInspectorPage topology={fixture} />)

    fireEvent.click(screen.getByRole('button', { name: /select kitchen/i }))
    expect(screen.getByRole('heading', { name: 'KITCHEN' })).toBeInTheDocument()

    rerender(<CatalogInspectorPage topology={topologyWithoutKitchen} />)

    expect(screen.queryByRole('heading', { name: 'KITCHEN' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'BEDROOM 2' })).toBeInTheDocument()
    expect(within(screen.getByTestId('catalog-inspector-canvas')).queryByTestId(`room-${kitchenRoom.room_id}`)).not.toBeInTheDocument()
  })

  it('renders wall graph metrics and toggles wall overlays', () => {
    render(<CatalogInspectorPage topology={fixture} />)

    expect(screen.getAllByText(/shared walls/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/^inferred walls$/i)).toBeInTheDocument()
    expect(screen.getAllByTestId(/^wall-/).length).toBeGreaterThan(0)

    const wallsToggle = screen.getByRole('checkbox', { name: /walls/i })
    fireEvent.click(wallsToggle)

    expect(screen.queryAllByTestId(/^wall-/)).toHaveLength(0)
  })

  it('shows selected room wall details including provenance and confidence', () => {
    render(<CatalogInspectorPage topology={fixture} />)

    fireEvent.click(screen.getByRole('button', { name: /select bedroom 2/i }))

    expect(screen.getByText(/connected walls/i)).toBeInTheDocument()
    expect(screen.getAllByText(/supported adjacency/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/provenance/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/snapped to trace/i).length).toBeGreaterThan(0)
  })

  it('shows wall ownership metadata in the selected wall and room panels', () => {
    render(<CatalogInspectorPage topology={fixture} />)

    fireEvent.click(screen.getByRole('button', { name: /^Shared$/i }))
    expect(screen.getByText(/boundary kind/i)).toBeInTheDocument()
    expect(screen.getByText(/owner rooms/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /select bedroom 2/i }))
    expect(screen.getAllByText(/owned walls/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/^shared walls$/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/exterior walls/i)).toBeInTheDocument()
  })

  it('shows expected isolated status for patio', () => {
    render(<CatalogInspectorPage topology={fixture} />)

    fireEvent.click(screen.getByRole('button', { name: /select patio/i }))

    expect(screen.getAllByText(/connected/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/opening adjacency/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/heuristic adjacency/i).length).toBeGreaterThan(0)
  })

  it('shows opening adjacency for master bedroom and dining without faking wall adjacency', () => {
    render(<CatalogInspectorPage topology={fixture} />)

    fireEvent.click(screen.getByRole('button', { name: /select mstr\. bedroom/i }))
    expect(screen.getAllByText(/opening adjacency/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/^LIVING ROOM$/i).length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: /select dining/i }))
    expect(screen.getAllByText(/opening adjacency/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/^PATIO$/i).length).toBeGreaterThan(0)
  })

  it('renders raw wall traces and toggles them off', () => {
    render(<CatalogInspectorPage topology={fixture} />)

    expect(screen.getByRole('checkbox', { name: /raw wall traces/i })).toBeChecked()
    expect(screen.getAllByTestId(/raw-wall-trace-/).length).toBe(rawWallTraceCount)

    const tracesToggle = screen.getByRole('checkbox', { name: /raw wall traces/i })
    fireEvent.click(tracesToggle)

    expect(screen.queryAllByTestId(/raw-wall-trace-/)).toHaveLength(0)
  })

  it('renders door and window traces separately from wall traces', () => {
    render(<CatalogInspectorPage topology={fixture} />)

    expect(screen.getAllByText(/^Door traces$/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/^Window traces$/i).length).toBeGreaterThan(0)
    expect(screen.getByRole('checkbox', { name: /door traces/i })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /window traces/i })).toBeChecked()
    expect(screen.getAllByTestId(/raw-door-trace-/).length).toBe(rawDoorTraceCount)
    expect(screen.getAllByTestId(/raw-window-trace-/).length).toBe(rawWindowTraceCount)

    fireEvent.click(screen.getByRole('checkbox', { name: /door traces/i }))
    expect(screen.queryAllByTestId(/raw-door-trace-/)).toHaveLength(0)
    expect(screen.getAllByTestId(/raw-window-trace-/).length).toBe(rawWindowTraceCount)
    expect(screen.getAllByTestId(/raw-wall-trace-/).length).toBe(rawWallTraceCount)
  })

  it('renders hosted openings and shows selected opening ownership', () => {
    render(<CatalogInspectorPage topology={fixture} />)

    expect(screen.getByRole('checkbox', { name: /hosted openings/i })).toBeChecked()
    expect(screen.getAllByTestId(/^opening-/).length).toBe(hostedOpeningCount)

    fireEvent.click(screen.getAllByTestId(/^opening-/)[0])

    expect(screen.getByTestId('selected-opening-panel')).toBeInTheDocument()
    expect(screen.getByText(/host wall/i)).toBeInTheDocument()
    expect(screen.getByText(/connected rooms/i)).toBeInTheDocument()
  })

  it('filters snapped walls and lets you navigate the focused issue list', () => {
    render(<CatalogInspectorPage topology={fixture} />)

    fireEvent.click(screen.getByRole('button', { name: /^Snapped$/i }))

    expect(screen.getByTestId('focus-mode-value')).toHaveTextContent('snapped')
    expect(screen.getAllByTestId(/focus-wall-/)).toHaveLength(snappedSharedWallCount)
    expect(screen.getAllByTestId(/^wall-/)).toHaveLength(snappedSharedWallCount)

    const firstWallId = screen.getByTestId('selected-wall-id').textContent
    fireEvent.click(screen.getAllByRole('button', { name: /next issue/i })[0])

    expect(screen.getByTestId('selected-wall-id').textContent).not.toEqual(firstWallId)
  })

  it('shows unsupported focus mode only for unresolved shared walls', () => {
    render(<CatalogInspectorPage topology={fixture} />)

    fireEvent.click(screen.getByRole('button', { name: /^Unsupported$/i }))

    expect(screen.getByTestId('focus-mode-value')).toHaveTextContent('unsupported')
    expect(screen.queryAllByTestId(/focus-wall-/)).toHaveLength(unsupportedSharedWallCount)
    expect(screen.queryAllByTestId(/^wall-/)).toHaveLength(unsupportedSharedWallCount)

    if (unsupportedSharedWallCount === 0) {
      expect(screen.queryByTestId('selected-wall-panel')).not.toBeInTheDocument()
    } else {
      expect(screen.getByTestId('selected-wall-panel')).toBeInTheDocument()
    }
  })
})
