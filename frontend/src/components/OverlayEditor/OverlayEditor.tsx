import { memo, useState, useRef, useCallback, useEffect } from 'react'
import type { AnnotationType, SwingDir, Annotation } from '../../types'
import { DoorSwingPicker } from '../DoorSwingPicker'
import { hitTestAnnotation, hitTestEndpoint, snapToEndpoint } from './geometry'
import { renderCanvas as renderCanvasFn } from './renderCanvas'
import { ROOM_PALETTE } from './constants'
import { getStroke } from 'perfect-freehand'

export default memo(function OverlayEditor({ previewUrl, regionOverlay, annotations, setAnnotations }: {
  previewUrl: string
  regionOverlay?: string
  annotations: Annotation[]
  setAnnotations: (a: Annotation[]) => void
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [tool, setTool] = useState<AnnotationType>('wall')
  const [fullscreen, setFullscreen] = useState(false)
  const [eraserSize, setEraserSize] = useState(10)

  // Paint tool state
  const [paintBrushSize, setPaintBrushSize] = useState(15)
  const [selectedRoomIdx, setSelectedRoomIdx] = useState<number>(-1)
  const [paintMode, setPaintMode] = useState<'brush' | 'separator'>('brush')
  const regionCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const paintingRef = useRef(false)
  const separatorStartRef = useRef<{ x: number; y: number } | null>(null)
  const paintModeRef = useRef<'brush' | 'separator'>('brush')

  // Refs that mirror state for use in mousemove (avoids stale closures)
  const drawingRef = useRef(false)
  const startPtRef = useRef<{ x: number; y: number } | null>(null)
  const cursorPtRef = useRef<{ x: number; y: number } | null>(null)
  const toolRef = useRef<AnnotationType>(tool)
  const annotationsRef = useRef(annotations)
  const rafId = useRef<number>(0)
  const hoveredIdxRef = useRef<number>(-1)
  const selectedRoomIdxRef = useRef<number>(-1)
  const paintBrushSizeRef = useRef(paintBrushSize)
  // Drag-resize: which annotation endpoint is being dragged
  const draggingRef = useRef<{ idx: number; endpoint: 'start' | 'end' | 'arc' } | null>(null)

  // Keep refs in sync with state
  useEffect(() => { toolRef.current = tool }, [tool])
  useEffect(() => { annotationsRef.current = annotations }, [annotations])
  useEffect(() => { selectedRoomIdxRef.current = selectedRoomIdx }, [selectedRoomIdx])
  useEffect(() => { paintBrushSizeRef.current = paintBrushSize }, [paintBrushSize])
  useEffect(() => { paintModeRef.current = paintMode }, [paintMode])

  // Pan + Zoom state
  const [view, setView] = useState({ offsetX: 0, offsetY: 0, scale: 1 })
  const viewRef = useRef(view)
  useEffect(() => { viewRef.current = view }, [view])
  const isPanning = useRef(false)
  const panStart = useRef({ x: 0, y: 0 })
  const spaceDown = useRef(false)
  const imgRef = useRef<HTMLImageElement | null>(null)
  const overlayImgRef = useRef<HTMLImageElement | null>(null)

  const snapRef = useRef<{ x: number; y: number; snapped: boolean }>({ x: 0, y: 0, snapped: false })

  // Geometry wrappers — delegate to pure functions, pass refs explicitly
  const _hitTest = (wx: number, wy: number) => hitTestAnnotation(wx, wy, annotationsRef.current, viewRef.current.scale)
  const _hitEndpoint = (wx: number, wy: number) => hitTestEndpoint(wx, wy, annotationsRef.current, viewRef.current.scale)
  const _snap = (wx: number, wy: number, skipIdx = -1) => snapToEndpoint(wx, wy, annotationsRef.current, viewRef.current.scale, skipIdx)

  // Collected points during a paint stroke
  const paintPointsRef = useRef<[number, number][]>([])
  const paintEraseRef = useRef(false)

  // Convert getStroke outline points to a Path2D
  const strokeToPath = useCallback((points: number[][]) => {
    if (points.length < 2) return null
    const path = new Path2D()
    path.moveTo(points[0][0], points[0][1])
    for (let i = 1; i < points.length - 1; i++) {
      const xc = (points[i][0] + points[i + 1][0]) / 2
      const yc = (points[i][1] + points[i + 1][1]) / 2
      path.quadraticCurveTo(points[i][0], points[i][1], xc, yc)
    }
    path.closePath()
    return path
  }, [])

  // Commit a stroke to the region offscreen canvas
  const commitStroke = useCallback((pts: [number, number][], erase: boolean) => {
    const rc = regionCanvasRef.current
    if (!rc || pts.length < 2) return
    const octx = rc.getContext('2d')!
    const outline = getStroke(pts, {
      size: paintBrushSizeRef.current * 2,
      thinning: 0,
      smoothing: 0.5,
      streamline: 0.5,
    })
    const path = strokeToPath(outline)
    if (!path) return

    if (erase) {
      octx.globalCompositeOperation = 'destination-out'
      octx.fillStyle = 'rgba(0,0,0,1)'
      octx.fill(path)
      octx.globalCompositeOperation = 'source-over'
    } else {
      const idx = selectedRoomIdxRef.current
      if (idx < 0) return
      const [r, g, b] = ROOM_PALETTE[idx % ROOM_PALETTE.length]
      // Clear existing color first to avoid alpha stacking
      octx.globalCompositeOperation = 'destination-out'
      octx.fillStyle = 'rgba(0,0,0,1)'
      octx.fill(path)
      octx.globalCompositeOperation = 'source-over'
      // Paint with exact room color (alpha 100/255 matches backend)
      octx.fillStyle = `rgba(${r},${g},${b},${100 / 255})`
      octx.fill(path)
    }
  }, [strokeToPath])

  // Find which label index is closest to a world point
  const findLabelAtWorld = useCallback((wx: number, wy: number): number => {
    const labels = annotationsRef.current.filter(a => a.type === 'label')
    let bestDist = 30 // max click distance in world px
    let bestIdx = -1
    for (let i = 0; i < labels.length; i++) {
      const dx = labels[i].x1 - wx
      const dy = labels[i].y1 - wy
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist < bestDist) { bestDist = dist; bestIdx = i }
    }
    return bestIdx
  }, [])

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

  // Load region overlay into editable offscreen canvas
  useEffect(() => {
    if (!regionOverlay) { regionCanvasRef.current = null; overlayImgRef.current = null; return }
    const img = new Image()
    img.onload = () => {
      overlayImgRef.current = img
      const offscreen = document.createElement('canvas')
      offscreen.width = img.width
      offscreen.height = img.height
      const octx = offscreen.getContext('2d')!
      octx.drawImage(img, 0, 0)
      regionCanvasRef.current = offscreen
    }
    img.src = `data:image/png;base64,${regionOverlay}`
  }, [regionOverlay])

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
      regionCanvasRef.current ?? overlayImgRef.current,
    )
  }, [])  // stable — reads everything from refs

  // Schedule a render via requestAnimationFrame (debounced)
  const scheduleRender = useCallback(() => {
    cancelAnimationFrame(rafId.current)
    rafId.current = requestAnimationFrame(() => renderCanvas())
  }, [renderCanvas])

  // React-triggered redraws when state changes
  useEffect(() => { scheduleRender() }, [view, annotations, regionOverlay, scheduleRender])

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
    // Delete hovered annotation (works in ALL tools including paint)
    if (hoveredIdxRef.current >= 0) {
      const idx = hoveredIdxRef.current
      const ha = annotationsRef.current[idx]
      if (ha) {
        const cx = (ha.x1 + ha.x2) / 2
        const cy = (ha.y1 + ha.y2) / 2
        const pt = screenToWorld(e.clientX, e.clientY)
        const hitRadius = 10 / viewRef.current.scale
        const dist = Math.sqrt((pt.x - cx) ** 2 + (pt.y - cy) ** 2)
        if (dist <= hitRadius) {
          setAnnotations(annotations.filter((_, i) => i !== idx))
          hoveredIdxRef.current = -1
          scheduleRender()
          return
        }
      }
    }
    // Paint tool
    if (toolRef.current === 'paint') {
      const pt = screenToWorld(e.clientX, e.clientY)
      // Click on a label → select its color (works in both modes)
      const labelIdx = findLabelAtWorld(pt.x, pt.y)
      if (labelIdx >= 0) {
        setSelectedRoomIdx(labelIdx)
        selectedRoomIdxRef.current = labelIdx
        scheduleRender()
        return
      }
      if (paintModeRef.current === 'separator') {
        // Separator: snap start, then drag → release end
        const snapped = _snap(pt.x, pt.y)
        separatorStartRef.current = { x: snapped.x, y: snapped.y }
        paintingRef.current = true
        drawingRef.current = true
        startPtRef.current = { x: snapped.x, y: snapped.y }
        cursorPtRef.current = { x: snapped.x, y: snapped.y }
        snapRef.current = snapped
        return
      }

      if (!regionCanvasRef.current) return

      // Brush mode: start painting (right-click = erase)
      if (selectedRoomIdxRef.current >= 0 || e.button === 2) {
        paintingRef.current = true
        paintEraseRef.current = e.button === 2
        paintPointsRef.current = [[pt.x, pt.y]]
        scheduleRender()
      }
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

    // Paint tool drag
    if (paintingRef.current && toolRef.current === 'paint') {
      const pt = screenToWorld(e.clientX, e.clientY)
      if (paintModeRef.current === 'separator') {
        // Update preview line with snap
        const snapped = _snap(pt.x, pt.y)
        cursorPtRef.current = { x: snapped.x, y: snapped.y }
        snapRef.current = snapped
        scheduleRender()
        return
      }
      // Brush mode — collect points, commit incrementally
      paintPointsRef.current.push([pt.x, pt.y])
      if (paintPointsRef.current.length > 3) {
        commitStroke(paintPointsRef.current, paintEraseRef.current)
        paintPointsRef.current = paintPointsRef.current.slice(-2)
      }
      scheduleRender()
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
  const [pendingLabel, setPendingLabel] = useState<{ x: number; y: number; sx: number; sy: number } | null>(null)
  const [labelName, setLabelName] = useState('')
  const [labelSqft, setLabelSqft] = useState('')

  const handleMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (isPanning.current) { isPanning.current = false; return }
    if (paintingRef.current) {
      if (paintModeRef.current === 'separator' && separatorStartRef.current) {
        const ptRaw = screenToWorld(e.clientX, e.clientY)
        const pt = _snap(ptRaw.x, ptRaw.y)
        const sp = separatorStartRef.current
        const dx = Math.abs(pt.x - sp.x)
        const dy = Math.abs(pt.y - sp.y)
        if (dx > 3 || dy > 3) {
          const ann: Annotation = {
            type: 'separator' as any,
            x1: sp.x, y1: sp.y,
            x2: pt.x, y2: pt.y,
          }
          setAnnotations([...annotationsRef.current, ann])
        }
        separatorStartRef.current = null
        drawingRef.current = false
        cursorPtRef.current = null
        startPtRef.current = null
      } else {
        // Commit remaining brush points
        if (paintPointsRef.current.length > 1) {
          commitStroke(paintPointsRef.current, paintEraseRef.current)
        }
        paintPointsRef.current = []
      }
      paintingRef.current = false
      scheduleRender()
      return
    }
    if (draggingRef.current) { draggingRef.current = null; return }
    if (!drawingRef.current || !startPtRef.current) return
    const ptRaw = screenToWorld(e.clientX, e.clientY)
    const pt = _snap(ptRaw.x, ptRaw.y)
    snapRef.current = { x: 0, y: 0, snapped: false }
    const sp = startPtRef.current

    // Clear drawing state (both state and refs)
    drawingRef.current = false
    cursorPtRef.current = null

    const dx = Math.abs(pt.x - sp.x)
    const dy = Math.abs(pt.y - sp.y)

    // Label tool: single click places a label
    if (tool === 'label') {
      const rect = canvasRef.current!.getBoundingClientRect()
      const sx = e.clientX - rect.left
      const sy = e.clientY - rect.top
      setPendingLabel({ x: sp.x, y: sp.y, sx, sy })
      setLabelName('')
      setLabelSqft('')
      startPtRef.current = null
      scheduleRender()
      return
    }

    if (dx < 5 && dy < 5) { startPtRef.current = null; scheduleRender(); return }

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
    { type: 'label', label: 'Label', color: 'bg-zinc-800/60 border-zinc-600/50 text-zinc-200' },
    { type: 'eraser', label: 'Eraser', color: 'bg-zinc-700/40 border-zinc-500/50 text-zinc-300' },
    { type: 'paint', label: 'Paint', color: 'bg-purple-900/40 border-purple-700/50 text-purple-400' },
  ]

  const clearLabels = () => {
    setAnnotations(annotations.filter(a => a.type !== 'label'))
  }
  const labelCount = annotations.filter(a => a.type === 'label').length

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
            {tool === 'label' && labelCount > 0 && (
              <button
                onClick={clearLabels}
                className="px-2 py-1 ml-1 rounded text-[10px] font-medium text-red-400 bg-red-900/30 border border-red-800/40
                           hover:bg-red-800/40 cursor-pointer transition-colors"
              >
                Clear Labels ({labelCount})
              </button>
            )}
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
            {tool === 'paint' && (
              <div className="flex items-center gap-1.5 ml-1">
                {/* Brush / Separator toggle */}
                <div className="flex items-center gap-0">
                  <button
                    onClick={() => setPaintMode('brush')}
                    className={`px-1.5 py-0.5 rounded-l text-[9px] font-medium border cursor-pointer transition-colors
                      ${paintMode === 'brush' ? 'bg-purple-800/60 text-purple-200 border-purple-600/60' : 'bg-zinc-900/40 text-zinc-500 border-zinc-800/40 hover:text-zinc-400'}`}
                  >Brush</button>
                  <button
                    onClick={() => setPaintMode('separator')}
                    className={`px-1.5 py-0.5 rounded-r text-[9px] font-medium border border-l-0 cursor-pointer transition-colors
                      ${paintMode === 'separator' ? 'bg-white/20 text-white border-zinc-500/60' : 'bg-zinc-900/40 text-zinc-500 border-zinc-800/40 hover:text-zinc-400'}`}
                  >Line</button>
                </div>
                <div className="w-px h-3 bg-zinc-700 mx-0.5" />
                {paintMode === 'brush' && selectedRoomIdx >= 0 ? (
                  <>
                    <div
                      className="w-3 h-3 rounded-full border border-white/30"
                      style={{ backgroundColor: `rgb(${ROOM_PALETTE[selectedRoomIdx % ROOM_PALETTE.length].join(',')})` }}
                    />
                    <span className="text-[9px] text-zinc-400">
                      {annotations.filter(a => a.type === 'label')[selectedRoomIdx]?.roomName ?? 'Room'}
                    </span>
                  </>
                ) : paintMode === 'brush' ? (
                  <span className="text-[9px] text-zinc-500">Click a label</span>
                ) : (
                  <span className="text-[9px] text-zinc-500">Click → drag → release</span>
                )}
                {paintMode === 'brush' && (
                  <>
                    <span className="text-[9px] text-zinc-600 ml-1">Size</span>
                    <input
                      type="range" min="3" max="50" value={paintBrushSize}
                      onChange={(e) => setPaintBrushSize(Number(e.target.value))}
                      className="w-14 h-1 accent-purple-500"
                    />
                    <span className="text-[9px] text-zinc-500 w-4">{paintBrushSize}</span>
                    <span className="text-[9px] text-zinc-600 ml-1">RMB=erase</span>
                  </>
                )}
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
          onMouseLeave={() => { drawingRef.current = false; paintingRef.current = false; startPtRef.current = null; cursorPtRef.current = null; isPanning.current = false; hoveredIdxRef.current = -1; draggingRef.current = null; scheduleRender() }}
          onContextMenu={(e) => { if (tool === 'paint') e.preventDefault() }}
          className="absolute inset-0 w-full h-full"
          style={{ cursor: spaceDown.current || isPanning.current ? 'grab' : tool === 'paint' ? (selectedRoomIdx >= 0 ? 'crosshair' : 'pointer') : 'crosshair' }}
        />
        {/* Label popup — room name + sqft */}
        {pendingLabel && (
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
                if (e.key === 'Enter' && labelName.trim()) {
                  const ann: Annotation = {
                    type: 'label',
                    x1: pendingLabel.x, y1: pendingLabel.y,
                    x2: pendingLabel.x, y2: pendingLabel.y,
                    roomName: labelName.trim().toUpperCase(),
                    sqft: labelSqft ? Number(labelSqft) : undefined,
                  }
                  setAnnotations([...annotations, ann])
                  setPendingLabel(null)
                }
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
                if (e.key === 'Enter' && labelName.trim()) {
                  const ann: Annotation = {
                    type: 'label',
                    x1: pendingLabel.x, y1: pendingLabel.y,
                    x2: pendingLabel.x, y2: pendingLabel.y,
                    roomName: labelName.trim().toUpperCase(),
                    sqft: labelSqft ? Number(labelSqft) : undefined,
                  }
                  setAnnotations([...annotations, ann])
                  setPendingLabel(null)
                }
                if (e.key === 'Escape') setPendingLabel(null)
              }}
              className="w-48 px-2 py-1 text-[11px] bg-zinc-100 border border-zinc-300 rounded text-zinc-900 mb-2 outline-none focus:border-zinc-500"
            />
            <div className="flex gap-1.5">
              <button
                onClick={() => {
                  if (!labelName.trim()) return
                  const ann: Annotation = {
                    type: 'label',
                    x1: pendingLabel.x, y1: pendingLabel.y,
                    x2: pendingLabel.x, y2: pendingLabel.y,
                    roomName: labelName.trim().toUpperCase(),
                    sqft: labelSqft ? Number(labelSqft) : undefined,
                  }
                  setAnnotations([...annotations, ann])
                  setPendingLabel(null)
                }}
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
        )}
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
})

