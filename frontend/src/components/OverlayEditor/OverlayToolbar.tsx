import type { AnnotationType, Annotation } from '../../types'
import { ROOM_PALETTE } from './constants'
import type { ToolGroup } from './types'

const toolGroups: ToolGroup[] = [
  {
    title: 'Structure',
    items: [
      { type: 'wall', label: 'Wall', hint: 'Boundaries' },
      { type: 'door', label: 'Door', hint: 'Openings' },
      { type: 'window', label: 'Window', hint: 'Openings' },
    ],
  },
  {
    title: 'Semantics',
    items: [
      { type: 'label', label: 'Label', hint: 'Names' },
      { type: 'paint', label: 'Region', hint: 'Rooms' },
    ],
  },
  {
    title: 'Edit',
    items: [
      { type: 'select', label: 'Select', hint: 'Move/Resize' },
      { type: 'eraser', label: 'Eraser', hint: 'Cleanup' },
    ],
  },
]

interface OverlayToolbarProps {
  tool: AnnotationType
  setTool: (t: AnnotationType) => void
  fullscreen: boolean
  setFullscreen: (f: boolean) => void
  eraserSize: number
  setEraserSize: (n: number) => void
  paintBrushSize: number
  setPaintBrushSize: (n: number) => void
  paintMode: 'brush' | 'separator'
  setPaintMode: (m: 'brush' | 'separator') => void
  selectedRoomIdx: number
  annotations: Annotation[]
  view: { scale: number }
  fitImage: () => void
  undo: () => void
  onClearLabels: () => void
}

