import { useState, useRef, useCallback, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { Status, AnnotationType, SwingDir, Annotation, V2Result } from './types'
import { fileToBase64 } from './utils/fileToBase64'
import { Spinner } from './components/Spinner'
import { UploadIcon } from './components/UploadIcon'
import { DownloadButton } from './components/DownloadButton'
import { DoorSwingPicker } from './components/DoorSwingPicker'
import { COLORS, TOOL_DEFS } from './components/OverlayEditor/constants'
import { hitTestAnnotation, hitTestEndpoint, snapToEndpoint } from './components/OverlayEditor/geometry'
import { renderCanvas as renderCanvasFn } from './components/OverlayEditor/renderCanvas'

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <div className="min-h-screen flex flex-col items-center px-4 sm:px-5 py-8 sm:py-16 safe-area-inset">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="text-center mb-6 sm:mb-10"
      >
        <h1 className="text-3xl sm:text-4xl font-light tracking-tight text-white/90">
          Pointe<span className="text-white/30">.ai</span>
        </h1>
        <p className="text-[10px] sm:text-xs tracking-[0.2em] uppercase text-zinc-600 mt-1.5 sm:mt-2">
          Floor Plan to DXF
        </p>
      </motion.div>

      {/* Panel */}
      <div className="w-full max-w-[640px]">
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
        >
          <UploadPanel />
        </motion.div>
      </div>
    </div>
  )
}

// ─── Upload Panel (v2) ────────────────────────────────────────────────────────

