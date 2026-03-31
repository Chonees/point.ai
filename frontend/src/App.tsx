import { useState, useRef, useCallback, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

// ─── Types ────────────────────────────────────────────────────────────────────

type Status = 'idle' | 'loading' | 'done' | 'error'
type ModelVariant = 'baseline' | 'mitunet' | 'ensemble'
type AnnotationType = 'wall' | 'door' | 'window' | 'eraser'
type SwingDir = 'up' | 'down' | 'left' | 'right'
interface Annotation { type: AnnotationType; x1: number; y1: number; x2: number; y2: number; swing?: SwingDir; _source?: string; arcRadius?: number }

interface V2Result {
  dxf_url: string
  preview_url: string | null
  structure: Record<string, unknown>
  quality_metrics: Record<string, unknown>
  review_flags: string[]
  needs_review: boolean
  scale_status: string
  auto_annotations?: { type: string; x1: number; y1: number; x2: number; y2: number; swing?: string; _source?: string }[]
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

function Spinner() {
  return (
    <motion.span
      animate={{ rotate: 360 }}
      transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
      className="inline-block w-3.5 h-3.5 border border-zinc-600 border-t-zinc-400 rounded-full"
    />
  )
}

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

function Stat({ label, value, dim = false }: { label: string; value: string; dim?: boolean }) {
  return (
    <div className="p-2.5 sm:p-3 bg-zinc-900/50 border border-zinc-800/40 rounded-lg text-center">
      <p className={`text-base sm:text-lg font-light ${dim ? 'text-zinc-600' : 'text-zinc-300'}`}>{value}</p>
      <p className="text-[9px] sm:text-[10px] text-zinc-700 mt-0.5">{label}</p>
    </div>
  )
}


function DoorSwingPicker({ pendingDoor, onPick, onCancel, onMirror, label }: {
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
}


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

  const COLORS: Record<AnnotationType, string> = {
    wall: '#ff3333',
    door: '#33ff66',
    window: '#3399ff',
    eraser: '#888888',
  }

  // Distance from point to line segment
  const _distToSeg = (px: number, py: number, x1: number, y1: number, x2: number, y2: number) => {
    const dx = x2 - x1, dy = y2 - y1
    const lenSq = dx * dx + dy * dy
    if (lenSq < 1) return Math.sqrt((px - x1) ** 2 + (py - y1) ** 2)
    const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lenSq))
    return Math.sqrt((px - (x1 + t * dx)) ** 2 + (py - (y1 + t * dy)) ** 2)
  }

  // Check if angle is within the 90° arc sweep from sA to oA
  const _angleInArc = (angle: number, sA: number, oA: number) => {
    // Normalize all to [0, 2π]
    const norm = (a: number) => ((a % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI)
    const a = norm(angle), s = norm(sA), o = norm(oA)
    // Check both sweep directions, pick the one that's ≤180°
    const cw = ((o - s) + 2 * Math.PI) % (2 * Math.PI)
    if (cw <= Math.PI) {
      // Clockwise from s to o
      return ((a - s) + 2 * Math.PI) % (2 * Math.PI) <= cw
    }
    // Counter-clockwise from s to o
    const ccw = 2 * Math.PI - cw
    return ((s - a) + 2 * Math.PI) % (2 * Math.PI) <= ccw
  }

  // Hit-test: find annotation index nearest to point (within threshold)
  const hitTestAnnotation = (wx: number, wy: number): number => {
    const threshold = 12 / viewRef.current.scale
    const anns = annotationsRef.current
    for (let i = anns.length - 1; i >= 0; i--) {
      const a = anns[i]
      if (a.type === 'eraser') {
        // Point inside rectangle
        const rx1 = Math.min(a.x1, a.x2), ry1 = Math.min(a.y1, a.y2)
        const rx2 = Math.max(a.x1, a.x2), ry2 = Math.max(a.y1, a.y2)
        if (wx >= rx1 - threshold && wx <= rx2 + threshold && wy >= ry1 - threshold && wy <= ry2 + threshold) return i
      } else if (a.type === 'door' && a.swing) {
        // Hit-test door: opening line + slab lines + arc
        const hx = a.x1, hy = a.y1
        const openingW = Math.sqrt((a.x2 - a.x1) ** 2 + (a.y2 - a.y1) ** 2)
        const arcR = a.arcRadius ?? openingW
        const slabAngles: Record<string, number> = { up: -Math.PI / 2, down: Math.PI / 2, left: Math.PI, right: 0 }
        const sA = slabAngles[a.swing]
        const tipX = hx + Math.cos(sA) * arcR, tipY = hy + Math.sin(sA) * arcR

        // Check slab line (hinge to tip)
        const distToSlab = _distToSeg(wx, wy, hx, hy, tipX, tipY)
        if (distToSlab < threshold) return i

        // Check opening line (x1,y1 to x2,y2)
        const distToOpening = _distToSeg(wx, wy, a.x1, a.y1, a.x2, a.y2)
        if (distToOpening < threshold) return i

        // Check arc (distance to arc curve)
        const distFromHinge = Math.sqrt((wx - hx) ** 2 + (wy - hy) ** 2)
        if (Math.abs(distFromHinge - arcR) < threshold) {
          // Check angle is within the arc sweep
          const ptAngle = Math.atan2(wy - hy, wx - hx)
          const oA = Math.atan2(a.y2 - a.y1, a.x2 - a.x1)
          if (_angleInArc(ptAngle, sA, oA)) return i
        }
      } else {
        // Distance from point to line segment
        const dx = a.x2 - a.x1, dy = a.y2 - a.y1
        const lenSq = dx * dx + dy * dy
        if (lenSq < 1) continue
        const t = Math.max(0, Math.min(1, ((wx - a.x1) * dx + (wy - a.y1) * dy) / lenSq))
        const px = a.x1 + t * dx, py = a.y1 + t * dy
        const dist = Math.sqrt((wx - px) ** 2 + (wy - py) ** 2)
        if (dist < threshold) return i
      }
    }
    return -1
  }

  // Hit-test for annotation endpoints (for drag-resize)
  const hitTestEndpoint = (wx: number, wy: number): { idx: number; endpoint: 'start' | 'end' | 'arc' } | null => {
    const threshold = 10 / viewRef.current.scale
    const anns = annotationsRef.current
    for (let i = anns.length - 1; i >= 0; i--) {
      const a = anns[i]
      if (a.type === 'eraser') continue
      // Arc handle for doors with swing (tip of the arc)
      if (a.type === 'door' && a.swing) {
        const arcR = a.arcRadius ?? Math.sqrt((a.x2 - a.x1) ** 2 + (a.y2 - a.y1) ** 2)
        const slabAngles: Record<string, number> = { up: -Math.PI / 2, down: Math.PI / 2, left: Math.PI, right: 0 }
        const sA = slabAngles[a.swing]
        const tipX = a.x1 + Math.cos(sA) * arcR
        const tipY = a.y1 + Math.sin(sA) * arcR
        const dt = Math.sqrt((wx - tipX) ** 2 + (wy - tipY) ** 2)
        if (dt < threshold) return { idx: i, endpoint: 'arc' }
      }
      const d1 = Math.sqrt((wx - a.x1) ** 2 + (wy - a.y1) ** 2)
      if (d1 < threshold) return { idx: i, endpoint: 'start' }
      const d2 = Math.sqrt((wx - a.x2) ** 2 + (wy - a.y2) ** 2)
      if (d2 < threshold) return { idx: i, endpoint: 'end' }
    }
    return null
  }

  // Snap point to nearest annotation endpoint (within threshold)
  const snapToEndpoint = (wx: number, wy: number, skipIdx: number = -1): { x: number; y: number; snapped: boolean } => {
    const threshold = 8 / viewRef.current.scale
    let bestDist = threshold
    let snap = { x: wx, y: wy, snapped: false }
    const anns = annotationsRef.current
    for (let i = 0; i < anns.length; i++) {
      if (i === skipIdx) continue
      const a = anns[i]
      if (a.type === 'eraser') continue
      for (const [px, py] of [[a.x1, a.y1], [a.x2, a.y2]] as [number, number][]) {
        const d = Math.sqrt((wx - px) ** 2 + (wy - py) ** 2)
        if (d < bestDist) {
          bestDist = d
          snap = { x: px, y: py, snapped: true }
        }
      }
    }
    return snap
  }
  const snapRef = useRef<{ x: number; y: number; snapped: boolean }>({ x: 0, y: 0, snapped: false })

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
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const v = viewRef.current
    const anns = annotationsRef.current

    // Clear in screen space
    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    // Dotted grid background
    ctx.fillStyle = '#111111'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    const dotSpacing = 20
    ctx.fillStyle = '#2a2a2a'
    for (let dx = (v.offsetX % dotSpacing + dotSpacing) % dotSpacing; dx < canvas.width; dx += dotSpacing) {
      for (let dy = (v.offsetY % dotSpacing + dotSpacing) % dotSpacing; dy < canvas.height; dy += dotSpacing) {
        ctx.beginPath()
        ctx.arc(dx, dy, 1, 0, Math.PI * 2)
        ctx.fill()
      }
    }

    // Apply pan+zoom
    ctx.setTransform(v.scale, 0, 0, v.scale, v.offsetX, v.offsetY)

    // Draw image at origin in world space
    ctx.drawImage(img, 0, 0)

    // Draw committed annotations
    for (const ann of anns) {
      const isAuto = ann._source === 'ensemble_cubicasa'
      if (ann.type === 'eraser') {
        ctx.fillStyle = 'rgba(0, 0, 0, 0.7)'
        ctx.fillRect(ann.x1, ann.y1, ann.x2 - ann.x1, ann.y2 - ann.y1)
        ctx.strokeStyle = '#ff4444'
        ctx.lineWidth = 1 / v.scale
        ctx.setLineDash([3 / v.scale, 3 / v.scale])
        ctx.strokeRect(ann.x1, ann.y1, ann.x2 - ann.x1, ann.y2 - ann.y1)
        ctx.setLineDash([])
      } else {
        // AI-detected annotations: dashed + slightly transparent
        if (isAuto) {
          ctx.setLineDash([6 / v.scale, 4 / v.scale])
          ctx.globalAlpha = 0.8
        }
        // Doors/windows without direction = yellow (needs attention), with = green (done)
        const color = (ann.type === 'door' || ann.type === 'window')
          ? (ann.swing ? '#33ff66' : '#ffcc00')
          : COLORS[ann.type]
        const lw = (ann.type === 'wall' ? 6 : 3) / v.scale
        ctx.strokeStyle = color
        ctx.lineWidth = lw

        if (ann.type === 'door' && ann.swing) {
          // Draw door: slab (2 parallel lines) + 90° arc
          // Uses angles so mirror is handled automatically.
          const openingW = Math.sqrt((ann.x2 - ann.x1) ** 2 + (ann.y2 - ann.y1) ** 2)
          const arcR = ann.arcRadius ?? openingW
          const hx = ann.x1, hy = ann.y1
          const ds = 3 / v.scale

          // Slab direction angle (where the door panel goes)
          const slabA: Record<string, number> = { up: -Math.PI / 2, down: Math.PI / 2, left: Math.PI, right: 0 }
          const sA = slabA[ann.swing]
          // Opening direction angle (from hinge toward far endpoint)
          const oA = Math.atan2(ann.y2 - ann.y1, ann.x2 - ann.x1)

          // Slab tip and opening endpoint
          const tipX = hx + Math.cos(sA) * arcR, tipY = hy + Math.sin(sA) * arcR
          const odx = Math.cos(oA) * ds, ody = Math.sin(oA) * ds

          // Slab: 2 parallel lines from hinge to tip
          ctx.beginPath()
          ctx.moveTo(hx, hy); ctx.lineTo(tipX, tipY)
          ctx.moveTo(hx + odx, hy + ody); ctx.lineTo(tipX + odx, tipY + ody)
          ctx.stroke()

          // Arc: bezier curve from slab tip to opening endpoint (adapts to any arcRadius)
          const cpX = tipX + (ann.x2 - hx), cpY = tipY + (ann.y2 - hy)
          ctx.beginPath()
          ctx.moveTo(tipX, tipY)
          ctx.quadraticCurveTo(cpX, cpY, ann.x2, ann.y2)
          ctx.stroke()
        } else if (ann.type === 'window') {
          // Draw window preview: 3 parallel lines + end caps
          const adx = Math.abs(ann.x2 - ann.x1)
          const ady = Math.abs(ann.y2 - ann.y1)
          const sp = 2 / v.scale // spacing between lines
          if (adx >= ady) {
            const xLo = Math.min(ann.x1, ann.x2), xHi = Math.max(ann.x1, ann.x2)
            const yM = (ann.y1 + ann.y2) / 2
            for (const off of [0, -sp, -sp * 2]) {
              ctx.beginPath(); ctx.moveTo(xLo, yM + off); ctx.lineTo(xHi, yM + off); ctx.stroke()
            }
            // End caps
            ctx.beginPath()
            ctx.moveTo(xLo, yM - sp); ctx.lineTo(xLo, yM - sp * 2)
            ctx.moveTo(xHi, yM - sp); ctx.lineTo(xHi, yM - sp * 2)
            ctx.stroke()
          } else {
            const yLo = Math.min(ann.y1, ann.y2), yHi = Math.max(ann.y1, ann.y2)
            const xM = (ann.x1 + ann.x2) / 2
            for (const off of [0, -sp, sp]) {
              ctx.beginPath(); ctx.moveTo(xM + off, yLo); ctx.lineTo(xM + off, yHi); ctx.stroke()
            }
            // End caps
            ctx.beginPath()
            ctx.moveTo(xM - sp, yLo); ctx.lineTo(xM, yLo)
            ctx.moveTo(xM - sp, yHi); ctx.lineTo(xM, yHi)
            ctx.stroke()
          }
        } else {
          // Walls and doors without swing: simple line
          ctx.beginPath()
          ctx.moveTo(ann.x1, ann.y1)
          ctx.lineTo(ann.x2, ann.y2)
          ctx.stroke()
        }

        ctx.fillStyle = color
        ctx.font = `${10 / v.scale}px monospace`
        const label = ann.type[0].toUpperCase()
        ctx.fillText(label, Math.min(ann.x1, ann.x2) - 12 / v.scale, (ann.y1 + ann.y2) / 2 + 4 / v.scale)

        // Endpoint handles on hovered annotation (for drag-resize)
        if (hoveredIdxRef.current === anns.indexOf(ann)) {
          const er = 4 / v.scale
          const handles: [number, number][] = [[ann.x1, ann.y1], [ann.x2, ann.y2]]
          // Third handle at arc tip (end of slab)
          if (ann.type === 'door' && ann.swing) {
            const arcR = ann.arcRadius ?? Math.sqrt((ann.x2 - ann.x1) ** 2 + (ann.y2 - ann.y1) ** 2)
            const slabAngles: Record<string, number> = { up: -Math.PI / 2, down: Math.PI / 2, left: Math.PI, right: 0 }
            const sA = slabAngles[ann.swing]
            handles.push([ann.x1 + Math.cos(sA) * arcR, ann.y1 + Math.sin(sA) * arcR])
          }
          for (const [px, py] of handles) {
            ctx.fillStyle = '#ffffff'
            ctx.strokeStyle = color
            ctx.lineWidth = 1.5 / v.scale
            ctx.setLineDash([])
            ctx.beginPath()
            ctx.arc(px, py, er, 0, Math.PI * 2)
            ctx.fill()
            ctx.stroke()
          }
        }

        // Reset dash and alpha
        if (isAuto) {
          ctx.setLineDash([])
          ctx.globalAlpha = 1.0
        }
      }
    }

    // Hover delete indicator: draw × on hovered annotation
    const hIdx = hoveredIdxRef.current
    if (hIdx >= 0 && hIdx < anns.length) {
      const ha = anns[hIdx]
      const cx = (ha.x1 + ha.x2) / 2
      const cy = (ha.y1 + ha.y2) / 2
      const r = 8 / v.scale
      // Red circle background
      ctx.fillStyle = 'rgba(220, 40, 40, 0.9)'
      ctx.beginPath()
      ctx.arc(cx, cy, r, 0, Math.PI * 2)
      ctx.fill()
      // White × cross
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 1.5 / v.scale
      ctx.setLineDash([])
      const d = r * 0.5
      ctx.beginPath()
      ctx.moveTo(cx - d, cy - d)
      ctx.lineTo(cx + d, cy + d)
      ctx.moveTo(cx + d, cy - d)
      ctx.lineTo(cx - d, cy + d)
      ctx.stroke()
    }

    // Snap indicator
    const sn = snapRef.current
    if (sn.snapped) {
      ctx.strokeStyle = '#44aaff'
      ctx.fillStyle = 'rgba(68, 170, 255, 0.3)'
      ctx.lineWidth = 1.5 / v.scale
      ctx.setLineDash([])
      ctx.beginPath()
      ctx.arc(sn.x, sn.y, 6 / v.scale, 0, Math.PI * 2)
      ctx.fill()
      ctx.stroke()
    }

    // Live preview overlay while dragging
    const sp = startPtRef.current
    const cp = cursorPtRef.current
    if (drawingRef.current && sp && cp) {
      const currentTool = toolRef.current
      ctx.setTransform(v.scale, 0, 0, v.scale, v.offsetX, v.offsetY)

      if (currentTool === 'eraser') {
        const rx1 = Math.min(sp.x, cp.x)
        const ry1 = Math.min(sp.y, cp.y)
        const rw = Math.abs(cp.x - sp.x)
        const rh = Math.abs(cp.y - sp.y)
        ctx.strokeStyle = '#ff4444'
        ctx.lineWidth = 1 / v.scale
        ctx.setLineDash([4 / v.scale, 4 / v.scale])
        ctx.strokeRect(rx1, ry1, rw, rh)
        ctx.fillStyle = 'rgba(255, 0, 0, 0.1)'
        ctx.fillRect(rx1, ry1, rw, rh)
        ctx.setLineDash([])
      } else {
        // Preview line with semi-transparency
        ctx.strokeStyle = COLORS[currentTool]
        ctx.lineWidth = (currentTool === 'wall' ? 6 : 4) / v.scale
        ctx.globalAlpha = 0.6
        ctx.beginPath()
        ctx.moveTo(sp.x, sp.y)
        ctx.lineTo(cp.x, cp.y)
        ctx.stroke()
        ctx.globalAlpha = 1.0

        // Endpoint dots
        const dotR = 3 / v.scale
        ctx.fillStyle = COLORS[currentTool]
        ctx.beginPath()
        ctx.arc(sp.x, sp.y, dotR, 0, Math.PI * 2)
        ctx.fill()
        ctx.beginPath()
        ctx.arc(cp.x, cp.y, dotR, 0, Math.PI * 2)
        ctx.fill()

        // Length label in pixels
        const lenPx = Math.round(Math.sqrt((cp.x - sp.x) ** 2 + (cp.y - sp.y) ** 2))
        ctx.fillStyle = '#ffffff'
        ctx.font = `bold ${11 / v.scale}px monospace`
        ctx.fillText(`${lenPx}px`, (sp.x + cp.x) / 2 + 6 / v.scale, (sp.y + cp.y) / 2 - 6 / v.scale)
      }
    }
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
    const ep = hitTestEndpoint(ptDown.x, ptDown.y)
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
    const pt = snapToEndpoint(ptRaw.x, ptRaw.y)
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
        const pt = snapToEndpoint(ptRaw.x, ptRaw.y, idx)
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
      const snapped = snapToEndpoint(ptRaw.x, ptRaw.y)
      snapRef.current = snapped
      cursorPtRef.current = snapped
      scheduleRender()
      return
    }

    // Not drawing → hit-test for hover delete + door swing tooltip + endpoint resize
    const pt = screenToWorld(e.clientX, e.clientY)
    const epHover = hitTestEndpoint(pt.x, pt.y)
    const prev = hoveredIdxRef.current
    hoveredIdxRef.current = hitTestAnnotation(pt.x, pt.y)
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
    const pt = snapToEndpoint(ptRaw.x, ptRaw.y)
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

function DownloadButton({ href }: { href: string }) {
  const [name, setName] = useState('')

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="File name..."
          className="flex-1 px-3 py-2 sm:py-1.5 bg-white/[0.04] border border-zinc-800/60 rounded-md
                     text-sm text-zinc-300 placeholder:text-zinc-600 outline-none
                     focus:border-zinc-700 transition-colors"
        />
        <a href={href} download={name.trim() ? `${name.trim()}.dxf` : 'floorplan.dxf'}
          className="inline-flex items-center justify-center gap-2
                     px-4 py-2.5 sm:py-2
                     bg-white/[0.04] border border-zinc-800/60 rounded-md
                     text-sm text-zinc-400
                     hover:bg-white/[0.08] hover:text-zinc-300
                     active:bg-white/[0.12]
                     transition-colors duration-200">
          <DownloadIcon />
          .dxf
        </a>
      </div>
    </div>
  )
}

function UploadIcon({ size = 14, className = '' }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  )
}

function DownloadIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  )
}
