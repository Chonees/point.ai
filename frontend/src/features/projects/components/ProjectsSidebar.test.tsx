import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ProjectsSidebar } from './ProjectsSidebar'

describe('ProjectsSidebar', () => {
  it('does not nest buttons inside project selection buttons', () => {
    const { container } = render(
      <ProjectsSidebar
        projects={[
          {
            id: 'project-1',
            name: 'Pointe Homes',
            createdAt: '2026-04-20T10:00:00.000Z',
            updatedAt: '2026-04-20T11:00:00.000Z',
            planCount: 1,
          },
        ]}
        loading={false}
        selectedProjectId={null}
        onSelectProject={vi.fn()}
        onCreateProject={vi.fn()}
        onDeleteProject={vi.fn()}
        onRenameProject={vi.fn()}
      />,
    )

    expect(container.querySelector('button button')).toBeNull()
  })

  it('separates project selection from rename action', () => {
    const onSelectProject = vi.fn()

    render(
      <ProjectsSidebar
        projects={[
          {
            id: 'project-1',
            name: 'Pointe Homes',
            createdAt: '2026-04-20T10:00:00.000Z',
            updatedAt: '2026-04-20T11:00:00.000Z',
            planCount: 1,
          },
        ]}
        loading={false}
        selectedProjectId={null}
        onSelectProject={onSelectProject}
        onCreateProject={vi.fn()}
        onDeleteProject={vi.fn()}
        onRenameProject={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /rename project pointe homes/i }))

    expect(onSelectProject).not.toHaveBeenCalled()
  })
})
