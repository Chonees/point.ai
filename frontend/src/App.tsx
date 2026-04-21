import { lazy, Suspense, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { useAuth } from './hooks/useAuth'
import { useProjectList, usePlanList, usePlanSave } from './hooks/useProject'
import { isSupabaseConfigured } from './lib/supabase'
import { LoginPage } from './components/Auth/LoginPage'
import { ProjectList } from './components/ProjectList/ProjectList'
import type { PlanData, ProjectScene } from './hooks/useProject'
import { planToInitialMessages, planToThreadSummary } from './features/projects'

const ThreadWorkspacePage = lazy(() =>
  import('./features/chatThread/ThreadWorkspacePage').then((m) => ({ default: m.ThreadWorkspacePage })),
)

type Page = 'login' | 'projects' | 'editor'

export default function App() {
  const auth = useAuth()
  const projectList = useProjectList(auth.user?.id)
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const planList = usePlanList(selectedProjectId)
  const [currentPlan, setCurrentPlan] = useState<PlanData | null>(null)
  const [page, setPage] = useState<Page>(isSupabaseConfigured ? 'login' : 'projects')
  const { saving, lastSaved, saveNow, debouncedSave } = usePlanSave(currentPlan?.id ?? null)
  const pendingSceneRef = useRef<ProjectScene | null>(null)
  const pendingStructureRef = useRef<Record<string, unknown> | null>(null)
  const pendingTotalSqftRef = useRef<number | null | undefined>(undefined)
  const activePlan = currentPlan ?? (selectedProjectId ? planList.plans[0] ?? null : null)
  const workspaceTitle = 'Chat workspace'
  const threadSummaries = useMemo(() => planList.plans.map(planToThreadSummary), [planList.plans])
  const threadMessages = useMemo(() => (
    activePlan ? planToInitialMessages(activePlan) : []
  ), [activePlan])
  const saveState = useMemo(() => {
    if (!currentPlan) return 'Not saved yet'
    if (saving) return 'Saving...'
    if (lastSaved) return `Saved ${lastSaved.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
    return 'Autosave ready'
  }, [currentPlan, lastSaved, saving])

  const handleSave = async () => {
    if (!currentPlan) return
    const updates: Record<string, unknown> = {}
    if (pendingSceneRef.current) updates.scene = pendingSceneRef.current
    if (pendingStructureRef.current) updates.structure = pendingStructureRef.current
    if (pendingTotalSqftRef.current !== undefined) updates.totalSqft = pendingTotalSqftRef.current
    await saveNow(updates)
  }

  // Loading
  if (auth.loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-700 border-t-zinc-400" />
      </div>
    )
  }

  // Login
  if (page === 'login' && !auth.user && isSupabaseConfigured) {
    return (
      <LoginPage
        onSignIn={async (e, p) => { await auth.signIn(e, p); setPage('projects') }}
        onSignUp={auth.signUp}
        onGoogleSignIn={async () => { await auth.signInWithGoogle(); setPage('projects') }}
        onSkip={() => setPage('projects')}
      />
    )
  }

  // Project + Plan list
  if ((auth.user || !isSupabaseConfigured) && (page === 'login' || page === 'projects')) {
    return (
      <div className="min-h-screen bg-zinc-950">
        <ProjectList
          projects={projectList.projects}
          loading={projectList.loading}
          onCreateProject={async (name) => {
            const p = await projectList.createProject(name)
            if (p) setSelectedProjectId(p.id)
          }}
          onDeleteProject={async (id) => {
            await projectList.deleteProject(id)
            if (selectedProjectId === id) setSelectedProjectId(null)
          }}
          onRenameProject={projectList.renameProject}
          plans={planList.plans}
          plansLoading={planList.loading}
          selectedProjectId={selectedProjectId}
          onSelectProject={setSelectedProjectId}
          onOpenPlan={(plan) => {
            setCurrentPlan(plan)
            setPage('editor')
          }}
          onCreatePlan={async (name) => {
            const plan = await planList.createPlan(name)
            if (plan) {
              setCurrentPlan(plan)
              setPage('editor')
            }
          }}
          onDeletePlan={planList.deletePlan}
          onRenamePlan={planList.renamePlan}
          onSignOut={async () => {
            await auth.signOut()
            setCurrentPlan(null)
            setSelectedProjectId(null)
            setPage('login')
          }}
          userEmail={auth.user?.email}
        />
      </div>
    )
  }

  // Workspace
  const projectName = projectList.projects.find((p) => p.id === activePlan?.projectId)?.name ?? 'Point.ai'
  return (
    <div className="min-h-screen bg-[#090909] text-zinc-100 safe-area-inset">
      <div className="border-b border-white/6 bg-zinc-950/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <div className="flex items-center gap-3">
            {auth.user && (
              <button
                onClick={() => {
                  setCurrentPlan(null)
                  setPage('projects')
                  projectList.refresh()
                  planList.refresh()
                }}
                className="rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-2 text-sm text-zinc-300 transition-colors hover:border-white/14 hover:bg-white/[0.05]"
              >
                Projects
              </button>
            )}
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.04] text-sm font-semibold text-zinc-100">
              P
            </div>
            <div>
              <h1 className="text-xl font-semibold tracking-tight text-zinc-100">
                Pointe<span className="text-white/30">.ai</span>
              </h1>
              <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">{workspaceTitle}</p>
            </div>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            {activePlan && (
              <div className="rounded-2xl border border-white/6 bg-white/[0.02] px-4 py-3">
                <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Current thread</p>
                <p className="mt-1 text-sm text-zinc-200">{projectName} / {activePlan.name}</p>
              </div>
            )}
            {activePlan && (
              <div className="rounded-2xl border border-white/6 bg-white/[0.02] px-4 py-3">
                <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Save status</p>
                <p className="mt-1 text-sm text-zinc-200">{saveState}</p>
              </div>
            )}
            {activePlan && auth.user && (
              <button
                onClick={handleSave}
                disabled={saving}
                className="rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-3 text-sm text-zinc-200 transition-colors hover:bg-white/[0.1] disabled:opacity-40"
              >
                Save now
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
        >
          <Suspense
            fallback={
              <div className="flex h-40 items-center justify-center rounded-[28px] border border-white/6 bg-zinc-950/80">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-700 border-t-zinc-400" />
              </div>
            }
          >
            <ThreadWorkspacePage
              projectName={projectName}
              threads={threadSummaries}
              selectedThreadId={activePlan?.id ?? null}
              messages={threadMessages}
              onSelectThread={(threadId) => {
                const nextPlan = planList.plans.find((plan) => plan.id === threadId) ?? null
                setCurrentPlan(nextPlan)
                if (nextPlan?.projectId) setSelectedProjectId(nextPlan.projectId)
              }}
              onSubmitMessage={(message) => {
                console.info('[chat-shell] pending tool orchestration:', message)
              }}
            />
          </Suspense>
        </motion.div>
      </div>
    </div>
  )
}
