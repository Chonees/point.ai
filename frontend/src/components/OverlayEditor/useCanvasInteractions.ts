import { useRef } from 'react'
import type React from 'react'
import type { Annotation, SwingDir } from '../../types'
import { hitTestAnnotation, hitTestEndpoint, snapToEndpoint } from './geometry'
import type { PendingDoor, PendingLabel, EditingLabel } from './types'
import type { useOverlayEditorState } from './useOverlayEditorState'
import { newAnnotationId } from '../../utils/annotationId'
import { inchesToFeetInches } from '../../utils/architecturalFormat'

type EditorState = ReturnType<typeof useOverlayEditorState>

export interface EditingDimensionRef {
  idx: number
  sx: number
  sy: number
  valueText: string
  locked: boolean
}

export function useCanvasInteractions(
  state: EditorState,
  annotations: Annotation[],
  setAnnotations: (a: Annotation[]) => void,
  pendingDoor: PendingDoor | null,
  setPendingDoor: (d: PendingDoor | null) => void,
  setPendingLabel: (l: PendingLabel | null) => void,
  setLabelName: (s: string) => void,
  setLabelSqft: (s: string) => void,
  setEditingLabel: (e: EditingLabel | null) => void,
  scaleIpp: number,
  setEditingDimension: (e: EditingDimensionRef | null) => void,
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
    longPressIdxRef,
    longPressActiveRef,
    setSelectedRoomIdx,
    setView,
    commitStroke,
    findLabelAtWorld,
    screenToWorld,
    scheduleRender,
  } = state

  const longPressTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const longPressStartRef = useRef<{ x: number; y: number } | null>(null)
  const labelDragStartRef = useRef<{ clientX: number; clientY: number; moved: boolean } | null>(null)
  /**
   * Start snapshot for a dimension body drag (offset change). We record
   * the cursor position and the original offsetPx so the pointer-move
   * delta translates 1:1 into offset adjustment, and so a pointerUp with
   * no movement opens the edit dialog instead of committing an offset.
   */
  const dimDragStartRef = useRef<{
    clientX: number
    clientY: number
    startOffset: number
    startOutward: 1 | -1
    orientation: 'H' | 'V'
    moved: boolean
  } | null>(null)

  const cancelLongPress = () => {
    if (longPressTimerRef.current) {
      clearTimeout(longPressTimerRef.current)
      longPressTimerRef.current = null
    }
    longPressStartRef.current = null
    if (longPressActiveRef.current) {
      longPressActiveRef.current = false
      longPressIdxRef.current = -1
      scheduleRender()
    }
  }

  const _hitTest = (wx: number, wy: number) => hitTestAnnotation(wx, wy, annotationsRef.current, viewRef.current.scale)
  const _hitEndpoint = (wx: number, wy: number) => hitTestEndpoint(wx, wy, annotationsRef.current, viewRef.current.scale)
  const _snap = (wx: number, wy: number, skipIdx = -1) => snapToEndpoint(wx, wy, annotationsRef.current, viewRef.current.scale, skipIdx)

  const handlePointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    cancelLongPress()
    if (e.button === 1 || (e.button === 0 && spaceDown.current)) {
      e.preventDefault()
      isPanning.current = true
      panStart.current = { x: e.clientX - viewRef.current.offsetX, y: e.clientY - viewRef.current.offsetY }
      return
    }
    // Start long-press timer for delete (works in any tool)
    if (e.button === 0) {
      const ptLP = screenToWorld(e.clientX, e.clientY)
      const hitIdx = _hitTest(ptLP.x, ptLP.y)
      if (hitIdx >= 0) {
        longPressStartRef.current = { x: e.clientX, y: e.clientY }
        longPressTimerRef.current = setTimeout(() => {
          longPressIdxRef.current = hitIdx
          longPressActiveRef.current = true
          if (navigator.vibrate) navigator.vibrate(30)
          scheduleRender()
        }, 400)
      }
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
        // Labels: start move drag (click without drag → edit dialog on pointerUp)
        if (ha.type === 'label') {
          draggingRef.current = { idx, endpoint: 'move' }
          labelDragStartRef.current = { clientX: e.clientX, clientY: e.clientY, moved: false }
          return
        }
        // Dimensions: start a body drag (changes offsetPx). If pointerUp
        // arrives without movement, we open the edit dialog instead.
        if (ha.type === 'dimension') {
          draggingRef.current = { idx, endpoint: 'move' }
          dimDragStartRef.current = {
            clientX: e.clientX,
            clientY: e.clientY,
            startOffset: ha.offsetPx ?? 40,
            startOutward: ha.outward ?? 1,
            orientation: ha.orientation ?? 'H',
            moved: false,
          }
          return
        }
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
    // Cancel long-press if pointer moves significantly
    if (longPressStartRef.current) {
      const dx = e.clientX - longPressStartRef.current.x
      const dy = e.clientY - longPressStartRef.current.y
      if (dx * dx + dy * dy > 64) cancelLongPress()
    }
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
      // Track if the label drag actually moved (for click-vs-drag)
      if (labelDragStartRef.current) {
        const ddx = e.clientX - labelDragStartRef.current.clientX
        const ddy = e.clientY - labelDragStartRef.current.clientY
        if (ddx * ddx + ddy * ddy > 9) labelDragStartRef.current.moved = true
      }
      // Track dimension body drag movement (click-vs-drag for dialog).
      if (dimDragStartRef.current) {
        const ddx = e.clientX - dimDragStartRef.current.clientX
        const ddy = e.clientY - dimDragStartRef.current.clientY
        if (ddx * ddx + ddy * ddy > 9) dimDragStartRef.current.moved = true
      }
      setAnnotations(annotations.map((a, i) => {
        if (i !== idx) return a
        // Dimension body drag → adjust offsetPx (and flip outward when the
        // user pulls past the wall axis). The cota line follows the cursor.
        if (endpoint === 'move' && a.type === 'dimension') {
          const orientation = a.orientation ?? 'H'
          if (orientation === 'H') {
            const wallY = (a.y1 + a.y2) / 2
            const deltaY = ptRaw.y - wallY
            // outward in image-space (image y grows down) flips: positive
            // cursor delta means the cota goes BELOW the wall → outward=-1
            // in DXF convention (which negates again at render time).
            const newOutward: 1 | -1 = deltaY < 0 ? 1 : -1
            const newOffset = Math.max(8, Math.abs(deltaY))
            return { ...a, offsetPx: newOffset, outward: newOutward }
          } else {
            const wallX = (a.x1 + a.x2) / 2
            const deltaX = ptRaw.x - wallX
            // For V dims, outward=1 means cota goes to the right in DXF
            // space (positive x). Image space doesn't flip X, so signs match.
            const newOutward: 1 | -1 = deltaX > 0 ? 1 : -1
            const newOffset = Math.max(8, Math.abs(deltaX))
            return { ...a, offsetPx: newOffset, outward: newOutward }
          }
        }
        // Dimension endpoint drag → reposition start/end of the span freely.
        // The user grabs the DIM LINE endpoint (with offset), so we subtract
        // the offset to get the underlying span position. Detach from walls
        // so the recompute pass leaves it where the user put it.
        if ((endpoint === 'start' || endpoint === 'end') && a.type === 'dimension') {
          const ori = a.orientation ?? 'H'
          const offOut = a.outward ?? 1
          const offPx = a.offsetPx ?? 40
          // Remove the visual offset so the cursor maps to the SPAN, not the dim line
          const snapX = ori === 'V' ? ptRaw.x - offOut * offPx : ptRaw.x
          const snapY = ori === 'H' ? ptRaw.y + offOut * offPx : ptRaw.y
          const updated: Partial<typeof a> = { wallIds: [] }
          if (endpoint === 'start') {
            updated.x1 = snapX
            updated.y1 = snapY
          } else {
            updated.x2 = snapX
            updated.y2 = snapY
          }
          // Recompute orientation from new geometry (could have become diagonal)
          const nx1 = updated.x1 ?? a.x1, ny1 = updated.y1 ?? a.y1
          const nx2 = updated.x2 ?? a.x2, ny2 = updated.y2 ?? a.y2
          updated.orientation = Math.abs(nx2 - nx1) >= Math.abs(ny2 - ny1) ? 'H' : 'V'
          return { ...a, ...updated }
        }
        // Label move: update all coords to cursor position (labels are points)
        if (endpoint === 'move' && a.type === 'label') {
          return { ...a, x1: ptRaw.x, y1: ptRaw.y, x2: ptRaw.x, y2: ptRaw.y }
        }
        // Label resize: distance from label center → scale factor
        if (endpoint === 'resize' && a.type === 'label') {
          const name = a.roomName || 'ROOM'
          const sqft = a.sqft ? `${a.sqft} SQ FT` : ''
          const baseW = Math.max(name.length, sqft.length) * 32 * 0.6 + 24
          const baseH = (sqft ? 32 + 22 + 12 : 32) + 24
          const baseDiag = Math.sqrt(baseW * baseW + baseH * baseH) / 2
          const curDiag = Math.sqrt((ptRaw.x - a.x1) ** 2 + (ptRaw.y - a.y1) ** 2)
          const newScale = Math.max(0.3, Math.min(5, curDiag / baseDiag))
          return { ...a, labelScale: newScale }
        }
        // Label rotate: angle from center to cursor; handle starts at top (−PI/2 unrotated)
        if (endpoint === 'rotate' && a.type === 'label') {
          const angle = Math.atan2(ptRaw.y - a.y1, ptRaw.x - a.x1)
          // Handle is at top-center (pointing "up" in local space = angle −PI/2).
          // Align that rest position to rotation 0.
          return { ...a, labelRotation: angle + Math.PI / 2 }
        }
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
    // Long-press delete: if active, delete and bail
    if (longPressActiveRef.current) {
      const idx = longPressIdxRef.current
      if (idx >= 0 && idx < annotations.length) {
        setAnnotations(annotations.filter((_, i) => i !== idx))
      }
      longPressActiveRef.current = false
      longPressIdxRef.current = -1
      hoveredIdxRef.current = -1
      cancelLongPress()
      scheduleRender()
      return
    }
    cancelLongPress()
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
            id: newAnnotationId(),
            type: 'separator',
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
    if (draggingRef.current) {
      // If the user clicked on a label without dragging, open the edit dialog
      const dr = draggingRef.current
      if (dr.endpoint === 'move' && labelDragStartRef.current && !labelDragStartRef.current.moved) {
        const ann = annotationsRef.current[dr.idx]
        if (ann && ann.type === 'label') {
          const rect = canvasRef.current!.getBoundingClientRect()
          const sx = e.clientX - rect.left
          const sy = e.clientY - rect.top
          setEditingLabel({
            idx: dr.idx,
            name: ann.roomName || '',
            sqft: ann.sqft != null ? String(ann.sqft) : '',
            sx, sy,
          })
        }
      }
      // Same click-vs-drag semantics for dimensions: a click without movement
      // opens the edit dialog; a drag commits the new offset/outward.
      if (dr.endpoint === 'move' && dimDragStartRef.current && !dimDragStartRef.current.moved) {
        const ann = annotationsRef.current[dr.idx]
        if (ann && ann.type === 'dimension') {
          const rect = canvasRef.current!.getBoundingClientRect()
          const sx = e.clientX - rect.left
          const sy = e.clientY - rect.top
          setEditingDimension({
            idx: dr.idx,
            sx, sy,
            valueText: ann.valueText ?? '',
            locked: !!ann.locked,
          })
        }
      }
      labelDragStartRef.current = null
      dimDragStartRef.current = null
      draggingRef.current = null
      return
    }
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
    } else if (tool === 'measure') {
      // Measure tool → create a dimension annotation. User can draw
      // diagonals freely, just like walls. Orientation is inferred from
      // the dominant axis for rendering decisions (ext line direction).
      const isH = Math.abs(pt.x - sp.x) >= Math.abs(pt.y - sp.y)
      const x1 = sp.x
      const y1 = sp.y
      const x2 = pt.x
      const y2 = pt.y
      const spanPx = Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

      // Compute outward from plan centroid so the cota sits on the outside
      // of the building (matches auto-generated exterior dims).
      const walls = annotationsRef.current.filter((a) => a.type === 'wall')
      let cx = 0, cy = 0
      if (walls.length > 0) {
        for (const w of walls) {
          cx += (w.x1 + w.x2) / 2
          cy += (w.y1 + w.y2) / 2
        }
        cx /= walls.length
        cy /= walls.length
      } else {
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
      }
      const wallCoord = isH ? (y1 + y2) / 2 : (x1 + x2) / 2
      const outward: 1 | -1 = isH
        ? (wallCoord > cy ? -1 : 1)
        : (wallCoord > cx ? 1 : -1)

      const valueInches = spanPx * (scaleIpp || 0)
      const valueText = scaleIpp && scaleIpp > 0
        ? inchesToFeetInches(valueInches)
        : `${Math.round(spanPx)} px`

      const dim: Annotation = {
        id: newAnnotationId(),
        type: 'dimension',
        subtype: 'exterior',
        orientation: isH ? 'H' : 'V',
        outward,
        offsetPx: 30,
        x1, y1, x2, y2,
        valueInches,
        valueText,
        wallIds: [],
      }
      setAnnotations([...annotations, dim])
    } else {
      setAnnotations([...annotations, {
        id: newAnnotationId(),
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
      setAnnotations([...annotations, { id: newAnnotationId(), type: 'door', ...pendingDoor, swing: dir }])
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
    cancelLongPress()
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