function UploadPanel() {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [status, setStatus] = useState<Status>('idle')
  const [statusMsg, setStatusMsg] = useState('')
  const [result, setResult] = useState<V2Result | null>(null)
  const [showDetails, setShowDetails] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [annotations, setAnnotations] = useState<Annotation[]>([])
  const [autoLoaded, setAutoLoaded] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFile = useCallback((f: File) => {
    setFile(f)
    setResult(null)
    setStatus('idle')
    setStatusMsg('')
    setAnnotations([])
    setAutoLoaded(false)
    const url = URL.createObjectURL(f)
    setPreview(url)
  }, [])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) handleFile(f)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files?.[0]
    if (f && f.type.startsWith('image/')) handleFile(f)
  }

  const generate = useCallback(async () => {
    if (!file) { setStatus('error'); setStatusMsg('Upload a floor plan image first.'); return }
    setStatus('loading'); setStatusMsg('Processing floor plan...'); setResult(null)

    try {
      const imageBase64 = await fileToBase64(file)
      const body: Record<string, unknown> = { image: imageBase64, model_variant: 'ensemble' }
      // After auto-annotations are loaded, always send annotations
      // (even if empty = user deleted all detections).
      // On first run (autoLoaded=false), don't send → backend uses auto-detected.
      if (autoLoaded) {
        body.annotations = annotations.map(({ _source, ...rest }) => rest)
      } else if (annotations.length > 0) {
        body.annotations = annotations.map(({ _source, ...rest }) => rest)
      }

      const res = await fetch('/api/v2/generate-dxf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!res.ok) throw new Error((await res.json()).detail ?? `Error ${res.status}`)
      const data: V2Result = await res.json()
      setResult(data); setStatus('done'); setStatusMsg('')

      // Load auto-detected annotations into editor on first run
      if (!autoLoaded && data.auto_annotations?.length) {
        setAnnotations(data.auto_annotations.map(a => ({
          type: a.type as AnnotationType,
          x1: a.x1, y1: a.y1, x2: a.x2, y2: a.y2,
          ...(a.swing ? { swing: a.swing as SwingDir } : {}),
          _source: a._source ?? 'ensemble_cubicasa',
        })))
        setAutoLoaded(true)
      }
    } catch (e) {
      setStatus('error')
      setStatusMsg(e instanceof Error ? e.message : 'Unknown error')
    }
  }, [file, annotations, autoLoaded])

  return (
    <>
      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileRef.current?.click()}
        className={`relative w-full rounded-lg border cursor-pointer
                    transition-all duration-200 overflow-hidden
                    ${dragging
                      ? 'border-zinc-500 bg-white/[0.04]'
                      : 'border-zinc-800/60 bg-zinc-950 hover:border-zinc-700'}
                    active:bg-white/[0.04]`}
        style={{ minHeight: preview ? 'auto' : '140px' }}
      >
        <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleFileChange} />

        {preview ? (
          <div className="relative">
            <img src={preview} alt="floor plan" className="w-full object-contain max-h-48 sm:max-h-64 rounded-lg" />
            <div className="absolute inset-0 bg-black/40 opacity-0 hover:opacity-100 transition-opacity
                            flex items-center justify-center rounded-lg">
              <span className="text-xs text-zinc-300">Tap to change</span>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-36 sm:h-40 gap-2 sm:gap-3">
            <UploadIcon size={20} className="text-zinc-700" />
            <div className="text-center">
              <p className="text-xs text-zinc-500">Tap or drop a floor plan image</p>
              <p className="text-[10px] text-zinc-700 mt-1">PNG, JPG, JPEG</p>
            </div>
          </div>
        )}
      </div>

      {/* Generate button */}
      <motion.button
        whileTap={{ scale: 0.98 }}
        onClick={generate}
        disabled={status === 'loading' || !file}
        className="w-full mt-4 py-3.5 sm:py-3 rounded-lg text-sm font-medium
                   bg-white/[0.06] text-zinc-400 border border-zinc-800/60
                   hover:bg-white/[0.09] hover:text-zinc-300
                   disabled:opacity-30 disabled:cursor-not-allowed
                   transition-all duration-200 cursor-pointer
                   active:bg-white/[0.12]"
      >
        {status === 'loading'
          ? <span className="flex items-center justify-center gap-2"><Spinner />Processing...</span>
          : 'Generate DXF'}
      </motion.button>

      {/* Status message */}
      <AnimatePresence>
        {statusMsg && (
          <motion.p initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className={`text-center text-xs mt-4 ${status === 'error' ? 'text-red-500/70' : 'text-zinc-600'}`}>
            {statusMsg}
          </motion.p>
        )}
      </AnimatePresence>

      {/* Results */}
      <AnimatePresence>
        {result && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="mt-6 space-y-3 sm:space-y-4">

            {/* Interactive overlay editor */}
            {result.preview_url && (
              <OverlayEditor
                previewUrl={result.preview_url}
                annotations={annotations}
                setAnnotations={setAnnotations}
              />
            )}

            {/* Download */}
            <DownloadButton href={result.dxf_url} />

            {/* TODO: Canvas editor for manual walls/doors/windows */}

            {/* Details toggle */}
            <button onClick={() => setShowDetails(!showDetails)}
              className="text-xs text-zinc-600 hover:text-zinc-500 transition-colors cursor-pointer">
              {showDetails ? 'Hide' : 'Show'} details
            </button>

            <AnimatePresence>
              {showDetails && (
                <motion.pre initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }}
                  className="p-3 bg-zinc-950 border border-zinc-800/40 rounded-md
                             text-[10px] sm:text-[11px] leading-relaxed text-zinc-600 font-mono overflow-auto max-h-60 sm:max-h-80">
                  {JSON.stringify(result.structure, null, 2)}
                </motion.pre>
              )}
            </AnimatePresence>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}

// ─── Shared components ────────────────────────────────────────────────────────



