import type { Annotation } from '../../types'
import type { PendingLabel } from './types'
import { newAnnotationId } from '../../utils/annotationId'

interface RoomLabelDialogProps {
  pendingLabel: PendingLabel
  labelName: string
  setLabelName: (s: string) => void
  labelSqft: string
  setLabelSqft: (s: string) => void
  annotations: Annotation[]
  setAnnotations: (a: Annotation[]) => void
  setPendingLabel: (l: PendingLabel | null) => void
}

export function RoomLabelDialog({
  pendingLabel,
  labelName, setLabelName,
  labelSqft, setLabelSqft,
  annotations, setAnnotations,
  setPendingLabel,
}: RoomLabelDialogProps) {
  const commitLabel = () => {
    if (!labelName.trim()) return
    const ann: Annotation = {
      id: newAnnotationId(),
      type: 'label',
      x1: pendingLabel.x, y1: pendingLabel.y,
      x2: pendingLabel.x, y2: pendingLabel.y,
      roomName: labelName.trim().toUpperCase(),
      sqft: labelSqft ? Number(labelSqft) : undefined,
    }
    setAnnotations([...annotations, ann])
    setPendingLabel(null)
  }

  return (
    <div
      style={{
        position: 'absolute',
        left: pendingLabel.sx,
        top: pendingLabel.sy - 10,
        transform: 'translate(-50%, -100%)',
        zIndex: 50,
      }}
      className="bg-white border border-zinc-400 rounded-lg p-3 shadow-xl"
    >
      <div className="text-[10px] text-zinc-800 font-semibold mb-2">Room Label</div>
      <input
        autoFocus
        type="text"
        placeholder="Room name (e.g. LIVING ROOM)"
        value={labelName}
        onChange={e => setLabelName(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' && labelName.trim()) commitLabel()
          if (e.key === 'Escape') setPendingLabel(null)
        }}
        className="w-48 px-2 py-1 text-[11px] bg-zinc-100 border border-zinc-300 rounded text-zinc-900 mb-1.5 outline-none focus:border-zinc-500"
      />
      <input
        type="number"
        placeholder="Sq ft (e.g. 350) — optional"
        value={labelSqft}
        onChange={e => setLabelSqft(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' && labelName.trim()) commitLabel()
          if (e.key === 'Escape') setPendingLabel(null)
        }}
        className="w-48 px-2 py-1 text-[11px] bg-zinc-100 border border-zinc-300 rounded text-zinc-900 mb-2 outline-none focus:border-zinc-500"
      />
      <div className="flex gap-1.5">
        <button
          onClick={commitLabel}
          className="flex-1 px-2 py-1 text-[10px] font-medium bg-zinc-800 border border-zinc-600 text-white rounded hover:bg-zinc-700 cursor-pointer"
        >
          Add
        </button>
        <button
          onClick={() => setPendingLabel(null)}
          className="px-2 py-1 text-[10px] text-zinc-500 hover:text-zinc-300 cursor-pointer"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
