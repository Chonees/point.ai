import { lazy, Suspense, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { useAuth } from './hooks/useAuth'
import { useProjectList, usePlanList, usePlanSave } from './hooks/useProject'
import { isSupabaseConfigured } from './lib/supabase'
import { LoginPage } from './components/Auth/LoginPage'
import { ProjectList } from './components/ProjectList/ProjectList'
import type { PlanData, ProjectScene } from './hooks/useProject'

const UploadPanel = lazy(() =>
  import('./components/UploadPanel').then((m) => ({ default: m.UploadPanel })),
)

type Page = 'login' | 'projects' | 'editor'

export default function App() {
  const auth = useAuth()
  const projectList = useProjectList(auth.user?.id)
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const planList = usePlanList(selectedProjectId)
  const [currentPlan, setCurrentPlan] = useState<PlanData | null>(null)
  const [page, setPage] = useState<Page>(isSupabaseConfigured ? 'login' : 'editor')
  const { saving, lastSaved, saveNow } = usePlanSave(currentPlan?.id ?? null)
  const pendingSceneRef = useRef<ProjectScene | null>(null)
  const pendingStructureRef = useRef<Record<string, unknown> | null>(null)

  const handleSave = async () => {
    if (!currentPlan) return
    const updates: Record<string, unknown> = {}
    if (pendingSceneRef.current) updates.scene = pendingSceneRef.current
    if (pendingStructureRef.current) updates.structure = pendingStructureRef.current
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
  if (page === 'login' && !auth.user) {
    return (
      <LoginPage
        onSignIn={async (e, p) => { await auth.signIn(e, p); setPage('projects') }}
        onSignUp={auth.signUp}
        onGoogleSignIn={async () => { await auth.signInWithGoogle(); setPage('projects') }}
        onSkip={() => setPage('editor')}
      />
    )
  }

  // Project + Plan list
  if (auth.user && (page === 'login' || page === 'projects')) {
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
          userEmail={auth.user.email}
        />
      </div>
    )
  }

  // Editor
  const projectName = projectList.projects.find((p) => p.id === currentPlan?.projectId)?.name
  return (
    <div className="min-h-screen flex flex-col items-center px-4 sm:px-5 py-8 sm:py-16 safe-area-inset">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="text-center mb-6 sm:mb-10"
      >
        <div className="flex items-center justify-center gap-3">
          {auth.user && (
            <button
              onClick={() => {
                setCurrentPlan(null)
                setPage('projects')
                projectList.refresh()
                planList.refresh()
              }}
              className="cursor-pointer rounded-md border border-zinc-800 px-3 py-1 text-xs text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
            >
              Projects
            </button>
          )}
          <h1 className="text-3xl sm:text-4xl font-light tracking-tight text-white/90">
            Pointe<span className="text-white/30">.ai</span>
          </h1>
          {currentPlan && auth.user && (
            <button
              onClick={handleSave}
              disabled={saving}
              className="cursor-pointer rounded-md border border-zinc-800 px-3 py-1 text-xs text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300 disabled:opacity-40"
            >
              {saving ? 'Saving...' : 'Save'}
            </button>
          )}
        </div>
        {currentPlan && (
          <p className="mt-2 text-xs text-zinc-600">
            {projectName} / {currentPlan.name}
            {lastSaved && ` · Last saved ${lastSaved.toLocaleTimeString()}`}
          </p>
        )}
        <p className="text-[10px] sm:text-xs tracking-[0.2em] uppercase text-zinc-600 mt-1.5 sm:mt-2">
          Floor Plan to DXF
        </p>
      </motion.div>

      <div className="w-full max-w-[640px]">
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
        >
          <Suspense fallback={
            <div className="flex h-40 items-center justify-center">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-700 border-t-zinc-400" />
            </div>
          }>
            <UploadPanel
              project={currentPlan}
              onSceneChange={(scene) => {
                pendingSceneRef.current = scene
              }}
              onStructureChange={(structure) => {
                pendingStructureRef.current = structure
              }}
              onSaveNow={(updates) => {
                if (updates.imageData) saveNow({ imageData: updates.imageData })
                if (updates.structure) pendingStructureRef.current = updates.structure
                if (updates.scene) pendingSceneRef.current = updates.scene
              }}
            />
          </Suspense>
        </motion.div>
      </div>
    </div>
  )
}
