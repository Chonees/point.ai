import type React from 'react'
import type { Annotation, SwingDir } from '../../types'
import { hitTestAnnotation, hitTestEndpoint, snapToEndpoint } from './geometry'
import type { PendingDoor, PendingLabel } from './types'
import type { useOverlayEditorState } from './useOverlayEditorState'

type EditorState = ReturnType<typeof useOverlayEditorState>

export function useCanvasInteractions(
  state: EditorState,
  annotations: Annotation[],
  setAnnotations: (a: Annotation[]) => void,
  pendingDoor: PendingDoor | null,
  setPendingDoor: (d: PendingDoor | null) => void,
  setPendingLabel: (l: PendingLabel | null) => void,
  setLabelName: (s: string) => void,
  setLabelSqft: (s: string) => void,
) {
  const {
    canvasRef,
    tool,
    viewRef,
    annotationsRef,
    drawingRef,
    startPtRef,
    cursorPtRef,
    hoveredIdxRef,
    snapRef,
    isPanning,
    panStart,
    spaceDown,
    paintingRef,
    paintModeRef,
    separatorStartRef,
    regionCanvasRef,
    selectedRoomIdxRef,
    paintEraseRef,
    paintPointsRef,
    draggingRef,
    editingDoorIdxRef,
    setSelectedRoomIdx,
    setView,
    commitStroke,
    findLabelAtWorld,
    screenToWorld,
    scheduleRender,
  } = state

  const _hitTest = (wx: number, wy: number) => hitTestAnnotation(wx, wy, annotationsRef.current, viewRef.current.scale)
  const _hitEndpoint = (wx: number, wy: number) => hitTestEndpoint(wx, wy, annotationsRef.current, viewRef.current.scale)
  const _snap = (wx: number, wy: number, skipIdx = -1) => snapToEndpoint(wx, wy, annotationsRef.current, viewRef.current.scale, skipIdx)

  const handlePointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (e.button === 1 || (e.button === 0 && spaceDown.current)) {
      e.preventDefault()
      isPanning.current = true
      panStart.current = { x: e.clientX - viewRef.current.offsetX, y: e.clientY - viewRef.current.offsetY }
      return
    }
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
    if (state.toolRef.current === 'paint') {
      const pt = screenToWorld(e.clientX, e.clientY)
      const labelIdx = findLabelAtWorld(pt.x, pt.y)
      if (labelIdx >= 0) {
        setSelectedRoomIdx(labelIdx)
        selectedRoomIdxRef.current = labelIdx
        scheduleRender()
        return
      }
      if (paintModeRef.current === 'separator') {
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

      if (selectedRoomIdxRef.current >= 0 || e.button === 2) {
        paintingRef.current = true
        paintEraseRef.current = e.button === 2
        paintPointsRef.current = [[pt.x, pt.y]]
        scheduleRender()
      }
      return
    }
    const ptDown = screenToWorld(e.clientX, e.clientY)
    const activeTool = state.toolRef.current
    const isSelectTool = activeTool === 'select'
    if (isSelectTool) {
      const ep = _hitEndpoint(ptDown.x, ptDown.y)
      if (ep) {
        draggingRef.current = ep
        return
      }
    }
    if (isSelectTool && hoveredIdxRef.current >= 0) {
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
          setPendingDoor(null)
          scheduleRender()
          return
        }
        if (ha.type === 'wall') {
          // Toggle wall thickness: 4 → 6 → 4
          const newThickness = ha.thickness === 6 ? 4 : 6
          setAnnotations(annotations.map((a, i) => i === idx ? { ...a, thickness: newThickness } : a))
          scheduleRender()
          return
        }
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
    if (isSelectTool) return
    const ptRaw = screenToWorld(e.clientX, e.clientY)
    const pt = _snap(ptRaw.x, ptRaw.y)
    snapRef.current = pt
    drawingRef.current = true
    startPtRef.current = pt
    cursorPtRef.current = pt
  }

  const handlePointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (isPanning.current) {
      setView(v => ({
        ...v,
        offsetX: e.clientX - panStart.current.x,
        offsetY: e.clientY - panStart.current.y,
      }))
      return
    }

    if (paintingRef.current && state.toolRef.current === 'paint') {
      const pt = screenToWorld(e.clientX, e.clientY)
      if (paintModeRef.current === 'separator') {
        const snapped = _snap(pt.x, pt.y)
        cursorPtRef.current = { x: snapped.x, y: snapped.y }
        snapRef.current = snapped
        scheduleRender()
        return
      }
      paintPointsRef.current.push([pt.x, pt.y])
      if (paintPointsRef.current.length > 3) {
        commitStroke(paintPointsRef.current, paintEraseRef.current)
        paintPointsRef.current = paintPointsRef.current.slice(-2)
      }
      scheduleRender()
      return
    }

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

    const pt = screenToWorld(e.clientX, e.clientY)
    const epHover = _hitEndpoint(pt.x, pt.y)
    const prev = hoveredIdxRef.current
    hoveredIdxRef.current = _hitTest(pt.x, pt.y)
    if (hoveredIdxRef.current !== prev || epHover) {
      const c = canvasRef.current
      const defaultCursor = state.toolRef.current === 'select' ? 'default' : 'crosshair'
      if (c) c.style.cursor = epHover ? 'grab' : hoveredIdxRef.current >= 0 ? 'pointer' : defaultCursor
      scheduleRender()
    }
  }

  const handlePointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
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

    drawingRef.current = false
    cursorPtRef.current = null

    const dx = Math.abs(pt.x - sp.x)
    const dy = Math.abs(pt.y - sp.y)

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

    if (tool === 'door') {
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
      setAnnotations(annotations.map((a, i) => i === editIdx ? { ...a, swing: dir } : a))
    } else {
      setAnnotations([...annotations, { type: 'door', ...pendingDoor, swing: dir }])
    }
    editingDoorIdxRef.current = -1
    setPendingDoor(null)
  }

  const mirrorDoor = () => {
    const idx = editingDoorIdxRef.current
    if (idx < 0) return
    setAnnotations(annotations.map((a, i) => {
      if (i !== idx) return a
      return { ...a, x1: a.x2, y1: a.y2, x2: a.x1, y2: a.y1 }
    }))
    setPendingDoor(pendingDoor ? { ...pendingDoor, x1: pendingDoor.x2, y1: pendingDoor.y2, x2: pendingDoor.x1, y2: pendingDoor.y1 } : null)
  }

  const undo = () => {
    if (annotations.length > 0) setAnnotations(annotations.slice(0, -1))
  }

  const handlePointerLeave = () => {
    drawingRef.current = false
    paintingRef.current = false
    startPtRef.current = null
    cursorPtRef.current = null
    isPanning.current = false
    hoveredIdxRef.current = -1
    draggingRef.current = null
    scheduleRender()
  }

  return { handlePointerDown, handlePointerMove, handlePointerUp, handlePointerLeave, addDoorWithSwing, mirrorDoor, undo }
}