export function OverlayToolbar({
  tool, setTool, fullscreen, setFullscreen,
  eraserSize, setEraserSize,
  paintBrushSize, setPaintBrushSize,
  paintMode, setPaintMode,
  selectedRoomIdx, annotations,
  view, fitImage, undo, onClearLabels,
}: OverlayToolbarProps) {
  const zoomLabel = `${Math.round(view.scale * 100)}%`
  const labelCount = annotations.filter(a => a.type === 'label').length

  return (
    <div className="flex items-center gap-2 px-3 py-2.5 bg-zinc-900/90 border-b border-zinc-800/40">
      {fullscreen ? (
        <>
          {toolGroups.map((group) => (
            <div key={group.title} className="flex items-center gap-1.5">
              <span className="hidden xl:block text-[10px] uppercase tracking-[0.22em] text-zinc-600">{group.title}</span>
              <div className="flex items-center gap-1 rounded-2xl border border-white/6 bg-white/[0.02] p-1">
                {group.items.map((item) => (
                  <button
                    key={item.type}
                    onClick={() => setTool(item.type)}
                    title={`${item.label} ? ${item.hint}`}
                    className={`rounded-xl border px-3 py-2 text-[11px] font-medium transition-all cursor-pointer ${
                      tool === item.type
                        ? 'border-white/14 bg-white/[0.08] text-zinc-100 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]'
                        : 'border-transparent bg-transparent text-zinc-500 hover:border-white/8 hover:text-zinc-300'
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
          {tool === 'label' && labelCount > 0 && (
            <button
              onClick={onClearLabels}
              className="px-3 py-2 ml-1 rounded-xl text-[11px] font-medium text-zinc-300 bg-white/[0.04] border border-white/8 hover:border-red-500/20 hover:bg-red-500/8 hover:text-red-300 cursor-pointer transition-colors"
            >
              Clear Labels ({labelCount})
            </button>
          )}
          {tool === 'eraser' && (
            <div className="flex items-center gap-2 ml-1 rounded-2xl border border-white/6 bg-white/[0.02] px-3 py-2">
              <span className="text-[10px] uppercase tracking-[0.18em] text-zinc-600">Size</span>
              <input
                type="range" min="3" max="30" value={eraserSize}
                onChange={(e) => setEraserSize(Number(e.target.value))}
                className="w-14 h-1 accent-zinc-500"
              />
              <span className="text-[10px] text-zinc-400 w-4">{eraserSize}</span>
            </div>
          )}
          {tool === 'paint' && (
            <div className="flex items-center gap-2 ml-1 rounded-2xl border border-white/6 bg-white/[0.02] px-3 py-2">
              <div className="flex items-center gap-0 rounded-xl border border-white/8 bg-zinc-950/80 p-0.5">
                <button
                  onClick={() => setPaintMode('brush')}
                  className={`px-2 py-1.5 rounded-lg text-[10px] font-medium cursor-pointer transition-colors ${
                    paintMode === 'brush' ? 'bg-white/[0.08] text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
                  }`}
                >Brush</button>
                <button
                  onClick={() => setPaintMode('separator')}
                  className={`px-2 py-1.5 rounded-lg text-[10px] font-medium cursor-pointer transition-colors ${
                    paintMode === 'separator' ? 'bg-white/[0.08] text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
                  }`}
                >Separator</button>
              </div>
              {paintMode === 'brush' && selectedRoomIdx >= 0 ? (
                <>
                  <div
                    className="w-3 h-3 rounded-full border border-white/30"
                    style={{ backgroundColor: `rgb(${ROOM_PALETTE[selectedRoomIdx % ROOM_PALETTE.length].join(',')})` }}
                  />
                  <span className="text-[10px] text-zinc-400">
                    {annotations.filter(a => a.type === 'label')[selectedRoomIdx]?.roomName ?? 'Room'}
                  </span>
                </>
              ) : paintMode === 'brush' ? (
                <span className="text-[10px] text-zinc-500">Select a room label</span>
              ) : (
                <span className="text-[10px] text-zinc-500">Click, drag, release</span>
              )}
              {paintMode === 'brush' && (
                <>
                  <span className="text-[10px] text-zinc-600 ml-1">Size</span>
                  <input
                    type="range" min="3" max="50" value={paintBrushSize}
                    onChange={(e) => setPaintBrushSize(Number(e.target.value))}
                    className="w-14 h-1 accent-zinc-400"
                  />
                  <span className="text-[10px] text-zinc-400 w-4">{paintBrushSize}</span>
                  <span className="text-[10px] text-zinc-600 ml-1">RMB erases</span>
                </>
              )}
            </div>
          )}
          <div className="flex items-center gap-1 ml-2">
            <button
              onClick={fitImage}
              className="px-3 py-2 rounded-xl text-[11px] text-zinc-400 hover:text-zinc-200 bg-white/[0.02] border border-white/6 cursor-pointer transition-colors"
            >
              Fit
            </button>
            <span className="text-[10px] text-zinc-500 w-10 text-center">{zoomLabel}</span>
          </div>
          <div className="flex-1" />
          <button
            onClick={undo}
            disabled={annotations.length === 0}
            className="px-3 py-2 rounded-xl text-[11px] text-zinc-500 hover:text-zinc-300 disabled:opacity-30 cursor-pointer transition-colors"
          >
            Undo
          </button>
          <button
            onClick={() => setFullscreen(false)}
            className="px-3 py-2 rounded-xl text-[11px] text-zinc-300 hover:text-zinc-100 bg-white/[0.04] border border-white/8 cursor-pointer transition-colors"
          >
            Done
          </button>
        </>
      ) : (
        <>
          <div className="rounded-2xl border border-white/6 bg-white/[0.02] px-3 py-2 text-[10px] uppercase tracking-[0.22em] text-zinc-600">
            2D editor
          </div>
          <div className="flex-1" />
          <button
            onClick={() => setFullscreen(true)}
            className="px-3 py-2 rounded-xl text-[11px] font-medium text-zinc-300 bg-white/[0.04] border border-white/8 hover:bg-white/[0.08] hover:text-zinc-100 cursor-pointer transition-colors"
          >
            Edit
          </button>
        </>
      )}
      <span className="text-[10px] text-zinc-700">
        {annotations.length} drawn
      </span>
    </div>
  )
}
