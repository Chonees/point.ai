import { useState, useCallback, useEffect } from 'react'
import { AnimatePresence } from 'framer-motion'
import { motion } from 'framer-motion'
import type { Annotation } from '../types'
import type { PlanData, PlanScene } from '../features/projects'
import { useGenerateDxf } from '../features/workspace/useGenerateDxf'
import { PlanSourceCard } from '../features/workspace/PlanSourceCard'
import { PlanMetadataCard } from '../features/workspace/PlanMetadataCard'
import { WorkspaceOutput } from '../features/workspace/WorkspaceOutput'

interface UploadPanelProps {
  project?: PlanData | null
  onSceneChange?: (scene: PlanScene) => void
  onStructureChange?: (structure: Record<string, unknown>) => void
  onSaveNow?: (updates: { structure?: Record<string, unknown>; scene?: PlanScene; imageData?: string }) => void
}

export function UploadPanel({ project, onSceneChange, onStructureChange, onSaveNow }: UploadPanelProps = {}) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [annotations, setAnnotations] = useState<Annotation[]>([])
  const [autoLoaded, setAutoLoaded] = useState(false)
  const [totalSqft, setTotalSqft] = useState('')
  const [dragging, setDragging] = useState(false)

  const { status, statusMsg, result, generate } = useGenerateDxf({
    file,
    preview,
    annotations,
    autoLoaded,
    totalSqft,
    onStructureChange,
    onAnnotationsUpdate: (updater) => setAnnotations(updater),
    onAutoLoaded: () => setAutoLoaded(true),
  })

  const labelCount = annotations.filter((a) => a.type === 'label').length
  const computedRoomCount = result?.computed_rooms?.length ?? 0
  const hasPlan = Boolean(file || preview)

  useEffect(() => {
    if (!project) return
    if (project.scene.annotations2d.length > 0) {
      setAnnotations(project.scene.annotations2d)
      setAutoLoaded(true)
    }
    if (project.imageData) {
      setPreview(project.imageData)
    }
    if (project.structure) {
      // Restored from saved project — handled by the hook's setResult isn't available here,
      // but useGenerateDxf only manages generation results. For restored state we set result via
      // a different path (the hook doesn't own restoration).
    }
  }, [project?.id])

  const notifySceneChange = useCallback((newAnnotations: Annotation[]) => {
    if (!onSceneChange || !project) return
    onSceneChange({
      annotations2d: newAnnotations,
      placedItems3d: project.scene.placedItems3d,
      floorMaterial: project.scene.floorMaterial,
      wallMaterial: project.scene.wallMaterial,
    })
  }, [onSceneChange, project])

  const handleFile = useCallback((uploadedFile: File) => {
    setFile(uploadedFile)
    setAnnotations([])
    setAutoLoaded(false)

    const reader = new FileReader()
    reader.onload = () => {
      const dataUrl = reader.result as string
      setPreview(dataUrl)
      if (onSaveNow) onSaveNow({ imageData: dataUrl })
    }
    reader.readAsDataURL(uploadedFile)
  }, [onSaveNow])

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-[28px] border border-white/6 bg-zinc-950/80 shadow-[0_0_0_1px_rgba(255,255,255,0.02)]">
        <div className="grid lg:grid-cols-[1.15fr_0.85fr]">
          <PlanSourceCard
            planName={project?.name}
            preview={preview}
            dragging={dragging}
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragging(false)
              const nextFile = e.dataTransfer.files?.[0]
              if (nextFile && nextFile.type.startsWith('image/')) handleFile(nextFile)
            }}
            onFileChange={(e) => {
              const nextFile = e.target.files?.[0]
              if (nextFile) handleFile(nextFile)
            }}
          />
          <PlanMetadataCard
            totalSqft={totalSqft}
            onTotalSqftChange={setTotalSqft}
            labelCount={labelCount}
            computedRoomCount={computedRoomCount}
            status={status}
            hasPlan={hasPlan}
            onGenerate={generate}
          />
        </div>
      </section>

      <AnimatePresence>
        {statusMsg && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className={`rounded-2xl border px-4 py-3 text-sm ${
              status === 'error'
                ? 'border-red-500/20 bg-red-500/8 text-red-300'
                : 'border-white/6 bg-white/[0.02] text-zinc-400'
            }`}
          >
            {statusMsg}
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {result && (
          <WorkspaceOutput
            result={result}
            annotations={annotations}
            setAnnotations={(next) => {
              setAnnotations(next)
              notifySceneChange(next)
            }}
            initialScene={project?.scene}
            onSceneChange={onSceneChange}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
