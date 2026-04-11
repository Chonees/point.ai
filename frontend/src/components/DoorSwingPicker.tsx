import { memo } from 'react'
import type { SwingDir } from '../types'

export const DoorSwingPicker = memo(function DoorSwingPicker({ pendingDoor, onPick, onCancel, onMirror, label }: {
  pendingDoor: { x1: number; y1: number; x2: number; y2: number; sx: number; sy: number }
  onPick: (dir: SwingDir) => void
  onCancel: () => void
  onMirror?: () => void
  label?: string
}) {
  const adx = Math.abs(pendingDoor.x2 - pendingDoor.x1)
  const ady = Math.abs(pendingDoor.y2 - pendingDoor.y1)
  const isVertical = ady >= adx
  const options: SwingDir[] = isVertical ? ['left', 'right'] : ['up', 'down']
  const arrows: Record<string, string> = { up: '↑', down: '↓', left: '←', right: '→' }
  return (
    <div
      className="absolute z-50 flex items-center gap-1 px-2 py-1.5 rounded-lg bg-zinc-800 border border-zinc-700/60 shadow-xl shadow-black/50"
      style={{ left: pendingDoor.sx, top: pendingDoor.sy + 8, transform: 'translateX(-50%)' }}
    >
      <span className="text-[9px] text-zinc-400 mr-1">{label ?? 'Opens'}</span>
      {options.map((dir) => (
        <button
          key={dir}
          onClick={() => onPick(dir)}
          className="px-2.5 py-1 rounded text-[10px] font-medium bg-zinc-700/60 border border-zinc-600/50
                     text-zinc-300 hover:bg-zinc-600/60 hover:text-white cursor-pointer transition-colors"
        >
          {arrows[dir]} {dir}
        </button>
      ))}
      {onMirror && (
        <button
          onClick={onMirror}
          className="px-2 py-1 rounded text-[10px] font-medium bg-amber-900/40 border border-amber-700/50
                     text-amber-300 hover:bg-amber-800/50 hover:text-amber-200 cursor-pointer transition-colors"
          title="Flip hinge side"
        >
          ⇄
        </button>
      )}
      <button
        onClick={onCancel}
        className="ml-1 px-1.5 py-1 text-[10px] text-zinc-500 hover:text-zinc-300 cursor-pointer"
      >
        ✕
      </button>
    </div>
  )
})
