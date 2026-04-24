import { useRef, useState } from 'react'
import type { ThreadComposerSubmission } from '../thread.types'

interface ThreadComposerProps {
  onSubmitMessage: (submission: ThreadComposerSubmission) => void | Promise<void>
  isSubmitting?: boolean
}

const QUICK_ACTIONS = ['Fit Seminole 2000 on this site plan', 'Run CAD diagnostic']

function defaultMessageForAttachment(file: File | null) {
  if (!file) return ''
  if (/\.(dxf|dwg)$/i.test(file.name)) return 'Fit Seminole 2000 on this site plan'
  return ''
}

export function ThreadComposer({ onSubmitMessage, isSubmitting = false }: ThreadComposerProps) {
  const [draft, setDraft] = useState('')
  const [attachment, setAttachment] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  return (
    <form
      className="border-t border-white/6 pt-4"
      onSubmit={async (event) => {
        event.preventDefault()
        const next = draft.trim() || defaultMessageForAttachment(attachment)
        if (!next && !attachment) return
        await onSubmitMessage({
          message: next,
          attachment,
        })
        setDraft('')
        setAttachment(null)
        if (fileInputRef.current) fileInputRef.current.value = ''
      }}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".dxf,.dwg"
        aria-label="Adjuntar archivo"
        className="sr-only"
        onChange={(event) => {
          setAttachment(event.target.files?.[0] ?? null)
        }}
      />
      <textarea
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        placeholder="Subi un site plan DXF/DWG y pedime meter Seminole 2000 o correr un diagnostico..."
        className="min-h-[120px] w-full rounded-2xl border border-white/8 bg-zinc-950 px-4 py-3 text-sm text-zinc-100 outline-none"
      />
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="rounded-2xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-zinc-200"
        >
          Adjuntar site plan
        </button>
        {attachment && (
          <div className="inline-flex items-center gap-2 rounded-full border border-white/8 px-3 py-1 text-xs text-zinc-300">
            <span>{attachment.name}</span>
            <button
              type="button"
              aria-label="Quitar archivo"
              onClick={() => {
                setAttachment(null)
                if (fileInputRef.current) fileInputRef.current.value = ''
              }}
              className="text-zinc-500 hover:text-zinc-100"
            >
              ×
            </button>
          </div>
        )}
      </div>
      <div className="mt-3 flex items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2 text-xs text-zinc-500">
          {QUICK_ACTIONS.map((action) => (
            <button
              key={action}
              type="button"
              onClick={() => setDraft(action)}
              className="rounded-full border border-white/8 px-3 py-1"
            >
              {action}
            </button>
          ))}
        </div>
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-3 text-sm text-zinc-100"
        >
          {isSubmitting ? 'Procesando...' : 'Enviar'}
        </button>
      </div>
    </form>
  )
}
