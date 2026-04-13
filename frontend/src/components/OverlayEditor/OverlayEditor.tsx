import { memo, useState } from 'react'
import type { Annotation } from '../../types'
import { useOverlayEditorState } from './useOverlayEditorState'
import { useCanvasInteractions } from './useCanvasInteractions'
import { OverlayToolbar } from './OverlayToolbar'
import { OverlayCanvas } from './OverlayCanvas'
import type { PendingDoor, PendingLabel } from './types'

export default memo(function OverlayEditor({ previewUrl, regionOverlay, annotations, setAnnotations }: {
  previewUrl: string
  regionOverlay?: string
  annotations: Annotation[]
  setAnnotations: (a: Annotation[]) => void
}) {
  const state = useOverlayEditorState(previewUrl, regionOverlay, annotations)

  const [pendingDoor, setPendingDoor] = useState<PendingDoor | null>(null)
  const [pendingLabel, setPendingLabel] = useState<PendingLabel | null>(null)
  const [labelName, setLabelName] = useState('')
  const [labelSqft, setLabelSqft] = useState('')

  const interactions = useCanvasInteractions(
    state, annotations, setAnnotations,
    pendingDoor, setPendingDoor,
    setPendingLabel, setLabelName, setLabelSqft,
  )

  const clearLabels = () => setAnnotations(annotations.filter(a => a.type !== 'label'))

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
        editingDoorIdxRef={state.editingDoorIdxRef}
        onPointerDown={interactions.handlePointerDown}
        onPointerMove={interactions.handlePointerMove}
        onPointerUp={interactions.handlePointerUp}
        onPointerLeave={interactions.handlePointerLeave}
        addDoorWithSwing={interactions.addDoorWithSwing}
        mirrorDoor={interactions.mirrorDoor}
      />
    </div>
  )
})
