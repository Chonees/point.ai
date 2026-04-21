import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { PlansGrid } from './PlansGrid'

describe('PlansGrid', () => {
  it('uses thread-first language in the chat-first shell', () => {
    render(
      <PlansGrid
        project={{
          id: 'project-1',
          name: 'Pointe Homes',
          createdAt: '2026-04-20T10:00:00.000Z',
          updatedAt: '2026-04-20T11:00:00.000Z',
          planCount: 1,
        }}
        plans={[]}
        plansLoading={false}
        onOpenPlan={vi.fn()}
        onCreatePlan={vi.fn()}
        onDeletePlan={vi.fn()}
        onRenamePlan={vi.fn()}
      />,
    )

    expect(screen.getByText(/new thread/i)).toBeInTheDocument()
    expect(screen.getByText(/no threads in this project yet/i)).toBeInTheDocument()
    expect(screen.getByText(/start the ai workflow/i)).toBeInTheDocument()
  })

  it('submits thread creation through the existing create-plan callback', () => {
    const onCreatePlan = vi.fn().mockResolvedValue(undefined)

    render(
      <PlansGrid
        project={{
          id: 'project-1',
          name: 'Pointe Homes',
          createdAt: '2026-04-20T10:00:00.000Z',
          updatedAt: '2026-04-20T11:00:00.000Z',
          planCount: 1,
        }}
        plans={[]}
        plansLoading={false}
        onOpenPlan={vi.fn()}
        onCreatePlan={onCreatePlan}
        onDeletePlan={vi.fn()}
        onRenamePlan={vi.fn()}
      />,
    )

    fireEvent.change(screen.getByPlaceholderText(/fit dawson/i), { target: { value: 'Resize option A' } })
    fireEvent.click(screen.getByRole('button', { name: /add thread/i }))

    expect(onCreatePlan).toHaveBeenCalledWith('Resize option A')
  })
})
