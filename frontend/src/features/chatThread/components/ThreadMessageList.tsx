import type { ThreadMessage } from '../thread.types'
import { ArtifactCard } from './ArtifactCard'

interface ThreadMessageListProps {
  messages: ThreadMessage[]
}

export function ThreadMessageList({ messages }: ThreadMessageListProps) {
  return (
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
  )
}
