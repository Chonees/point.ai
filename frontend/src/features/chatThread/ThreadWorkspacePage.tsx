import { useMemo } from 'react'
import type { ThreadComposerSubmission, ThreadMessage, ThreadSummary } from './thread.types'
import { ThreadComposer } from './components/ThreadComposer'
import { ThreadMessageList } from './components/ThreadMessageList'
import { ThreadSidebar } from './components/ThreadSidebar'

interface ThreadWorkspacePageProps {
  projectName: string
  threads: ThreadSummary[]
  selectedThreadId: string | null
  messages: ThreadMessage[]
  onSelectThread: (threadId: string) => void
  onSubmitMessage: (submission: ThreadComposerSubmission) => void | Promise<void>
  isSubmittingMessage?: boolean
}

export function ThreadWorkspacePage({
  projectName,
  threads,
  selectedThreadId,
  messages,
  onSelectThread,
  onSubmitMessage,
  isSubmittingMessage = false,
}: ThreadWorkspacePageProps) {
  const selectedThread = useMemo(
    () => threads.find((thread) => thread.id === selectedThreadId) ?? null,
    [selectedThreadId, threads],
  )

  return (
    <div className="grid gap-6 xl:grid-cols-[320px_1fr]">
      <ThreadSidebar
        projectName={projectName}
        threads={threads}
        selectedThreadId={selectedThreadId}
        onSelectThread={onSelectThread}
      />

      <section className="rounded-[28px] border border-white/6 bg-zinc-950/80 p-5">
        <div className="border-b border-white/6 pb-4">
          <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Thread</p>
          <h3 className="mt-2 text-2xl font-semibold text-zinc-100">{selectedThread?.title ?? 'Nuevo thread'}</h3>
        </div>

        <ThreadMessageList messages={messages} />
        <ThreadComposer onSubmitMessage={onSubmitMessage} isSubmitting={isSubmittingMessage} />
      </section>
    </div>
  )
}
