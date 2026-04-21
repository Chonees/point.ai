import { render, screen } from '@testing-library/react'
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

vi.mock('./components/UploadPanel', () => ({
  UploadPanel: () => <div data-testid="legacy-upload-panel">legacy upload panel</div>,
}))

vi.mock('./features/cadWorkspace/CadWorkspacePage', () => ({
  CadWorkspacePage: () => <div data-testid="legacy-cad-page">legacy cad workspace</div>,
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
})
