import { useState } from 'react'

/** State the editor passes when opening the dialog — where to place it and which dim. */
export interface EditingDimension {
  idx: number
  sx: number
  sy: number
  valueText: string
  locked: boolean
}

interface DimensionEditDialogProps {
  editing: EditingDimension
  onSave: (valueText: string, locked: boolean) => void
  onDelete: () => void
  onClose: () => void
}

/**
 * Dialog for editing a dimension annotation.
 *
 * The user can override the displayed value. If the override parses as a
 * real length (e.g. 10'-0"), the parent will treat it as a **scale
 * calibration** — the whole plan re-scales so every other cota follows.
 * If it doesn't parse (e.g. a free-form note), the parent auto-locks so
 * the dynamic recompute doesn't clobber the typed text.
 */
export function DimensionEditDialog({
  editing,
  onSave,
  onDelete,
  onClose,
}: DimensionEditDialogProps) {
  const [valueText, setValueText] = useState(editing.valueText)
  const [locked, setLocked] = useState(editing.locked)

  const commit = () => {
    onSave(valueText, locked)
  }

  return (
    <div
      style={{
        position: 'absolute',
        left: editing.sx,
        top: editing.sy - 10,
        transform: 'translate(-50%, -100%)',
        zIndex: 50,
      }}
      className="bg-white border border-zinc-400 rounded-lg p-3 shadow-xl"
    >
      <div className="text-[10px] text-zinc-800 font-semibold mb-2">Edit Dimension</div>
      <input
        autoFocus
        type="text"
        placeholder="e.g. 10'-0&quot;"
        value={valueText}
        onChange={(e) => setValueText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') commit()
          if (e.key === 'Escape') onClose()
        }}
        className="w-52 px-2 py-1 text-[11px] bg-zinc-100 border border-zinc-300 rounded text-zinc-900 mb-1.5 outline-none focus:border-zinc-500"
      />
      <div className="text-[10px] text-zinc-500 mb-2 leading-tight">
        Typing a real length (e.g. <code>10'-0"</code>) re-scales the whole plan.
      </div>
      <label className="flex items-center gap-2 text-[11px] text-zinc-700 mb-2 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={locked}
          onChange={(e) => setLocked(e.target.checked)}
        />
        Lock value (don&apos;t auto-update when walls move)
      </label>
      <div className="flex gap-1.5">
        <button
          onClick={commit}
          className="flex-1 px-2 py-1 text-[10px] font-medium bg-zinc-800 border border-zinc-600 text-white rounded hover:bg-zinc-700 cursor-pointer"
        >
          Save
        </button>
        <button
          onClick={onDelete}
          className="px-2 py-1 text-[10px] font-medium text-red-600 border border-red-300 rounded hover:bg-red-50 cursor-pointer"
        >
          Delete
        </button>
        <button
          onClick={onClose}
          className="px-2 py-1 text-[10px] text-zinc-500 hover:text-zinc-700 cursor-pointer"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
