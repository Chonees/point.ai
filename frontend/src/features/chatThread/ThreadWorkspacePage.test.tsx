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
            preview: 'Floor plan disponible',
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
    expect(screen.getByPlaceholderText(/pedile algo a point/i)).toBeInTheDocument()
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

    fireEvent.change(screen.getByPlaceholderText(/pedile algo a point/i), {
      target: { value: 'Generame un floor plan' },
    })
    fireEvent.click(screen.getByRole('button', { name: /enviar/i }))

    expect(onSubmitMessage).toHaveBeenCalledWith('Generame un floor plan')
  })
})
