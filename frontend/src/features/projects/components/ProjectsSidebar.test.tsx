import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ProjectsSidebar } from './ProjectsSidebar'

const project = {
  id: 'project-1',
  name: 'Seminole rollout',
  planCount: 3,
  createdAt: '2026-04-01T00:00:00Z',
  updatedAt: '2026-04-20T00:00:00Z',
}

describe('ProjectsSidebar', () => {
  it('does not render nested buttons inside a project card', () => {
    const { container } = render(
      <ProjectsSidebar
        projects={[project]}
        loading={false}
        selectedProjectId={null}
        onSelectProject={vi.fn()}
        onCreateProject={vi.fn().mockResolvedValue(undefined)}
        onDeleteProject={vi.fn().mockResolvedValue(undefined)}
        onRenameProject={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    expect(screen.getByText('Rename').closest('button')).toBeInTheDocument()
    expect(screen.getByText('Delete').closest('button')).toBeInTheDocument()
    expect(container.querySelector('button button')).toBeNull()
  })

  it('does not select the project when rename is clicked', () => {
    const onSelectProject = vi.fn()

    render(
      <ProjectsSidebar
        projects={[project]}
        loading={false}
        selectedProjectId={null}
        onSelectProject={onSelectProject}
        onCreateProject={vi.fn().mockResolvedValue(undefined)}
        onDeleteProject={vi.fn().mockResolvedValue(undefined)}
        onRenameProject={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    fireEvent.click(screen.getByText('Rename').closest('button')!)

    expect(onSelectProject).not.toHaveBeenCalled()
    expect(screen.getByDisplayValue(project.name)).toBeInTheDocument()
  })
})
