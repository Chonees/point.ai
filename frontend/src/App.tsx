import { lazy, Suspense, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { useAuth } from './hooks/useAuth'
import { useProjectList } from './hooks/useProject'
import { isSupabaseConfigured } from './lib/supabase'
import { LoginPage } from './components/Auth/LoginPage'
import { ProjectList } from './components/ProjectList/ProjectList'
import type { ProjectScene } from './hooks/useProject'
import inspectorTopology from './features/catalogInspector/catalogInspector.fixture.json'
import { CatalogInspectorPage } from './features/catalogInspector/CatalogInspectorPage'
import { runChatAgentTool } from './features/chatThread/chatAgent'
import type { ThreadComposerSubmission, ThreadMessage } from './features/chatThread/thread.types'
import {
  threadToInitialMessages,
  threadToThreadSummary,
  useThreadList,
  useThreadSave,
  type ThreadData,
} from './features/threads'

const ThreadWorkspacePage = lazy(() =>
  import('./features/chatThread/ThreadWorkspacePage').then((m) => ({ default: m.ThreadWorkspacePage })),
)

type Page = 'login' | 'projects' | 'editor'

function isSeminoleTopologyInspectorRoute() {
  if (typeof window === 'undefined') return false
  return new URLSearchParams(window.location.search).get('debug') === 'seminole-topology'
}

export default function App() {
  if (isSeminoleTopologyInspectorRoute()) {
    return <CatalogInspectorPage topology={inspectorTopology} />
  }

  const auth = useAuth()
  const projectList = useProjectList(auth.user?.id)
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const threadList = useThreadList(selectedProjectId)
  const [currentThread, setCurrentThread] = useState<ThreadData | null>(null)
  const [page, setPage] = useState<Page>(isSupabaseConfigured ? 'login' : 'projects')
  const { saving, lastSaved, saveNow } = useThreadSave(currentThread?.id ?? null)
  const pendingSceneRef = useRef<ProjectScene | null>(null)
  const pendingStructureRef = useRef<Record<string, unknown> | null>(null)
  const pendingTotalSqftRef = useRef<number | null | undefined>(undefined)
  const [threadMessagesByThreadId, setThreadMessagesByThreadId] = useState<Record<string, ThreadMessage[]>>({})
  const [submittingThreadId, setSubmittingThreadId] = useState<string | null>(null)
  const activeThread = currentThread ?? (selectedProjectId ? threadList.threads[0] ?? null : null)
  const workspaceTitle = 'Chat workspace'
  const threadSummaries = useMemo(() => threadList.threads.map(threadToThreadSummary), [threadList.threads])
  const seededThreadMessages = useMemo(() => (
    activeThread ? threadToInitialMessages(activeThread) : []
  ), [activeThread])
  const threadMessages = useMemo(() => {
    if (!activeThread) return []
    return threadMessagesByThreadId[activeThread.id] ?? seededThreadMessages
  }, [activeThread, seededThreadMessages, threadMessagesByThreadId])
  const saveState = useMemo(() => {
    if (!currentThread) return 'Not saved yet'
    if (saving) return 'Saving...'
    if (lastSaved) return `Saved ${lastSaved.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
    return 'Autosave ready'
  }, [currentThread, lastSaved, saving])

  const handleSave = async () => {
    if (!currentThread) return
    const updates: Record<string, unknown> = {}
    if (pendingSceneRef.current) updates.scene = pendingSceneRef.current
    if (pendingStructureRef.current) updates.structure = pendingStructureRef.current
    if (pendingTotalSqftRef.current !== undefined) updates.totalSqft = pendingTotalSqftRef.current
    await saveNow(updates)
  }

  const appendThreadMessages = (threadId: string, messages: ThreadMessage[]) => {
    setThreadMessagesByThreadId((prev) => {
      const base = prev[threadId] ?? (threadList.threads.find((thread) => thread.id === threadId)
        ? threadToInitialMessages(threadList.threads.find((thread) => thread.id === threadId)!)
        : [])
      return {
        ...prev,
        [threadId]: [...base, ...messages],
      }
    })
  }

  const buildUserMessage = (submission: ThreadComposerSubmission): ThreadMessage => ({
    id: `user-${Math.random().toString(36).slice(2, 10)}`,
    role: 'user',
    content: submission.message || submission.attachment?.name || 'Adjunto enviado',
    createdAtIso: new Date().toISOString(),
    artifacts: submission.attachment ? [{
      id: `artifact-${Math.random().toString(36).slice(2, 10)}`,
      kind: submission.attachment.type.startsWith('image/') ? 'image-source' : 'cad-source',
      title: submission.attachment.name,
      description: 'Adjunto enviado al agente desde el chat.',
    }] : [],
  })

  const handleThreadSubmit = async (submission: ThreadComposerSubmission) => {
    if (!activeThread) return
    const threadId = activeThread.id
    appendThreadMessages(threadId, [buildUserMessage(submission)])
    setSubmittingThreadId(threadId)

    try {
      const result = await runChatAgentTool({
        prompt: submission.message,
        attachment: submission.attachment,
        planName: activeThread.name,
      })

      appendThreadMessages(threadId, [result.assistantMessage])

      if (result.planUpdates) {
        setCurrentThread((prev) => {
          if (!prev || prev.id !== threadId) return prev
          return {
            ...prev,
            ...result.planUpdates,
            updatedAt: new Date().toISOString(),
          }
        })
        await saveNow(result.planUpdates)
      }
    } catch (error) {
      appendThreadMessages(planId, [{
        id: `assistant-${Math.random().toString(36).slice(2, 10)}`,
        role: 'assistant',
        content: error instanceof Error ? error.message : 'No pude ejecutar la herramienta del chat.',
        createdAtIso: new Date().toISOString(),
        artifacts: [],
      }])
    } finally {
      setSubmittingThreadId((prev) => (prev === threadId ? null : prev))
    }
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
          plans={threadList.threads}
          plansLoading={threadList.loading}
          selectedProjectId={selectedProjectId}
          onSelectProject={setSelectedProjectId}
          onOpenPlan={(plan) => {
            setCurrentThread(plan)
            setPage('editor')
          }}
          onCreatePlan={async (name) => {
            const thread = await threadList.createThread(name)
            if (thread) {
              setCurrentThread(thread)
              setPage('editor')
            }
          }}
          onDeletePlan={threadList.deleteThread}
          onRenamePlan={threadList.renameThread}
          onSignOut={async () => {
            await auth.signOut()
            setCurrentThread(null)
            setSelectedProjectId(null)
            setPage('login')
          }}
          userEmail={auth.user?.email}
        />
      </div>
    )
  }

  // Workspace
  const projectName = projectList.projects.find((p) => p.id === activeThread?.projectId)?.name ?? 'Point.ai'
  return (
    <div className="min-h-screen bg-[#090909] text-zinc-100 safe-area-inset">
      <div className="border-b border-white/6 bg-zinc-950/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <div className="flex items-center gap-3">
            {auth.user && (
              <button
                onClick={() => {
                  setCurrentThread(null)
                  setPage('projects')
                  projectList.refresh()
                  threadList.refresh()
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
            {activeThread && (
              <div className="rounded-2xl border border-white/6 bg-white/[0.02] px-4 py-3">
                <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Current thread</p>
                <p className="mt-1 text-sm text-zinc-200">{projectName} / {activeThread.name}</p>
              </div>
            )}
            {activeThread && (
              <div className="rounded-2xl border border-white/6 bg-white/[0.02] px-4 py-3">
                <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Save status</p>
                <p className="mt-1 text-sm text-zinc-200">{saveState}</p>
              </div>
            )}
            {activeThread && auth.user && (
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
              selectedThreadId={activeThread?.id ?? null}
              messages={threadMessages}
              onSelectThread={(threadId) => {
                const nextThread = threadList.threads.find((thread) => thread.id === threadId) ?? null
                setCurrentThread(nextThread)
                if (nextThread?.projectId) setSelectedProjectId(nextThread.projectId)
              }}
              onSubmitMessage={handleThreadSubmit}
              isSubmittingMessage={submittingThreadId === activeThread?.id}
            />
          </Suspense>
        </motion.div>
      </div>
    </div>
  )
}
