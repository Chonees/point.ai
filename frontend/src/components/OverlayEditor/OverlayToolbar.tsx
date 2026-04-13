import { useState, useRef, useEffect } from 'react'
import type { AnnotationType, Annotation } from '../../types'
import { ROOM_PALETTE } from './constants'
import type { ToolGroup, Visibility } from './types'

const TOOL_ICONS: Record<string, string> = {
  wall: '▬',
  door: '🚪',
  window: '⊞',
  label: 'Aa',
  paint: '◉',
  select: '⇱',
}

const toolGroups: ToolGroup[] = [
  {
    title: 'Draw',
    items: [
      { type: 'wall', label: 'Wall', hint: 'Boundaries' },
      { type: 'door', label: 'Door', hint: 'Openings' },
      { type: 'window', label: 'Window', hint: 'Openings' },
    ],
  },
  {
    title: 'Annotate',
    items: [
      { type: 'label', label: 'Label', hint: 'Names' },
      { type: 'paint', label: 'Region', hint: 'Rooms' },
    ],
  },
  {
    title: '',
    items: [
      { type: 'select', label: 'Select', hint: 'Edit/Delete' },
    ],
  },
]

interface OverlayToolbarProps {
  tool: AnnotationType
  setTool: (t: AnnotationType) => void
  fullscreen: boolean
  setFullscreen: (f: boolean) => void
  paintBrushSize: number
  setPaintBrushSize: (n: number) => void
  paintMode: 'brush' | 'separator'
  setPaintMode: (m: 'brush' | 'separator') => void
  selectedRoomIdx: number
  annotations: Annotation[]
  visibility: Visibility
  setVisibility: (v: Visibility) => void
  fitImage: () => void
  undo: () => void
  onClearLabels: () => void
}

