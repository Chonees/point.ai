import { useState } from 'react'

interface ThreadComposerProps {
  onSubmitMessage: (message: string) => void
}

const QUICK_ACTIONS = ['Generate from image', 'Analyze DXF/DWG']

export function ThreadComposer({ onSubmitMessage }: ThreadComposerProps) {
  const [draft, setDraft] = useState('')

  return (
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
          {QUICK_ACTIONS.map((action) => (
            <span key={action} className="rounded-full border border-white/8 px-3 py-1">
              {action}
            </span>
          ))}
        </div>
        <button
          type="submit"
          className="rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-3 text-sm text-zinc-100"
        >
          Enviar
        </button>
      </div>
    </form>
  )
}
