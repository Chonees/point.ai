import { useState, useRef, useCallback, useEffect } from 'react'
import type { AnnotationType, Annotation } from '../../types'
import { renderCanvas as renderCanvasFn } from './renderCanvas'
import { ROOM_PALETTE } from './constants'
import { getStroke } from 'perfect-freehand'
import type { View, SnapState } from './types'

export function useOverlayEditorState(
  previewUrl: string,
  regionOverlay: string | undefined,
  annotations: Annotation[],
) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [tool, setTool] = useState<AnnotationType>('wall')
  const [fullscreen, setFullscreen] = useState(false)
  const [paintBrushSize, setPaintBrushSize] = useState(15)
  const [selectedRoomIdx, setSelectedRoomIdx] = useState<number>(-1)
  const [paintMode, setPaintMode] = useState<'brush' | 'separator'>('brush')
  const regionCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const paintingRef = useRef(false)
  const separatorStartRef = useRef<{ x: number; y: number } | null>(null)
  const paintModeRef = useRef<'brush' | 'separator'>('brush')

  const drawingRef = useRef(false)
  const startPtRef = useRef<{ x: number; y: number } | null>(null)
  const cursorPtRef = useRef<{ x: number; y: number } | null>(null)
  const toolRef = useRef<AnnotationType>(tool)
  const annotationsRef = useRef(annotations)
  const rafId = useRef<number>(0)
  const hoveredIdxRef = useRef<number>(-1)
  const selectedRoomIdxRef = useRef<number>(-1)
  const paintBrushSizeRef = useRef(paintBrushSize)
  const draggingRef = useRef<{ idx: number; endpoint: 'start' | 'end' | 'arc' } | null>(null)

  useEffect(() => { toolRef.current = tool }, [tool])
  useEffect(() => { annotationsRef.current = annotations }, [annotations])
  useEffect(() => { selectedRoomIdxRef.current = selectedRoomIdx }, [selectedRoomIdx])
  useEffect(() => { paintBrushSizeRef.current = paintBrushSize }, [paintBrushSize])
  useEffect(() => { paintModeRef.current = paintMode }, [paintMode])

  const [view, setView] = useState<View>({ offsetX: 0, offsetY: 0, scale: 1 })
  const viewRef = useRef(view)
  useEffect(() => { viewRef.current = view }, [view])
  const isPanning = useRef(false)
  const panStart = useRef({ x: 0, y: 0 })
  const spaceDown = useRef(false)
  const imgRef = useRef<HTMLImageElement | null>(null)
  const overlayImgRef = useRef<HTMLImageElement | null>(null)

  const snapRef = useRef<SnapState>({ x: 0, y: 0, snapped: false })

  const paintPointsRef = useRef<[number, number][]>([])
  const paintEraseRef = useRef(false)

  const editingDoorIdxRef = useRef<number>(-1)
  const longPressIdxRef = useRef<number>(-1)
  const longPressActiveRef = useRef(false)

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
      octx.globalCompositeOperation = 'destination-out'
      octx.fillStyle = 'rgba(0,0,0,1)'
      octx.fill(path)
      octx.globalCompositeOperation = 'source-over'
      octx.fillStyle = `rgba(${r},${g},${b},${100 / 255})`
      octx.fill(path)
    }
  }, [strokeToPath])

  const findLabelAtWorld = useCallback((wx: number, wy: number): number => {
    const labels = annotationsRef.current.filter(a => a.type === 'label')
    let bestDist = 30
    let bestIdx = -1
    for (let i = 0; i < labels.length; i++) {
      const dx = labels[i].x1 - wx
      const dy = labels[i].y1 - wy
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist < bestDist) { bestDist = dist; bestIdx = i }
    }
    return bestIdx
  }, [])

  const screenToWorld = useCallback((clientX: number, clientY: number) => {
    const canvas = canvasRef.current
    if (!canvas) return { x: 0, y: 0 }
    const rect = canvas.getBoundingClientRect()
    const canvasX = (clientX - rect.left) * (canvas.width / rect.width)
    const canvasY = (clientY - rect.top) * (canvas.height / rect.height)
    return {
      x: Math.round((canvasX - viewRef.current.offsetX) / viewRef.current.scale),
      y: Math.round((canvasY - viewRef.current.offsetY) / viewRef.current.scale),
    }
  }, [])

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

  useEffect(() => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      imgRef.current = img
      fitImage()
    }
    img.src = previewUrl
  }, [previewUrl, fitImage])

  useEffect(() => {
    if (!regionOverlay) { regionCanvasRef.current = null; overlayImgRef.current = null; return }
    const img = new Image()
    img.crossOrigin = 'anonymous'
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

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const ro = new ResizeObserver(() => fitImage())
    ro.observe(container)
    return () => ro.disconnect()
  }, [fitImage])

  const renderCanvas = useCallback(() => {
    const canvas = canvasRef.current
    const img = imgRef.current
    if (!canvas || !img) return
    renderCanvasFn(
      canvas, img, viewRef.current, annotationsRef.current,
      hoveredIdxRef.current, snapRef.current,
      { active: drawingRef.current, start: startPtRef.current, cursor: cursorPtRef.current, tool: toolRef.current },
      regionCanvasRef.current ?? overlayImgRef.current,
      longPressActiveRef.current ? longPressIdxRef.current : -1,
    )
  }, [])

  const scheduleRender = useCallback(() => {
    cancelAnimationFrame(rafId.current)
    rafId.current = requestAnimationFrame(() => renderCanvas())
  }, [renderCanvas])

  useEffect(() => { scheduleRender() }, [view, annotations, regionOverlay, scheduleRender])

  useEffect(() => {
    const onDown = (e: KeyboardEvent) => { if (e.code === 'Space') { e.preventDefault(); spaceDown.current = true } }
    const onUp = (e: KeyboardEvent) => { if (e.code === 'Space') spaceDown.current = false }
    window.addEventListener('keydown', onDown)
    window.addEventListener('keyup', onUp)
    return () => { window.removeEventListener('keydown', onDown); window.removeEventListener('keyup', onUp) }
  }, [])

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

  return {
    canvasRef,
    containerRef,
    tool, setTool,
    fullscreen, setFullscreen,
    paintBrushSize, setPaintBrushSize,
    selectedRoomIdx, setSelectedRoomIdx,
    paintMode, setPaintMode,
    regionCanvasRef,
    paintingRef,
    separatorStartRef,
    paintModeRef,
    drawingRef,
    startPtRef,
    cursorPtRef,
    toolRef,
    annotationsRef,
    hoveredIdxRef,
    selectedRoomIdxRef,
    paintBrushSizeRef,
    draggingRef,
    view, setView,
    viewRef,
    isPanning,
    panStart,
    spaceDown,
    snapRef,
    paintPointsRef,
    paintEraseRef,
    editingDoorIdxRef,
    longPressIdxRef,
    longPressActiveRef,
    commitStroke,
    findLabelAtWorld,
    screenToWorld,
    fitImage,
    scheduleRender,
  }
}
