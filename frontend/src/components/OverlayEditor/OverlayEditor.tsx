import { memo, useEffect, useRef, useState } from 'react'
import type { Annotation, Visibility } from '../../types'
import { useOverlayEditorState } from './useOverlayEditorState'
import { useCanvasInteractions } from './useCanvasInteractions'
import type { EditingDimensionRef } from './useCanvasInteractions'
import { OverlayToolbar } from './OverlayToolbar'
import { OverlayCanvas } from './OverlayCanvas'
import type { PendingDoor, PendingLabel, EditingLabel } from './types'
import { recomputeDimensionsFor } from '../../utils/dimensionRecompute'
import { DimensionEditDialog } from './DimensionEditDialog'
import { inchesToFeetInches, parseArchitectural } from '../../utils/architecturalFormat'

export default memo(function OverlayEditor({
  previewUrl, regionOverlay, annotations, setAnnotations,
  initialVisibility, onVisibilityChange, scaleIpp,
}: {
  previewUrl: string
  regionOverlay?: string
  annotations: Annotation[]
  setAnnotations: (a: Annotation[]) => void
  initialVisibility?: Visibility
  onVisibilityChange?: (v: Visibility) => void
  scaleIpp?: number
}) {
  const state = useOverlayEditorState(previewUrl, regionOverlay, annotations, initialVisibility)

  // Notify parent when visibility changes (but not on initial mount)
  const mounted = useRef(false)
  useEffect(() => {
    if (!mounted.current) { mounted.current = true; return }
    onVisibilityChange?.(state.visibility)
  }, [state.visibility, onVisibilityChange])

  const [pendingDoor, setPendingDoor] = useState<PendingDoor | null>(null)
  const [pendingLabel, setPendingLabel] = useState<PendingLabel | null>(null)
  const [labelName, setLabelName] = useState('')
  const [labelSqft, setLabelSqft] = useState('')
  const [editingLabel, setEditingLabel] = useState<EditingLabel | null>(null)
  const [editingDimension, setEditingDimension] = useState<EditingDimensionRef | null>(null)

  // Scale override: lets the user recalibrate the plan by editing any
  // dimension's value (e.g. typing 10'-0" on a wall the user knows is 10 ft).
  // When set, takes precedence over `scaleIpp` from the backend response.
  // Reset whenever the backend ships a new authoritative scale.
  const [scaleOverride, setScaleOverride] = useState<number | null>(null)
  const lastPropScaleRef = useRef<number | undefined>(scaleIpp)
  useEffect(() => {
    if (scaleIpp !== lastPropScaleRef.current) {
      lastPropScaleRef.current = scaleIpp
      setScaleOverride(null)
    }
  }, [scaleIpp])
  const effectiveScale = scaleOverride ?? scaleIpp ?? 0

  // Dynamic dimension recompute: when a wall's geometry or the effective
  // scale changes, every dim anchored to a wall updates value+span at once.
  // Locked dims preserve their user-edited valueText (only position adapts).
  const wallSig = annotations
    .filter((a) => a.type === 'wall')
    .map((w) => `${w.id}:${w.x1},${w.y1},${w.x2},${w.y2}`)
    .join('|')
  useEffect(() => {
    if (!effectiveScale || effectiveScale <= 0) return
    if (!annotations.some((a) => a.type === 'dimension')) return
    const next = recomputeDimensionsFor(annotations, effectiveScale)
    let changed = false
    for (let i = 0; i < next.length; i++) {
      if (next[i] !== annotations[i]) { changed = true; break }
    }
    if (changed) setAnnotations(next)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wallSig, effectiveScale])

  const interactions = useCanvasInteractions(
    state, annotations, setAnnotations,
    pendingDoor, setPendingDoor,
    setPendingLabel, setLabelName, setLabelSqft,
    setEditingLabel,
    effectiveScale,
    setEditingDimension,
  )

  const clearLabels = () => setAnnotations(annotations.filter(a => a.type !== 'label'))

  /**
   * Commit a dimension edit. If the user typed a parseable value that
   * differs from the current one, recalibrate the whole plan: compute a
   * new scale_ipp from this cota's pixel span vs. the new inch value,
   * push it as the override, and let the recompute effect propagate it
   * to every other cota. Free-floating measures (no wallIds) stay locked
   * to the new value so they don't flip back on the next recompute.
   */
  const handleDimensionSave = (
    idx: number,
    newValueText: string,
    locked: boolean,
  ) => {
    const dim = annotations[idx]
    if (!dim || dim.type !== 'dimension') { setEditingDimension(null); return }

    const prevText = dim.valueText ?? ''
    const prevInches = dim.valueInches ?? 0
    const parsed = parseArchitectural(newValueText)

    // Axis-aligned span in pixels; recalibration requires a real length.
    const spanPx = dim.orientation === 'H'
      ? Math.abs(dim.x2 - dim.x1)
      : Math.abs(dim.y2 - dim.y1)

    let next = annotations.map((a, i) => {
      if (i !== idx) return a
      return {
        ...a,
        valueText: newValueText.trim() || a.valueText,
        locked,
      }
    })

    // Recalibrate only if the user typed something parseable that actually
    // changes the measurement (ignore pure relabels like "LIVING 10'-0"").
    const shouldRecalibrate =
      parsed !== null && spanPx > 1 && Math.abs(parsed - prevInches) > 0.5
    if (shouldRecalibrate) {
      const newScale = parsed / spanPx
      setScaleOverride(newScale)
      // Update this dim's value_inches so it's internally consistent.
      next = next.map((a, i) =>
        i === idx ? { ...a, valueInches: parsed, valueText: inchesToFeetInches(parsed) } : a,
      )
      // The recompute effect will reformat every other dim from the new
      // scale on the next tick.
    } else if (parsed === null) {
      // Non-parseable → treat as a cosmetic override and lock to preserve.
      next = next.map((a, i) => (i === idx ? { ...a, locked: true } : a))
    }

    setAnnotations(next)
    setEditingDimension(null)
    void prevText
  }

  const handleDimensionDelete = (idx: number) => {
    setAnnotations(annotations.filter((_, i) => i !== idx))
    setEditingDimension(null)
  }

  return (
    <div className={`rounded-[24px] overflow-hidden border border-white/6 bg-zinc-950/85 transition-all duration-300
      ${state.fullscreen ? 'fixed inset-4 z-50 flex flex-col' : ''}`}>
      <OverlayToolbar
        tool={state.tool}
        setTool={state.setTool}
        fullscreen={state.fullscreen}
        setFullscreen={state.setFullscreen}
        paintBrushSize={state.paintBrushSize}
        setPaintBrushSize={state.setPaintBrushSize}
        paintMode={state.paintMode}
        setPaintMode={state.setPaintMode}
        selectedRoomIdx={state.selectedRoomIdx}
        annotations={annotations}
        visibility={state.visibility}
        setVisibility={state.setVisibility}
        fitImage={state.fitImage}
        undo={interactions.undo}
        onClearLabels={clearLabels}
      />
      <OverlayCanvas
        canvasRef={state.canvasRef}
        containerRef={state.containerRef}
        fullscreen={state.fullscreen}
        tool={state.tool}
        selectedRoomIdx={state.selectedRoomIdx}
        spaceDown={state.spaceDown}
        isPanning={state.isPanning}
        pendingDoor={pendingDoor}
        setPendingDoor={setPendingDoor}
        pendingLabel={pendingLabel}
        setPendingLabel={setPendingLabel}
        labelName={labelName}
        setLabelName={setLabelName}
        labelSqft={labelSqft}
        setLabelSqft={setLabelSqft}
        annotations={annotations}
        setAnnotations={setAnnotations}
        editingLabel={editingLabel}
        setEditingLabel={setEditingLabel}
        editingDoorIdxRef={state.editingDoorIdxRef}
        onPointerDown={interactions.handlePointerDown}
        onPointerMove={interactions.handlePointerMove}
        onPointerUp={interactions.handlePointerUp}
        onPointerLeave={interactions.handlePointerLeave}
        addDoorWithSwing={interactions.addDoorWithSwing}
        mirrorDoor={interactions.mirrorDoor}
      />
      {editingDimension && (
        <DimensionEditDialog
          editing={editingDimension}
          onSave={(valueText, locked) =>
            handleDimensionSave(editingDimension.idx, valueText, locked)
          }
          onDelete={() => handleDimensionDelete(editingDimension.idx)}
          onClose={() => setEditingDimension(null)}
        />
      )}
    </div>
  )
})
