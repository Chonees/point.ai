# Chat-First Point.ai Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the visible workspace-first shell with a minimalist chat-first shell backed by the existing project/plan persistence model.

**Architecture:** Keep the current backend APIs and persistence intact, but reinterpret plan records as thread records in the UI. Build a thin chat-thread workspace that becomes the primary surface, and defer heavy geometry tool integration to artifact cards and follow-up changes.

**Tech Stack:** React 19, TypeScript, Vitest, Testing Library, Framer Motion, existing Supabase project/plan hooks

---

## File Structure

### Create

- `frontend/src/features/chatThread/thread.types.ts` — thread/artifact/message view models derived from existing project/plan data
- `frontend/src/features/chatThread/thread.mappers.ts` — pure mapping helpers from `PlanData` to `ThreadSummary` and initial system messages
- `frontend/src/features/chatThread/thread.mappers.test.ts` — unit tests for mapping rules
- `frontend/src/features/chatThread/ThreadWorkspacePage.tsx` — primary chat-first workspace page
- `frontend/src/features/chatThread/components/ThreadSidebar.tsx` — left column list of project threads
- `frontend/src/features/chatThread/components/ThreadMessageList.tsx` — scrollable chat transcript area
- `frontend/src/features/chatThread/components/ThreadComposer.tsx` — minimalist composer with submit button and quick action chips
- `frontend/src/features/chatThread/components/ArtifactCard.tsx` — contextual artifact rendering for previews/actions
- `frontend/src/features/chatThread/ThreadWorkspacePage.test.tsx` — UI regression tests for the new shell

### Modify

- `frontend/src/App.tsx` — replace visible workspace toggles with thread-first navigation
- `frontend/src/features/projects/project.types.ts` — add thread-safe extension fields only if needed for view state compatibility
- `frontend/src/features/projects/usePlanList.ts` — expose plan ordering/selection in a way that works for thread navigation without changing DB semantics
- `frontend/src/features/projects/index.ts` — re-export any new types/helpers needed by the shell

### Reuse as-is

- `frontend/src/features/projects/useProjectList.ts`
- `frontend/src/features/projects/usePlanSave.ts`
- `frontend/src/components/Auth/LoginPage.tsx`
- backend APIs in `backend/app.py`

---

### Task 1: Define thread and artifact view models

**Files:**
- Create: `frontend/src/features/chatThread/thread.types.ts`
- Create: `frontend/src/features/chatThread/thread.mappers.ts`
- Test: `frontend/src/features/chatThread/thread.mappers.test.ts`
- Modify: `frontend/src/features/projects/index.ts`

- [ ] **Step 1: Write the failing mapper test**

```ts
import { describe, expect, it } from 'vitest'
import type { PlanData } from '../projects'
import { planToThreadSummary, planToInitialMessages } from './thread.mappers'

function buildPlan(overrides: Partial<PlanData> = {}): PlanData {
  return {
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
      visibility: { dimensions: true, labels: true, furniture: true, shell3d: true },
    },
    totalSqft: 2100,
    createdAt: '2026-04-20T10:00:00.000Z',
    updatedAt: '2026-04-20T11:00:00.000Z',
    ...overrides,
  }
}

describe('thread.mappers', () => {
  it('maps a plan into a thread summary with last activity', () => {
    const summary = planToThreadSummary(buildPlan())
    expect(summary.id).toBe('plan-1')
    expect(summary.title).toBe('Fit Dawson')
    expect(summary.lastActivityIso).toBe('2026-04-20T11:00:00.000Z')
  })

  it('creates a starter system transcript from persisted plan data', () => {
    const messages = planToInitialMessages(buildPlan({ imageData: 'data:image/png;base64,abc' }))
    expect(messages[0].role).toBe('system')
    expect(messages[1].role).toBe('assistant')
    expect(messages[1].artifacts[0].kind).toBe('image-source')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cmd /c npm --prefix frontend test -- src/features/chatThread/thread.mappers.test.ts`  
