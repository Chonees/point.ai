import { useState } from 'react'
import type { PlanData } from '../project.types'

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

interface PlanCardProps {
  plan: PlanData
  onOpen: () => void
  onDelete: () => void
  onRename: (name: string) => void
}

export function PlanCard({ plan, onOpen, onDelete, onRename }: PlanCardProps) {
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState('')

  const handleRename = () => {
    if (editName.trim()) onRename(editName.trim())
    setEditing(false)
  }

  return (
    <div className="group overflow-hidden rounded-[24px] border border-white/6 bg-white/[0.02] transition-all hover:border-white/12 hover:bg-white/[0.04]">
      <button type="button" onClick={onOpen} className="block w-full text-left">
        <div className="relative h-40 border-b border-white/6 bg-zinc-950">
          {plan.imageData ? (
            <img src={plan.imageData} alt={plan.name} className="h-full w-full object-cover opacity-90" />
          ) : (
            <div className="flex h-full items-center justify-center">
              <div className="space-y-2 text-center">
                <div className="mx-auto h-12 w-12 rounded-2xl border border-white/8 bg-white/[0.04]" />
                <p className="text-xs uppercase tracking-[0.24em] text-zinc-600">No preview</p>
              </div>
            </div>
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/15 to-transparent" />
          <div className="absolute bottom-4 left-4 right-4 flex items-end justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate text-lg font-medium text-zinc-100">{plan.name}</p>
              <p className="mt-1 text-xs text-zinc-300/75">
                {plan.scene.annotations2d.length} annotations · {plan.scene.placedItems3d.length} 3D items
              </p>
            </div>
            <span className="rounded-full border border-white/10 bg-black/35 px-2.5 py-1 text-[10px] uppercase tracking-[0.2em] text-zinc-300">
              Open
            </span>
          </div>
        </div>
      </button>

      <div className="flex items-center justify-between gap-3 px-4 py-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Last saved</p>
          <p className="mt-1 text-sm text-zinc-300">{formatDate(plan.updatedAt)} at {formatTime(plan.updatedAt)}</p>
        </div>
        <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          <button
            type="button"
            onClick={() => { setEditing(true); setEditName(plan.name) }}
            className="rounded-xl border border-white/8 px-2.5 py-1.5 text-[11px] text-zinc-400 hover:border-white/14 hover:text-zinc-200"
          >
            Rename
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="rounded-xl border border-white/8 px-2.5 py-1.5 text-[11px] text-zinc-500 hover:border-red-500/20 hover:bg-red-500/8 hover:text-red-300"
          >
            Delete
          </button>
        </div>
      </div>

      {editing && (
        <div className="border-t border-white/6 px-4 py-3">
          <input
            autoFocus
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            onBlur={handleRename}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleRename()
              if (e.key === 'Escape') setEditing(false)
            }}
            className="w-full rounded-2xl border border-white/10 bg-zinc-950 px-4 py-3 text-sm text-zinc-100 outline-none"
          />
        </div>
      )}
    </div>
  )
}