export function OverlayToolbar({
  tool, setTool, fullscreen, setFullscreen,
  paintBrushSize, setPaintBrushSize,
  paintMode, setPaintMode,
  selectedRoomIdx, annotations,
  visibility, setVisibility,
  fitImage, undo, onClearLabels,
}: OverlayToolbarProps) {
  const [hidePanelOpen, setHidePanelOpen] = useState(false)
  const hidePanelRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!hidePanelOpen) return
    const onDown = (e: MouseEvent) => {
      if (hidePanelRef.current && !hidePanelRef.current.contains(e.target as Node)) {
        setHidePanelOpen(false)
      }
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [hidePanelOpen])

  const anyHidden = Object.values(visibility).some(v => !v)
  const toggleLayer = (key: keyof Visibility) => setVisibility({ ...visibility, [key]: !visibility[key] })
  const HIDE_LAYERS: { key: keyof Visibility; label: string }[] = [
    { key: 'bg', label: 'Background image' },
    { key: 'regions', label: 'Room colors' },
    { key: 'walls', label: 'Walls' },
    { key: 'doors', label: 'Doors' },
    { key: 'windows', label: 'Windows' },
    { key: 'labels', label: 'Room labels' },
    { key: 'separators', label: 'Separators' },
  ]
  const labelCount = annotations.filter(a => a.type === 'label').length

  const allTools = toolGroups.flatMap(g => g.items)

  if (fullscreen) {
    return (
      <div className="fixed bottom-0 inset-x-0 z-50 bg-zinc-900/95 border-t border-zinc-800/40" style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}>
        {/* Tool options row */}
        {tool === 'paint' && (
          <div className="flex items-center gap-2 px-3 py-2 border-b border-zinc-800/20">
            <div className="flex items-center gap-0 rounded-xl border border-white/8 bg-zinc-950/80 p-0.5">
              <button
                onClick={() => setPaintMode('brush')}
                className={`px-2.5 py-2 rounded-lg text-[11px] font-medium cursor-pointer transition-colors ${
                  paintMode === 'brush' ? 'bg-white/[0.08] text-zinc-100' : 'text-zinc-500'
                }`}
              >Brush</button>
              <button
                onClick={() => setPaintMode('separator')}
                className={`px-2.5 py-2 rounded-lg text-[11px] font-medium cursor-pointer transition-colors ${
                  paintMode === 'separator' ? 'bg-white/[0.08] text-zinc-100' : 'text-zinc-500'
                }`}
              >Separator</button>
            </div>
            {paintMode === 'brush' && (
              <>
                <input
                  type="range" min="3" max="50" value={paintBrushSize}
                  onChange={(e) => setPaintBrushSize(Number(e.target.value))}
                  className="flex-1 max-w-32 h-1 accent-zinc-400"
                />
                <span className="text-[10px] text-zinc-400">{paintBrushSize}</span>
              </>
            )}
            {paintMode === 'brush' && selectedRoomIdx >= 0 && (
              <div className="flex items-center gap-1.5 ml-auto">
                <div
                  className="w-3 h-3 rounded-full border border-white/30"
                  style={{ backgroundColor: `rgb(${ROOM_PALETTE[selectedRoomIdx % ROOM_PALETTE.length].join(',')})` }}
                />
                <span className="text-[10px] text-zinc-400">
                  {annotations.filter(a => a.type === 'label')[selectedRoomIdx]?.roomName ?? 'Room'}
                </span>
              </div>
            )}
          </div>
        )}
        {tool === 'label' && labelCount > 0 && (
          <div className="flex items-center px-3 py-2 border-b border-zinc-800/20">
            <button
              onClick={onClearLabels}
              className="px-3 py-2 rounded-xl text-[11px] font-medium text-red-300 bg-red-500/8 border border-red-500/20 cursor-pointer"
            >
              Clear Labels ({labelCount})
            </button>
          </div>
        )}
        {/* Tool icons row */}
        <div className="flex items-center justify-around px-2 py-2">
          {allTools.map((item) => (
            <button
              key={item.type}
              onClick={() => setTool(item.type)}
              className={`flex flex-col items-center justify-center w-11 h-11 rounded-xl transition-all cursor-pointer ${
                tool === item.type
                  ? 'bg-white/[0.08] text-zinc-100'
                  : 'text-zinc-500'
              }`}
            >
              <span className="text-[14px] leading-none">{TOOL_ICONS[item.type] ?? '?'}</span>
              <span className="text-[8px] mt-0.5">{item.label}</span>
            </button>
          ))}
          <button
            onClick={fitImage}
            className="flex flex-col items-center justify-center w-11 h-11 rounded-xl text-zinc-500 cursor-pointer"
          >
            <span className="text-[14px] leading-none">⊡</span>
            <span className="text-[8px] mt-0.5">Fit</span>
          </button>
          <div className="relative" ref={hidePanelRef}>
            <button
              onClick={() => setHidePanelOpen(!hidePanelOpen)}
              title="Show/hide layers"
              className={`flex flex-col items-center justify-center w-11 h-11 rounded-xl cursor-pointer transition-colors ${
                anyHidden ? 'bg-white/[0.08] text-zinc-100' : 'text-zinc-500'
              }`}
            >
              <span className="text-[14px] leading-none">👁</span>
              <span className="text-[8px] mt-0.5">Hide</span>
            </button>
            {hidePanelOpen && (
              <div
                className="absolute bottom-full mb-2 right-0 w-48 rounded-xl border border-white/8 bg-zinc-900/95 backdrop-blur shadow-xl p-2 z-50"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 px-2 py-1.5">Visibility</div>
                {HIDE_LAYERS.map(({ key, label }) => (
                  <label
                    key={key}
                    className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-white/[0.04] cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={visibility[key]}
                      onChange={() => toggleLayer(key)}
                      className="w-3.5 h-3.5 accent-zinc-300 cursor-pointer"
                    />
                    <span className="text-[11px] text-zinc-200 select-none">{label}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
          <button onClick={undo} disabled={annotations.length === 0} className="flex flex-col items-center justify-center w-11 h-11 rounded-xl text-zinc-500 disabled:opacity-30 cursor-pointer">
            <span className="text-[14px] leading-none">↩</span>
            <span className="text-[8px] mt-0.5">Undo</span>
          </button>
          <button onClick={() => setFullscreen(false)} className="flex flex-col items-center justify-center w-11 h-11 rounded-xl bg-white/[0.04] text-zinc-300 cursor-pointer">
            <span className="text-[14px] leading-none">✓</span>
            <span className="text-[8px] mt-0.5">Done</span>
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2 px-3 py-2.5 bg-zinc-900/90 border-b border-zinc-800/40">
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
      <span className="text-[10px] text-zinc-700">
        {annotations.length} drawn
      </span>
    </div>
  )
}