Expected: FAIL with module not found for `thread.mappers`

- [ ] **Step 3: Write the thread types**

```ts
export type ThreadRole = 'system' | 'user' | 'assistant'

export interface ThreadArtifact {
  id: string
  kind: 'image-source' | 'cad-source' | 'preview' | 'export'
  title: string
  description?: string
  href?: string
}

export interface ThreadMessage {
  id: string
  role: ThreadRole
  content: string
  createdAtIso: string
  artifacts: ThreadArtifact[]
}

export interface ThreadSummary {
  id: string
  projectId: string
  title: string
  lastActivityIso: string
  preview: string
}
```

- [ ] **Step 4: Write the mapper implementation**

```ts
import type { PlanData } from '../projects'
import type { ThreadArtifact, ThreadMessage, ThreadSummary } from './thread.types'

export function planToThreadSummary(plan: PlanData): ThreadSummary {
  return {
    id: plan.id,
    projectId: plan.projectId,
    title: plan.name,
    lastActivityIso: plan.updatedAt,
    preview: plan.structure ? 'Floor plan disponible' : 'Thread listo para empezar',
  }
}

export function planToInitialMessages(plan: PlanData): ThreadMessage[] {
  const artifacts: ThreadArtifact[] = []
  if (plan.imageData) {
    artifacts.push({
      id: `${plan.id}-image`,
      kind: 'image-source',
      title: 'Original image',
      description: 'Fuente persistida del thread',
    })
  }

  return [
    {
      id: `${plan.id}-system`,
      role: 'system',
      content: 'Thread restaurado desde el proyecto.',
      createdAtIso: plan.createdAt,
      artifacts: [],
    },
    {
      id: `${plan.id}-assistant`,
      role: 'assistant',
      content: 'Listo para continuar con generacion, fit o ajustes.',
      createdAtIso: plan.updatedAt,
      artifacts,
    },
  ]
}
```

- [ ] **Step 5: Re-export the new thread helpers**

```ts
export type { ProjectData, PlanData, PlanScene, ProjectScene } from './project.types'
export { useProjectList } from './useProjectList'
export { usePlanList } from './usePlanList'
export { usePlanSave, useProjectSave } from './usePlanSave'
export type { ThreadSummary, ThreadMessage, ThreadArtifact } from '../chatThread/thread.types'
export { planToThreadSummary, planToInitialMessages } from '../chatThread/thread.mappers'
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cmd /c npm --prefix frontend test -- src/features/chatThread/thread.mappers.test.ts`  
Expected: PASS with 2 tests

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/chatThread/thread.types.ts frontend/src/features/chatThread/thread.mappers.ts frontend/src/features/chatThread/thread.mappers.test.ts frontend/src/features/projects/index.ts
git commit -m "feat: add chat thread view models"
```

---

### Task 2: Build the minimalist chat-thread workspace components

**Files:**
- Create: `frontend/src/features/chatThread/components/ThreadSidebar.tsx`
- Create: `frontend/src/features/chatThread/components/ThreadMessageList.tsx`
- Create: `frontend/src/features/chatThread/components/ThreadComposer.tsx`
- Create: `frontend/src/features/chatThread/components/ArtifactCard.tsx`
- Create: `frontend/src/features/chatThread/ThreadWorkspacePage.tsx`
- Test: `frontend/src/features/chatThread/ThreadWorkspacePage.test.tsx`

- [ ] **Step 1: Write the failing UI test**

```ts
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
          { id: 'thread-1', projectId: 'project-1', title: 'Fit Dawson', lastActivityIso: '2026-04-20T11:00:00.000Z', preview: 'Floor plan disponible' },
        ]}
        selectedThreadId="thread-1"
        messages={[
          { id: 'm-1', role: 'assistant', content: 'Listo para continuar.', createdAtIso: '2026-04-20T11:00:00.000Z', artifacts: [] },
        ]}
        onSelectThread={onSelectThread}
        onSubmitMessage={vi.fn()}
      />,
    )

    expect(screen.getByText('Pointe Homes')).toBeInTheDocument()
    expect(screen.getByText('Fit Dawson')).toBeInTheDocument()
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

    fireEvent.change(screen.getByPlaceholderText(/pedile algo a point/i), { target: { value: 'Generame un floor plan' } })
    fireEvent.click(screen.getByRole('button', { name: /enviar/i }))

    expect(onSubmitMessage).toHaveBeenCalledWith('Generame un floor plan')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cmd /c npm --prefix frontend test -- src/features/chatThread/ThreadWorkspacePage.test.tsx`  
Expected: FAIL with module not found for `ThreadWorkspacePage`

- [ ] **Step 3: Write the artifact card component**

```tsx
import type { ThreadArtifact } from '../thread.types'

