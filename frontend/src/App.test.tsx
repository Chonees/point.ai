import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

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

const { runChatAgentTool, runSiteFitApplyTool } = vi.hoisted(() => ({
  runChatAgentTool: vi.fn(),
  runSiteFitApplyTool: vi.fn(),
}))

vi.mock('./features/chatThread/chatAgent', () => ({
  runChatAgentTool,
  runSiteFitApplyTool,
}))

import App from './App'

const originalUrl = window.location.href

afterEach(() => {
  window.history.replaceState({}, '', originalUrl)
})

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
        content: 'Listo, analice el site plan y ya deje el overlay listo.',
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
    expect(await screen.findByText(/analice el site plan/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open' })).toHaveAttribute('href', '/api/cad-workspace/export-overlay/cad-123')
  })

  it('lets the user apply a Bridge MVP proposal from inside the chat', async () => {
    runChatAgentTool.mockResolvedValueOnce({
      assistantMessage: {
        id: 'assistant-1',
        role: 'assistant',
        content: 'Te dejo la propuesta de site-fit.',
        createdAtIso: '2026-04-24T00:00:00.000Z',
        artifacts: [{
          id: 'proposal-1',
          kind: 'site-fit-proposal',
          title: 'SEMINOLE2000 proposal',
          proposal: {
            planId: 'seminole-2000',
            planName: 'SEMINOLE2000',
            candidateId: 'baseline_preserved',
            siteConstraints: { unit: 'inch' },
            summary: 'Keep the current plan unchanged.',
            fitStatus: 'fit_ready',
            warnings: [],
          },
        }],
      },
    })
    runSiteFitApplyTool.mockResolvedValueOnce({
      assistantMessage: {
        id: 'assistant-2',
        role: 'assistant',
        content: 'Aplique la propuesta baseline.',
        createdAtIso: '2026-04-24T00:01:00.000Z',
        artifacts: [{
          id: 'apply-1',
          kind: 'site-fit-apply',
          title: 'Applied site-fit result',
          apply: {
            planId: 'seminole-2000',
            planName: 'SEMINOLE2000',
            candidateId: 'baseline_preserved',
            applyStatus: 'applied',
            complianceStatus: 'pass',
            warnings: [],
          },
        }],
      },
    })

    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /open project pointe homes/i }))
    fireEvent.click(await screen.findByRole('button', { name: /open thread fit dawson/i }))
    fireEvent.change(screen.getByPlaceholderText(/pedile algo a point/i), {
      target: { value: 'Fit Seminole 2000 on this site plan' },
    })
    fireEvent.click(screen.getByRole('button', { name: /enviar/i }))

    fireEvent.click(await screen.findByRole('button', { name: /apply proposal/i }))

    expect(runSiteFitApplyTool).toHaveBeenCalledWith({
      planId: 'seminole-2000',
      planName: 'SEMINOLE2000',
      candidateId: 'baseline_preserved',
      siteConstraints: { unit: 'inch' },
    })
    expect(await screen.findByText(/aplique la propuesta baseline/i)).toBeInTheDocument()
    expect(screen.getByText('Applied site-fit result')).toBeInTheDocument()
  })

  it('keeps the assistant error message on the same thread when the chat tool fails', async () => {
    runChatAgentTool.mockRejectedValueOnce(new Error('Bridge failed hard'))

    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /open project pointe homes/i }))
    fireEvent.click(await screen.findByRole('button', { name: /open thread fit dawson/i }))
    fireEvent.change(screen.getByPlaceholderText(/pedile algo a point/i), {
      target: { value: 'Fit Seminole 2000 on this site plan' },
    })
    fireEvent.click(screen.getByRole('button', { name: /enviar/i }))

    expect(await screen.findByText('Bridge failed hard')).toBeInTheDocument()
  })

  it('renders the temporary seminole topology inspector when the debug query flag is present', async () => {
    window.history.replaceState({}, '', '/?debug=seminole-topology')

    render(<App />)

    expect(screen.getByTestId('app-route-loading')).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: /topology inspector/i })).toBeInTheDocument()
    expect(screen.getByText(/SEMINOLE2000/i)).toBeInTheDocument()
  })

  it('restores the URL state between tests so the main shell does not stay stuck in debug mode', async () => {
    render(<App />)

    expect(await screen.findByText(/your workspace/i)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /topology inspector/i })).not.toBeInTheDocument()
  })
})
