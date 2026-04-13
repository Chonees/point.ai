import { useState } from 'react'
import type { Annotation } from '../../types'
import type { EditingLabel } from './types'

interface LabelEditDialogProps {
  editingLabel: EditingLabel
  annotations: Annotation[]
  setAnnotations: (a: Annotation[]) => void
  setEditingLabel: (e: EditingLabel | null) => void
}

export function LabelEditDialog({
  editingLabel,
  annotations,
  setAnnotations,
  setEditingLabel,
}: LabelEditDialogProps) {
  const [name, setName] = useState(editingLabel.name)
  const [sqft, setSqft] = useState(editingLabel.sqft)

  const close = () => setEditingLabel(null)

  const commit = () => {
    if (!name.trim()) return
    const trimmedName = name.trim().toUpperCase()
    const newSqft = sqft ? Number(sqft) : undefined
    const current = annotations[editingLabel.idx]
    if (!current || current.type !== 'label') {
      close()
      return
    }
    const oldSqft = current.sqft

    setAnnotations(annotations.map((a, i) => {
      // Recalibrate sqft across all labels when this one changed
      if (a.type === 'label' && newSqft != null && oldSqft != null && oldSqft > 0 && newSqft !== oldSqft) {
        const ratio = newSqft / oldSqft
        if (i === editingLabel.idx) {
          return { ...a, roomName: trimmedName, sqft: newSqft }
        }
        if (a.sqft != null) {
          return { ...a, sqft: Math.round(a.sqft * ratio) }
        }
        return a
      }
      if (i === editingLabel.idx) {
        return { ...a, roomName: trimmedName, sqft: newSqft }
      }
      return a
    }))
    close()
  }

  const deleteLabel = () => {
    setAnnotations(annotations.filter((_, i) => i !== editingLabel.idx))
    close()
  }

  return (
    <div
      style={{
        position: 'absolute',
        left: editingLabel.sx,
        top: editingLabel.sy - 10,
        transform: 'translate(-50%, -100%)',
        zIndex: 50,
      }}
      className="bg-white border border-zinc-400 rounded-lg p-3 shadow-xl"
    >
      <div className="text-[10px] text-zinc-800 font-semibold mb-2">Edit Room Label</div>
      <input
        autoFocus
        type="text"
        placeholder="Room name"
        value={name}
        onChange={e => setName(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' && name.trim()) commit()
          if (e.key === 'Escape') close()
        }}
        className="w-48 px-2 py-1 text-[11px] bg-zinc-100 border border-zinc-300 rounded text-zinc-900 mb-1.5 outline-none focus:border-zinc-500"
      />
      <input
        type="number"
        placeholder="Sq ft (recalibrates others)"
        value={sqft}
        onChange={e => setSqft(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' && name.trim()) commit()
          if (e.key === 'Escape') close()
        }}
        className="w-48 px-2 py-1 text-[11px] bg-zinc-100 border border-zinc-300 rounded text-zinc-900 mb-2 outline-none focus:border-zinc-500"
      />
      <div className="flex gap-1.5">
        <button
          onClick={commit}
          className="flex-1 px-2 py-1 text-[10px] font-medium bg-zinc-800 border border-zinc-600 text-white rounded hover:bg-zinc-700 cursor-pointer"
        >
          Save
        </button>
        <button
          onClick={deleteLabel}
          className="px-2 py-1 text-[10px] font-medium text-red-600 border border-red-300 rounded hover:bg-red-50 cursor-pointer"
        >
          Delete
        </button>
        <button
          onClick={close}
          className="px-2 py-1 text-[10px] text-zinc-500 hover:text-zinc-700 cursor-pointer"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
