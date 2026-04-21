import type { ThreadSummary } from '../thread.types'

interface ThreadSidebarProps {
  projectName: string
  threads: ThreadSummary[]
  selectedThreadId: string | null
  onSelectThread: (threadId: string) => void
}

export function ThreadSidebar({ projectName, threads, selectedThreadId, onSelectThread }: ThreadSidebarProps) {
  return (
    <aside className="rounded-[28px] border border-white/6 bg-zinc-950/80 p-5">
      <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Project</p>
      <h2 className="mt-2 text-2xl font-semibold text-zinc-100">{projectName}</h2>
      <div className="mt-4 space-y-2">
        {threads.map((thread) => (
          <button
            key={thread.id}
            type="button"
            onClick={() => onSelectThread(thread.id)}
            className={`w-full rounded-2xl border px-4 py-3 text-left ${
              thread.id === selectedThreadId
                ? 'border-white/14 bg-white/[0.08]'
                : 'border-white/8 bg-white/[0.03]'
            }`}
          >
            <div className="text-sm font-medium text-zinc-100">{thread.title}</div>
            <div className="mt-1 text-xs text-zinc-500">{thread.preview}</div>
          </button>
        ))}
      </div>
    </aside>
  )
}
