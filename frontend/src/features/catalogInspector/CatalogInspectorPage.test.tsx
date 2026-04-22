import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import fixture from './catalogInspector.fixture.json'
import { CatalogInspectorPage } from './CatalogInspectorPage'

describe('CatalogInspectorPage', () => {
  it('renders the real topology, lets you select a room, and toggles ids and adjacency layers', () => {
    render(<CatalogInspectorPage topology={fixture} />)

    expect(screen.getByRole('heading', { name: /topology inspector/i })).toBeInTheDocument()
    expect(screen.getByText('SEMINOLE2000')).toBeInTheDocument()
    expect(screen.getAllByText('KITCHEN').length).toBeGreaterThan(0)
    expect(screen.getAllByText('BEDROOM 2').length).toBeGreaterThan(0)

    const canvas = screen.getByTestId('catalog-inspector-canvas')
    expect(within(canvas).queryByTestId('room-id-label-room-kitchen-c5e1fe755eb1')).not.toBeInTheDocument()
    expect(within(canvas).queryAllByTestId(/^adjacency-link-/).length).toBe(0)

    fireEvent.click(screen.getByTestId('room-room-kitchen-c5e1fe755eb1'))

    expect(screen.getByRole('heading', { name: 'KITCHEN' })).toBeInTheDocument()
    expect(screen.getByText('room-kitchen-c5e1fe755eb1')).toBeInTheDocument()
    expect(screen.getByText(/adjacent rooms/i)).toBeInTheDocument()
    expect(screen.getAllByText('BEDROOM 2').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('checkbox', { name: /room ids/i }))

    expect(within(canvas).getByTestId('room-id-label-room-kitchen-c5e1fe755eb1')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('checkbox', { name: /adjacency/i }))

    expect(within(canvas).queryAllByTestId(/^adjacency-link-/).length).toBeGreaterThan(0)
  })
})
