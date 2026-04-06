import type React from 'react'
import type { Annotation } from '../../types'
import { DoorSwingPicker } from '../DoorSwingPicker'
import { RoomLabelDialog } from './RoomLabelDialog'
import type { PendingDoor, PendingLabel } from './types'
import type { SwingDir } from '../../types'

interface OverlayCanvasProps {
  canvasRef: React.RefObject<HTMLCanvasElement | null>
  containerRef: React.RefObject<HTMLDivElement | null>
  fullscreen: boolean
  tool: string
  selectedRoomIdx: number
  spaceDown: React.MutableRefObject<boolean>
  isPanning: React.MutableRefObject<boolean>
  pendingDoor: PendingDoor | null
  setPendingDoor: (d: PendingDoor | null) => void
  pendingLabel: PendingLabel | null
  setPendingLabel: (l: PendingLabel | null) => void
  labelName: string
  setLabelName: (s: string) => void
  labelSqft: string
  setLabelSqft: (s: string) => void
  annotations: Annotation[]
  setAnnotations: (a: Annotation[]) => void
  editingDoorIdxRef: React.MutableRefObject<number>
  onMouseDown: (e: React.MouseEvent<HTMLCanvasElement>) => void
  onMouseMove: (e: React.MouseEvent<HTMLCanvasElement>) => void
  onMouseUp: (e: React.MouseEvent<HTMLCanvasElement>) => void
  onMouseLeave: () => void
  addDoorWithSwing: (dir: SwingDir) => void
  mirrorDoor: () => void
}

export function OverlayCanvas({
  canvasRef, containerRef, fullscreen, tool, selectedRoomIdx,
  spaceDown, isPanning,
  pendingDoor, setPendingDoor,
  pendingLabel, setPendingLabel,
  labelName, setLabelName, labelSqft, setLabelSqft,
  annotations, setAnnotations,
  editingDoorIdxRef,
  onMouseDown, onMouseMove, onMouseUp, onMouseLeave,
  addDoorWithSwing, mirrorDoor,
}: OverlayCanvasProps) {
  return (
    <div ref={containerRef} className={`relative ${fullscreen ? 'flex-1 overflow-hidden' : 'h-64'}`}>
      <canvas
        ref={canvasRef}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseLeave}
        onContextMenu={(e) => { if (tool === 'paint') e.preventDefault() }}
        className="absolute inset-0 w-full h-full"
        style={{ cursor: spaceDown.current || isPanning.current ? 'grab' : tool === 'paint' ? (selectedRoomIdx >= 0 ? 'crosshair' : 'pointer') : 'crosshair' }}
      />
      {pendingLabel && (
        <RoomLabelDialog
          pendingLabel={pendingLabel}
          labelName={labelName}
          setLabelName={setLabelName}
          labelSqft={labelSqft}
          setLabelSqft={setLabelSqft}
          annotations={annotations}
          setAnnotations={setAnnotations}
          setPendingLabel={setPendingLabel}
        />
      )}
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
  )
}