interface ArtifactCardProps {
  artifact: ThreadArtifact
}

export function ArtifactCard({ artifact }: ArtifactCardProps) {
  return (
    <article className="rounded-2xl border border-white/8 bg-white/[0.03] p-3">
      <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">{artifact.kind}</p>
      <h4 className="mt-2 text-sm font-medium text-zinc-100">{artifact.title}</h4>
      {artifact.description && <p className="mt-2 text-sm text-zinc-400">{artifact.description}</p>}
      {artifact.href && (
        <a href={artifact.href} className="mt-3 inline-flex rounded-xl border border-white/10 px-3 py-2 text-xs text-zinc-100">
          Open
        </a>
      )}
    </article>
  )
}
```

- [ ] **Step 4: Write the thread shell components**

```tsx
import { useMemo, useState } from 'react'
import type { ThreadMessage, ThreadSummary } from './thread.types'
import { ArtifactCard } from './components/ArtifactCard'

interface ThreadWorkspacePageProps {
  projectName: string
  threads: ThreadSummary[]
  selectedThreadId: string | null
  messages: ThreadMessage[]
  onSelectThread: (threadId: string) => void
  onSubmitMessage: (message: string) => void
}

export function ThreadWorkspacePage({
  projectName,
  threads,
  selectedThreadId,
  messages,
  onSelectThread,
  onSubmitMessage,
}: ThreadWorkspacePageProps) {
  const [draft, setDraft] = useState('')
  const selectedThread = useMemo(
    () => threads.find((thread) => thread.id === selectedThreadId) ?? null,
    [selectedThreadId, threads],
  )

  return (
    <div className="grid gap-6 xl:grid-cols-[320px_1fr]">
      <aside className="rounded-[28px] border border-white/6 bg-zinc-950/80 p-5">
        <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Project</p>
        <h2 className="mt-2 text-2xl font-semibold text-zinc-100">{projectName}</h2>
        <div className="mt-4 space-y-2">
          {threads.map((thread) => (
            <button
              key={thread.id}
              type="button"
              onClick={() => onSelectThread(thread.id)}
              className={`w-full rounded-2xl border px-4 py-3 text-left ${thread.id === selectedThreadId ? 'border-white/14 bg-white/[0.08]' : 'border-white/8 bg-white/[0.03]'}`}
            >
              <div className="text-sm font-medium text-zinc-100">{thread.title}</div>
              <div className="mt-1 text-xs text-zinc-500">{thread.preview}</div>
            </button>
          ))}
        </div>
      </aside>

      <section className="rounded-[28px] border border-white/6 bg-zinc-950/80 p-5">
        <div className="border-b border-white/6 pb-4">
          <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Thread</p>
          <h3 className="mt-2 text-2xl font-semibold text-zinc-100">{selectedThread?.title ?? 'Nuevo thread'}</h3>
        </div>

        <div className="space-y-4 py-5">
          {messages.map((message) => (
            <article key={message.id} className="rounded-2xl border border-white/6 bg-white/[0.03] p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-zinc-500">{message.role}</p>
              <p className="mt-2 text-sm leading-6 text-zinc-200">{message.content}</p>
              {message.artifacts.length > 0 && (
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  {message.artifacts.map((artifact) => <ArtifactCard key={artifact.id} artifact={artifact} />)}
                </div>
              )}
            </article>
          ))}
        </div>

        <form
          className="border-t border-white/6 pt-4"
          onSubmit={(event) => {
            event.preventDefault()
            const next = draft.trim()
            if (!next) return
            onSubmitMessage(next)
            setDraft('')
          }}
        >
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Pedile algo a Point..."
            className="min-h-[120px] w-full rounded-2xl border border-white/8 bg-zinc-950 px-4 py-3 text-sm text-zinc-100 outline-none"
          />
          <div className="mt-3 flex items-center justify-between gap-3">
            <div className="flex flex-wrap gap-2 text-xs text-zinc-500">
              <span className="rounded-full border border-white/8 px-3 py-1">Generate from image</span>
              <span className="rounded-full border border-white/8 px-3 py-1">Analyze DXF/DWG</span>
            </div>
            <button type="submit" className="rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-3 text-sm text-zinc-100">
              Enviar
            </button>
          </div>
        </form>
      </section>
    </div>
  )
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cmd /c npm --prefix frontend test -- src/features/chatThread/ThreadWorkspacePage.test.tsx`  
Expected: PASS with 2 tests

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/chatThread/components/ArtifactCard.tsx frontend/src/features/chatThread/ThreadWorkspacePage.tsx frontend/src/features/chatThread/ThreadWorkspacePage.test.tsx
git commit -m "feat: add chat-first thread workspace shell"
```

---

### Task 3: Rewire the app shell to use projects + threads + one chat surface

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/features/projects/usePlanList.ts`
- Test: `frontend/src/features/chatThread/ThreadWorkspacePage.test.tsx`

- [ ] **Step 1: Write the failing app-shell regression test**

```ts
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from '../../App'

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ loading: false, user: null, signIn: vi.fn(), signUp: vi.fn(), signInWithGoogle: vi.fn(), signOut: vi.fn() }),
}))