function OverlayEditor({ previewUrl, annotations, setAnnotations }: {
  previewUrl: string
  annotations: Annotation[]
  setAnnotations: (a: Annotation[]) => void
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [tool, setTool] = useState<AnnotationType>('wall')
  const [drawing, setDrawing] = useState(false)
  const [startPt, setStartPt] = useState<{ x: number; y: number } | null>(null)
  const [fullscreen, setFullscreen] = useState(false)
  const [eraserSize, setEraserSize] = useState(10)

  // Refs that mirror state for use in mousemove (avoids stale closures)
  const drawingRef = useRef(false)
  const startPtRef = useRef<{ x: number; y: number } | null>(null)
  const cursorPtRef = useRef<{ x: number; y: number } | null>(null)
  const toolRef = useRef<AnnotationType>(tool)
  const annotationsRef = useRef(annotations)
  const rafId = useRef<number>(0)
  const hoveredIdxRef = useRef<number>(-1)
  // Drag-resize: which annotation endpoint is being dragged
  const draggingRef = useRef<{ idx: number; endpoint: 'start' | 'end' | 'arc' } | null>(null)

  // Keep refs in sync with state
  useEffect(() => { toolRef.current = tool }, [tool])
  useEffect(() => { annotationsRef.current = annotations }, [annotations])

  // Pan + Zoom state
  const [view, setView] = useState({ offsetX: 0, offsetY: 0, scale: 1 })
  const viewRef = useRef(view)
  useEffect(() => { viewRef.current = view }, [view])
  const isPanning = useRef(false)
  const panStart = useRef({ x: 0, y: 0 })
  const spaceDown = useRef(false)
  const imgRef = useRef<HTMLImageElement | null>(null)

  const snapRef = useRef<{ x: number; y: number; snapped: boolean }>({ x: 0, y: 0, snapped: false })

  // Geometry wrappers — delegate to pure functions, pass refs explicitly
  const _hitTest = (wx: number, wy: number) => hitTestAnnotation(wx, wy, annotationsRef.current, viewRef.current.scale)
  const _hitEndpoint = (wx: number, wy: number) => hitTestEndpoint(wx, wy, annotationsRef.current, viewRef.current.scale)
  const _snap = (wx: number, wy: number, skipIdx = -1) => snapToEndpoint(wx, wy, annotationsRef.current, viewRef.current.scale, skipIdx)

  // Screen mouse → world (image-pixel) coordinates, accounting for pan+zoom
  const screenToWorld = (clientX: number, clientY: number) => {
    const canvas = canvasRef.current
    if (!canvas) return { x: 0, y: 0 }
    const rect = canvas.getBoundingClientRect()
    const canvasX = (clientX - rect.left) * (canvas.width / rect.width)
    const canvasY = (clientY - rect.top) * (canvas.height / rect.height)
    return {
      x: Math.round((canvasX - view.offsetX) / view.scale),
      y: Math.round((canvasY - view.offsetY) / view.scale),
    }
  }

  // Index of existing door being re-picked (swing edit via DoorSwingPicker)
  const editingDoorIdxRef = useRef<number>(-1)

  // Fit image inside canvas on load
  const fitImage = useCallback(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    const img = imgRef.current
    if (!canvas || !container || !img) return

    const cw = container.clientWidth
    const ch = container.clientHeight || 400
    canvas.width = cw
    canvas.height = ch

    const s = Math.min(cw / img.width, ch / img.height, 1)
    const ox = (cw - img.width * s) / 2
    const oy = (ch - img.height * s) / 2
    setView({ offsetX: ox, offsetY: oy, scale: s })
  }, [])

  // Load image once into ref
  useEffect(() => {
    const img = new Image()
    img.onload = () => {
      imgRef.current = img
      fitImage()
    }
    img.src = previewUrl
  }, [previewUrl, fitImage])

  // Resize canvas when container changes (fullscreen toggle)
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const ro = new ResizeObserver(() => fitImage())
    ro.observe(container)
    return () => ro.disconnect()
  }, [fitImage])

  // Core render: clear → grid → image → annotations → live preview overlay
  const renderCanvas = useCallback(() => {
    const canvas = canvasRef.current
    const img = imgRef.current
    if (!canvas || !img) return
    renderCanvasFn(
      canvas, img, viewRef.current, annotationsRef.current,
      hoveredIdxRef.current, snapRef.current,
      { active: drawingRef.current, start: startPtRef.current, cursor: cursorPtRef.current, tool: toolRef.current },
    )
  }, [])  // stable — reads everything from refs

  // Schedule a render via requestAnimationFrame (debounced)
  const scheduleRender = useCallback(() => {
    cancelAnimationFrame(rafId.current)
    rafId.current = requestAnimationFrame(() => renderCanvas())
  }, [renderCanvas])

  // React-triggered redraws when state changes
  useEffect(() => { scheduleRender() }, [view, annotations, scheduleRender])

  // Space key for pan mode
  useEffect(() => {
    const onDown = (e: KeyboardEvent) => { if (e.code === 'Space') { e.preventDefault(); spaceDown.current = true } }
    const onUp = (e: KeyboardEvent) => { if (e.code === 'Space') spaceDown.current = false }
    window.addEventListener('keydown', onDown)
    window.addEventListener('keyup', onUp)
    return () => { window.removeEventListener('keydown', onDown); window.removeEventListener('keyup', onUp) }
  }, [])

  // Wheel zoom centered on cursor
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const rect = canvas.getBoundingClientRect()
      const mouseX = (e.clientX - rect.left) * (canvas.width / rect.width)
      const mouseY = (e.clientY - rect.top) * (canvas.height / rect.height)

      setView(v => {
        const worldX = (mouseX - v.offsetX) / v.scale
        const worldY = (mouseY - v.offsetY) / v.scale
        const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15
        const newScale = Math.min(Math.max(v.scale * factor, 0.1), 30)
        return {
          scale: newScale,
          offsetX: mouseX - worldX * newScale,
          offsetY: mouseY - worldY * newScale,
        }
      })
    }
    canvas.addEventListener('wheel', onWheel, { passive: false })
    return () => canvas.removeEventListener('wheel', onWheel)
  }, [])

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    // Middle-click or Space+left → pan
    if (e.button === 1 || (e.button === 0 && spaceDown.current)) {
      e.preventDefault()
      isPanning.current = true
      panStart.current = { x: e.clientX - view.offsetX, y: e.clientY - view.offsetY }
      return
    }
    // Check endpoint drag-resize first
    const ptDown = screenToWorld(e.clientX, e.clientY)
    const ep = _hitEndpoint(ptDown.x, ptDown.y)
    if (ep) {
      draggingRef.current = ep
      return
    }
    // Clicked on a hovered annotation
    if (hoveredIdxRef.current >= 0) {
      const idx = hoveredIdxRef.current
      const ha = annotationsRef.current[idx]
      if (ha) {
        const cx = (ha.x1 + ha.x2) / 2
        const cy = (ha.y1 + ha.y2) / 2
        const pt = screenToWorld(e.clientX, e.clientY)
        const hitRadius = 10 / viewRef.current.scale
        const dist = Math.sqrt((pt.x - cx) ** 2 + (pt.y - cy) ** 2)
        // Click on × → delete
        if (dist <= hitRadius) {
          setAnnotations(annotations.filter((_, i) => i !== idx))
          hoveredIdxRef.current = -1
          setPendingDoor(null)
          scheduleRender()
          return
        }
        // Click on door/window line → open picker to edit swing/side
        if (ha.type === 'door' || ha.type === 'window') {
          const rect = canvasRef.current!.getBoundingClientRect()
          const sx = e.clientX - rect.left
          const sy = e.clientY - rect.top
          editingDoorIdxRef.current = idx
          setPendingDoor({ x1: ha.x1, y1: ha.y1, x2: ha.x2, y2: ha.y2, sx, sy })
          return
        }
      }
    }
    const ptRaw = screenToWorld(e.clientX, e.clientY)
    const pt = _snap(ptRaw.x, ptRaw.y)
    snapRef.current = pt
    setDrawing(true)
    setStartPt(pt)
    // Sync refs for live preview
    drawingRef.current = true
    startPtRef.current = pt
    cursorPtRef.current = pt
  }

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (isPanning.current) {
      setView(v => ({
        ...v,
        offsetX: e.clientX - panStart.current.x,
        offsetY: e.clientY - panStart.current.y,
      }))
      return
    }

    // Drag-resize endpoint with snap
    if (draggingRef.current) {
      const ptRaw = screenToWorld(e.clientX, e.clientY)
      const { idx, endpoint } = draggingRef.current
      setAnnotations(annotations.map((a, i) => {
        if (i !== idx) return a
        if (endpoint === 'arc' && a.swing) {
          const slabAs: Record<string, number> = { up: -Math.PI / 2, down: Math.PI / 2, left: Math.PI, right: 0 }
          const sA = slabAs[a.swing]
          const dx = ptRaw.x - a.x1, dy = ptRaw.y - a.y1
          const proj = dx * Math.cos(sA) + dy * Math.sin(sA)
          return { ...a, arcRadius: Math.max(5, Math.abs(proj)) }
        }
        const pt = _snap(ptRaw.x, ptRaw.y, idx)
        snapRef.current = pt
        return endpoint === 'start'
          ? { ...a, x1: pt.x, y1: pt.y }
          : { ...a, x2: pt.x, y2: pt.y }
      }))
      scheduleRender()
      return
    }

    if (drawingRef.current && startPtRef.current) {
      const ptRaw = screenToWorld(e.clientX, e.clientY)
      const snapped = _snap(ptRaw.x, ptRaw.y)
      snapRef.current = snapped
      cursorPtRef.current = snapped
      scheduleRender()
      return
    }

    // Not drawing → hit-test for hover delete + door swing tooltip + endpoint resize
    const pt = screenToWorld(e.clientX, e.clientY)
    const epHover = _hitEndpoint(pt.x, pt.y)
    const prev = hoveredIdxRef.current
    hoveredIdxRef.current = _hitTest(pt.x, pt.y)
    if (hoveredIdxRef.current !== prev || epHover) {
      const c = canvasRef.current
      if (c) c.style.cursor = epHover ? 'grab' : hoveredIdxRef.current >= 0 ? 'pointer' : 'crosshair'
      scheduleRender()
    }
  }

  const [pendingDoor, setPendingDoor] = useState<{ x1: number; y1: number; x2: number; y2: number; sx: number; sy: number } | null>(null)

  const handleMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (isPanning.current) { isPanning.current = false; return }
    if (draggingRef.current) { draggingRef.current = null; return }
    if (!drawingRef.current || !startPtRef.current) return
    const ptRaw = screenToWorld(e.clientX, e.clientY)
    const pt = _snap(ptRaw.x, ptRaw.y)
    snapRef.current = { x: 0, y: 0, snapped: false }
    const sp = startPtRef.current

    // Clear drawing state (both state and refs)
    setDrawing(false)
    drawingRef.current = false
    cursorPtRef.current = null

    const dx = Math.abs(pt.x - sp.x)
    const dy = Math.abs(pt.y - sp.y)
    if (dx < 5 && dy < 5) { setStartPt(null); startPtRef.current = null; scheduleRender(); return }

    if (tool === 'eraser') {
      const rx1 = Math.min(sp.x, pt.x)
      const ry1 = Math.min(sp.y, pt.y)
      const rx2 = Math.max(sp.x, pt.x)
      const ry2 = Math.max(sp.y, pt.y)

      const remaining = annotations.filter((a) => {
        if (a.type === 'eraser') return true
        const aMidX = (a.x1 + a.x2) / 2
        const aMidY = (a.y1 + a.y2) / 2
        return !(aMidX >= rx1 && aMidX <= rx2 && aMidY >= ry1 && aMidY <= ry2)
      })
      remaining.push({ type: 'eraser', x1: rx1, y1: ry1, x2: rx2, y2: ry2 })
      setAnnotations(remaining)
    } else if (tool === 'door') {
      const rect = canvasRef.current!.getBoundingClientRect()
      const sx = e.clientX - rect.left
      const sy = e.clientY - rect.top
      setPendingDoor({ x1: sp.x, y1: sp.y, x2: pt.x, y2: pt.y, sx, sy })
    } else {
      setAnnotations([...annotations, {
        type: tool,
        x1: sp.x, y1: sp.y,
        x2: pt.x, y2: pt.y,
      }])
    }
    setStartPt(null)
    startPtRef.current = null
    scheduleRender()
  }

  const addDoorWithSwing = (dir: SwingDir) => {
    if (!pendingDoor) return
    const editIdx = editingDoorIdxRef.current
    if (editIdx >= 0) {
      // Editing existing door swing
      setAnnotations(annotations.map((a, i) => i === editIdx ? { ...a, swing: dir } : a))
    } else {
      // New door
      setAnnotations([...annotations, { type: 'door', ...pendingDoor, swing: dir }])
    }
    editingDoorIdxRef.current = -1
    setPendingDoor(null)
  }

  const mirrorDoor = () => {
    const idx = editingDoorIdxRef.current
    if (idx < 0) return
    // Swap endpoints: hinge moves to the other side
    setAnnotations(annotations.map((a, i) => {
      if (i !== idx) return a
      return { ...a, x1: a.x2, y1: a.y2, x2: a.x1, y2: a.y1 }
    }))
    // Update pendingDoor coords too so the picker stays consistent
    setPendingDoor(prev => prev ? { ...prev, x1: prev.x2, y1: prev.y2, x2: prev.x1, y2: prev.y1 } : null)
  }

  const undo = () => {
    if (annotations.length > 0) setAnnotations(annotations.slice(0, -1))
  }

  const zoomLabel = `${Math.round(view.scale * 100)}%`

  const tools: { type: AnnotationType; label: string; color: string }[] = [
    { type: 'wall', label: 'Wall', color: 'bg-red-900/40 border-red-700/50 text-red-400' },
    { type: 'door', label: 'Door', color: 'bg-green-900/40 border-green-700/50 text-green-400' },
    { type: 'window', label: 'Window', color: 'bg-blue-900/40 border-blue-700/50 text-blue-400' },
    { type: 'eraser', label: 'Eraser', color: 'bg-zinc-700/40 border-zinc-500/50 text-zinc-300' },
  ]

  return (
    <div className={`rounded-lg overflow-hidden border border-zinc-800/60 transition-all duration-300
      ${fullscreen ? 'fixed inset-4 z-50 bg-zinc-950 flex flex-col' : ''}`}>
      {/* Toolbar */}
      <div className="flex items-center gap-1.5 px-2 py-1.5 bg-zinc-900/80 border-b border-zinc-800/40">
        {fullscreen ? (
          <>
            {tools.map((t) => (
              <button
                key={t.type}
                onClick={() => setTool(t.type)}
                className={`px-2.5 py-1 rounded text-[10px] font-medium border transition-all cursor-pointer
                  ${tool === t.type ? t.color + ' ring-1 ring-white/20' : 'bg-zinc-900 border-zinc-800 text-zinc-600'}`}
              >
                {t.label}
              </button>
            ))}
            {tool === 'eraser' && (
              <div className="flex items-center gap-1 ml-1">
                <span className="text-[9px] text-zinc-600">Size</span>
                <input
                  type="range" min="3" max="30" value={eraserSize}
                  onChange={(e) => setEraserSize(Number(e.target.value))}
                  className="w-14 h-1 accent-zinc-500"
                />
                <span className="text-[9px] text-zinc-500 w-4">{eraserSize}</span>
              </div>
            )}
            <div className="flex items-center gap-1 ml-2">
              <button
                onClick={fitImage}
                className="px-2 py-1 rounded text-[10px] text-zinc-500 hover:text-zinc-300 bg-zinc-900 border border-zinc-800 cursor-pointer transition-colors"
              >
                Fit
              </button>
              <span className="text-[9px] text-zinc-600 w-8 text-center">{zoomLabel}</span>
            </div>
            <div className="flex-1" />
            <button
              onClick={undo}
              disabled={annotations.length === 0}
              className="px-2 py-1 rounded text-[10px] text-zinc-500 hover:text-zinc-300
                         disabled:opacity-30 cursor-pointer transition-colors"
            >
              Undo
            </button>
            <button
              onClick={() => setFullscreen(false)}
              className="px-2 py-1 rounded text-[10px] text-zinc-500 hover:text-zinc-300 cursor-pointer transition-colors"
            >
              Done
            </button>
          </>
        ) : (
          <>
            <div className="flex-1" />
            <button
              onClick={() => setFullscreen(true)}
              className="px-3 py-1 rounded text-[10px] font-medium text-zinc-400 bg-zinc-800/60 border border-zinc-700/50
                         hover:bg-zinc-700/60 hover:text-zinc-300 cursor-pointer transition-colors"
            >
              Edit
            </button>
          </>
        )}
        <span className="text-[9px] text-zinc-700">
          {annotations.length} drawn
        </span>
      </div>

      {/* Canvas */}
      <div ref={containerRef} className={`relative ${fullscreen ? 'flex-1 overflow-hidden' : 'h-64'}`}>
        <canvas
          ref={canvasRef}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={() => { setDrawing(false); setStartPt(null); drawingRef.current = false; startPtRef.current = null; cursorPtRef.current = null; isPanning.current = false; hoveredIdxRef.current = -1; draggingRef.current = null; scheduleRender() }}
          className="absolute inset-0 w-full h-full"
          style={{ cursor: spaceDown.current || isPanning.current ? 'grab' : 'crosshair' }}
        />
        {/* Door swing popup — appears where user released the mouse */}
        {pendingDoor && (() => {
          const editIdx = editingDoorIdxRef.current
          const editingType = editIdx >= 0 ? annotations[editIdx]?.type : 'door'
          const isWindow = editingType === 'window'
          return <DoorSwingPicker
            pendingDoor={pendingDoor}
            onPick={addDoorWithSwing}
            onCancel={() => { editingDoorIdxRef.current = -1; setPendingDoor(null) }}
            onMirror={editIdx >= 0 && !isWindow ? mirrorDoor : undefined}
            label={isWindow ? 'Exterior' : 'Opens'}
          />
        })()}
      </div>

    </div>
  )
}

