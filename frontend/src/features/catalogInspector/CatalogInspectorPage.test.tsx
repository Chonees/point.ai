import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import fixture from './catalogInspector.fixture.json'
import { CatalogInspectorPage } from './CatalogInspectorPage'

const topologyWithoutKitchen = {
  ...fixture,
  rooms: fixture.rooms.filter((room) => room.room_id !== 'room-kitchen-c5e1fe755eb1'),
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
    expect(screen.getByTestId('selected-room-id')).toHaveTextContent('room-bedroom-2-f167749e3959')
  })

  it('drops a stale selected room when the topology changes', () => {
    const { rerender } = render(<CatalogInspectorPage topology={fixture} />)

    fireEvent.click(screen.getByRole('button', { name: /select kitchen/i }))
    expect(screen.getByRole('heading', { name: 'KITCHEN' })).toBeInTheDocument()

    rerender(<CatalogInspectorPage topology={topologyWithoutKitchen} />)

    expect(screen.queryByRole('heading', { name: 'KITCHEN' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'BEDROOM 2' })).toBeInTheDocument()
    expect(within(screen.getByTestId('catalog-inspector-canvas')).queryByTestId('room-room-kitchen-c5e1fe755eb1')).not.toBeInTheDocument()
  })

  it('renders wall graph metrics and toggles wall overlays', () => {
    render(<CatalogInspectorPage topology={fixture} />)

    expect(screen.getByText(/shared walls/i)).toBeInTheDocument()
    expect(screen.getByText(/inferred walls/i)).toBeInTheDocument()
    expect(screen.getAllByTestId(/wall-/).length).toBeGreaterThan(0)

    const wallsToggle = screen.getByRole('checkbox', { name: /walls/i })
    fireEvent.click(wallsToggle)

    expect(screen.queryAllByTestId(/wall-/)).toHaveLength(0)
  })

  it('shows selected room wall details including inferred boundaries', () => {
    render(<CatalogInspectorPage topology={fixture} />)

    fireEvent.click(screen.getByRole('button', { name: /select bedroom 2/i }))

    expect(screen.getByText(/connected walls/i)).toBeInTheDocument()
    expect(screen.getByText(/inferred_from_bbox/i)).toBeInTheDocument()
  })
})
