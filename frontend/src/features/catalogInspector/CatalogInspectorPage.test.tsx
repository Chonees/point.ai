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
    expect(screen.getByText('room-bedroom-2-f167749e3959')).toBeInTheDocument()
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
})
