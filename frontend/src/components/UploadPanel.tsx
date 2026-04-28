import { useState, useCallback, useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import type { OpeningAnnotation } from '../types'
import type { PlanData, PlanScene } from '../features/projects'
import { hasPersistedOpeningReview } from '../features/projects/openingReviewPersistence'
import { useGenerateDxf } from '../features/workspace/useGenerateDxf'
import { PlanSourceCard } from '../features/workspace/PlanSourceCard'
import { PlanMetadataCard } from '../features/workspace/PlanMetadataCard'
import { WorkspaceOutput } from '../features/workspace/WorkspaceOutput'
import { filterOpeningAnnotations } from '../features/workspace/openingsReview'

interface UploadPanelProps {
  project?: PlanData | null
  onSceneChange?: (scene: PlanScene) => void
  onStructureChange?: (structure: Record<string, unknown>) => void
  onSaveNow?: (updates: {
    structure?: Record<string, unknown>
    scene?: PlanScene
    imageData?: string
  }) => void
  onOpeningReviewStateChange?: (state: {
    annotations: OpeningAnnotation[]
    reviewSessionActive: boolean
  }) => void
}

export function UploadPanel({
  project,
  onSceneChange,
  onStructureChange,
  onSaveNow,
  onOpeningReviewStateChange,
}: UploadPanelProps = {}) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [reviewedAnnotations, setReviewedAnnotations] = useState<OpeningAnnotation[]>([])
  const [reviewSessionActive, setReviewSessionActive] = useState(false)

  const { status, statusMsg, result, generate } = useGenerateDxf({
    file,
    preview,
    onStructureChange,
    reviewedAnnotations,
    useReviewedAnnotations: reviewSessionActive,
  })

  const hasPlan = Boolean(file || preview)

  useEffect(() => {
    if (!project) return

    setPreview(project.imageData ?? null)
    setReviewedAnnotations(project.reviewedOpeningAnnotations ?? [])
    setReviewSessionActive(
      hasPersistedOpeningReview(project.structure) || (project.reviewedOpeningAnnotations?.length ?? 0) > 0,
    )
  }, [project?.id, project?.imageData, project?.reviewedOpeningAnnotations, project?.structure])

  useEffect(() => {
    if (!result) return
    setReviewedAnnotations(filterOpeningAnnotations(result.auto_annotations))
    setReviewSessionActive(true)
  }, [result])

  useEffect(() => {
    onOpeningReviewStateChange?.({
      annotations: reviewedAnnotations,
      reviewSessionActive,
    })
  }, [onOpeningReviewStateChange, reviewSessionActive, reviewedAnnotations])

  const handleFile = useCallback((uploadedFile: File) => {
    setFile(uploadedFile)
    setReviewedAnnotations([])
    setReviewSessionActive(false)

    const reader = new FileReader()
    reader.onload = () => {
      const dataUrl = reader.result as string
      setPreview(dataUrl)
      onSaveNow?.({ imageData: dataUrl })
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
            sourceImage={preview}
            initialScene={project?.scene}
            onSceneChange={onSceneChange}
            openingAnnotations={reviewedAnnotations}
            onOpeningAnnotationsChange={(annotations) => {
              setReviewedAnnotations(annotations)
              setReviewSessionActive(true)
            }}
            onRegenerate={generate}
            isRegenerating={status === 'loading'}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