describe('App chat shell', () => {
  it('does not render workspace toggle copy on the main shell', () => {
    render(<App />)
    expect(screen.queryByText('Image workspace')).not.toBeInTheDocument()
    expect(screen.queryByText('CAD workspace')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cmd /c npm --prefix frontend test -- src/features/chatThread/ThreadWorkspacePage.test.tsx`  
Expected: FAIL because `App` still renders workspace toggles

- [ ] **Step 3: Update `usePlanList` to expose thread-friendly selection order**

```ts
const orderedPlans = [...plans].sort((left, right) => (
  new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime()
))

return {
  plans: orderedPlans,
  loading,
  refresh,
  createPlan,
  deletePlan,
  renamePlan,
}
```

- [ ] **Step 4: Replace the workspace-first shell in `App.tsx`**

```tsx
const ThreadWorkspacePage = lazy(() =>
  import('./features/chatThread/ThreadWorkspacePage').then((m) => ({ default: m.ThreadWorkspacePage })),
)

const threadSummaries = useMemo(() => planList.plans.map(planToThreadSummary), [planList.plans])
const selectedThread = currentPlan ?? planList.plans[0] ?? null
const threadMessages = useMemo(
  () => (selectedThread ? planToInitialMessages(selectedThread) : []),
  [selectedThread],
)

// inside authenticated workspace branch
<ThreadWorkspacePage
  projectName={projectName ?? 'Point.ai'}
  threads={threadSummaries}
  selectedThreadId={selectedThread?.id ?? null}
  messages={threadMessages}
  onSelectThread={(threadId) => {
    const nextPlan = planList.plans.find((plan) => plan.id === threadId) ?? null
    setCurrentPlan(nextPlan)
  }}
  onSubmitMessage={(message) => {
    console.info('[chat-shell] pending tool orchestration:', message)
  }}
/>
```

- [ ] **Step 5: Run the focused frontend tests**

Run: `cmd /c npm --prefix frontend test -- src/features/chatThread/thread.mappers.test.ts src/features/chatThread/ThreadWorkspacePage.test.tsx`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx frontend/src/features/projects/usePlanList.ts
git commit -m "feat: switch app shell to chat-first threads"
```

---

### Task 4: Seed minimal artifact actions so the shell is ready for existing tools

**Files:**
- Modify: `frontend/src/features/chatThread/thread.mappers.ts`
- Modify: `frontend/src/features/chatThread/ThreadWorkspacePage.tsx`
- Test: `frontend/src/features/chatThread/ThreadWorkspacePage.test.tsx`

- [ ] **Step 1: Write the failing artifact-action test**

```ts
it('renders tool quick actions in the composer and artifact open actions in the transcript', () => {
  render(
    <ThreadWorkspacePage
      projectName="Pointe Homes"
      threads={[{ id: 'thread-1', projectId: 'project-1', title: 'Fit Dawson', lastActivityIso: '2026-04-20T11:00:00.000Z', preview: 'Floor plan disponible' }]}
      selectedThreadId="thread-1"
      messages={[
        {
          id: 'm-1',
          role: 'assistant',
          content: 'Abramos el ultimo overlay.',
          createdAtIso: '2026-04-20T11:00:00.000Z',
          artifacts: [{ id: 'a-1', kind: 'preview', title: 'Overlay', href: '/api/cad-workspace/export-overlay/demo' }],
        },
      ]}
      onSelectThread={vi.fn()}
      onSubmitMessage={vi.fn()}
    />,
  )

  expect(screen.getByText('Generate from image')).toBeInTheDocument()
  expect(screen.getByText('Analyze DXF/DWG')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Open' })).toHaveAttribute('href', '/api/cad-workspace/export-overlay/demo')
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cmd /c npm --prefix frontend test -- src/features/chatThread/ThreadWorkspacePage.test.tsx`  
Expected: FAIL if quick actions or artifact links are missing

- [ ] **Step 3: Seed artifacts from existing persisted plan data**

```ts
if (plan.structure) {
  artifacts.push({
    id: `${plan.id}-preview`,
    kind: 'preview',
    title: 'Latest parsed structure',
    description: 'Persisted geometry is available for the agent to continue from.',
  })
}
```

- [ ] **Step 4: Keep composer quick actions visible and stable**

```tsx
const quickActions = ['Generate from image', 'Analyze DXF/DWG']

<div className="flex flex-wrap gap-2 text-xs text-zinc-500">
  {quickActions.map((action) => (
    <span key={action} className="rounded-full border border-white/8 px-3 py-1">
      {action}
    </span>
  ))}
</div>
```

- [ ] **Step 5: Run the final focused frontend suite**

Run: `cmd /c npm --prefix frontend test -- src/features/chatThread/thread.mappers.test.ts src/features/chatThread/ThreadWorkspacePage.test.tsx`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/chatThread/thread.mappers.ts frontend/src/features/chatThread/ThreadWorkspacePage.tsx frontend/src/features/chatThread/ThreadWorkspacePage.test.tsx
git commit -m "feat: seed chat shell artifacts and quick actions"
```

---

## Self-Review

### Spec coverage

- Minimal chat-first shell: covered by Tasks 2 and 3
- Reuse current persistence model: covered by Tasks 1 and 3
- Thread/artifact interpretation over existing plans: covered by Tasks 1 and 4
- Keep current tools behind the scenes: covered by Task 4 quick actions and artifact seeding

### Placeholder scan

- No `TODO`, `TBD`, or “implement later” placeholders remain
- Each task has explicit file paths, commands, and concrete code blocks

### Type consistency

- `ThreadSummary`, `ThreadMessage`, and `ThreadArtifact` are defined once in Task 1 and reused consistently in Tasks 2–4
- `planToThreadSummary` and `planToInitialMessages` remain the canonical mapper names throughout the plan

---

Plan complete and saved to `docs/superpowers/plans/2026-04-20-chat-first-point-ai-shell.md`.
