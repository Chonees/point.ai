import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('./hooks/useAuth', () => ({
  useAuth: () => ({
    loading: false,
    user: null,
    signIn: vi.fn(),
    signUp: vi.fn(),
    signInWithGoogle: vi.fn(),
    signOut: vi.fn(),
  }),
}))

vi.mock('./hooks/useProject', () => ({
  useProjectList: () => ({
    projects: [{ id: 'project-1', name: 'Pointe Homes', createdAt: '2026-04-20T10:00:00.000Z', updatedAt: '2026-04-20T11:00:00.000Z', planCount: 1 }],
    loading: false,
    refresh: vi.fn(),
    createProject: vi.fn(),
    deleteProject: vi.fn(),
    renameProject: vi.fn(),
  }),
  usePlanList: () => ({
    plans: [{
      id: 'plan-1',
      projectId: 'project-1',
      name: 'Fit Dawson',
      imageData: null,
      structure: { rooms: [] },
      scene: {
        annotations2d: [],
        placedItems3d: [],
        floorMaterial: 'hardwood',
        wallMaterial: 'white-paint',
        visibility: { bg: true, regions: true, walls: true, doors: true, windows: true, labels: true, separators: true, dimensions: true },
      },
      totalSqft: null,
      createdAt: '2026-04-20T10:00:00.000Z',
      updatedAt: '2026-04-20T11:00:00.000Z',
    }],
    loading: false,
    refresh: vi.fn(),
    createPlan: vi.fn(),
    deletePlan: vi.fn(),
    renamePlan: vi.fn(),
  }),
  usePlanSave: () => ({
    saving: false,
    lastSaved: null,
    saveNow: vi.fn(),
    debouncedSave: vi.fn(),
  }),
}))

vi.mock('./lib/supabase', () => ({
  isSupabaseConfigured: false,
}))

const { runChatAgentTool } = vi.hoisted(() => ({
  runChatAgentTool: vi.fn(),
}))

vi.mock('./features/chatThread/chatAgent', () => ({
  runChatAgentTool,
}))

import App from './App'

describe('App chat shell', () => {
  it('lands on the project shell instead of an empty black thread workspace when no thread is active', async () => {
    render(<App />)

    expect(screen.queryByText('Image workspace')).not.toBeInTheDocument()
    expect(screen.queryByText('CAD workspace')).not.toBeInTheDocument()
    expect(await screen.findByText(/your workspace/i)).toBeInTheDocument()
    expect(screen.queryByPlaceholderText(/pedile algo a point/i)).not.toBeInTheDocument()
  })

  it('can transition from projects to an open thread without hook-order crashes', async () => {
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /open project pointe homes/i }))
    fireEvent.click(await screen.findByRole('button', { name: /open thread fit dawson/i }))

    expect(await screen.findByPlaceholderText(/pedile algo a point/i)).toBeInTheDocument()
  })

  it('routes a chat prompt through the agent tool and appends the assistant response', async () => {
    runChatAgentTool.mockResolvedValueOnce({
      assistantMessage: {
        id: 'assistant-1',
        role: 'assistant',
        content: 'Listo, analicé el site plan y ya dejé el overlay listo.',
        createdAtIso: '2026-04-21T00:00:00.000Z',
        artifacts: [
          {
            id: 'artifact-1',
            kind: 'export',
            title: 'Download CAD overlay DXF',
            href: '/api/cad-workspace/export-overlay/cad-123',
          },
        ],
      },
    })

    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /open project pointe homes/i }))
    fireEvent.click(await screen.findByRole('button', { name: /open thread fit dawson/i }))
    fireEvent.change(screen.getByPlaceholderText(/pedile algo a point/i), {
      target: { value: 'Analyze DXF/DWG' },
    })
    fireEvent.click(screen.getByRole('button', { name: /enviar/i }))

    expect((await screen.findAllByText('Analyze DXF/DWG')).length).toBeGreaterThan(0)
    expect(await screen.findByText(/analicé el site plan/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open' })).toHaveAttribute('href', '/api/cad-workspace/export-overlay/cad-123')
  })

  it('renders the temporary seminole topology inspector when the debug query flag is present', async () => {
    window.history.replaceState({}, '', '/?debug=seminole-topology')

    render(<App />)

    expect(await screen.findByRole('heading', { name: /topology inspector/i })).toBeInTheDocument()
    expect(screen.getByText(/SEMINOLE2000/i)).toBeInTheDocument()
  })
})
