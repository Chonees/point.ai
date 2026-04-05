import { useState, useRef, useCallback, useEffect, lazy, Suspense } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { Status, AnnotationType, SwingDir, Annotation, V2Result } from '../types'
import type { PlanData, PlanScene } from '../hooks/useProject'
import { fileToBase64 } from '../utils/fileToBase64'
import { Spinner } from './Spinner'
import { UploadIcon } from './UploadIcon'
import { DownloadButton } from './DownloadButton'

const OverlayEditor = lazy(() => import('./OverlayEditor'))
const FloorPlan3D = lazy(() => import('./FloorPlan3D'))

interface UploadPanelProps {
  project?: PlanData | null
  onSceneChange?: (scene: PlanScene) => void
  onStructureChange?: (structure: Record<string, unknown>) => void
  onSaveNow?: (updates: { structure?: Record<string, unknown>; scene?: PlanScene; imageData?: string }) => void
}

export function UploadPanel({ project, onSceneChange, onStructureChange, onSaveNow }: UploadPanelProps = {}) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [status, setStatus] = useState<Status>('idle')
  const [statusMsg, setStatusMsg] = useState('')
  const [result, setResult] = useState<V2Result | null>(null)
  const [showDetails, setShowDetails] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [annotations, setAnnotations] = useState<Annotation[]>([])
  const [autoLoaded, setAutoLoaded] = useState(false)
  const [view3D, setView3D] = useState(false)
  const [totalSqft, setTotalSqft] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  // Load project state when project changes
  useEffect(() => {
    if (!project) return
    if (project.scene.annotations2d.length > 0) {
      setAnnotations(project.scene.annotations2d)
      setAutoLoaded(true)
    }
    // Restore saved image
    if (project.imageData) {
      setPreview(project.imageData)
    }
    if (project.structure) {
      const savedPreview = (project.structure as any)._preview_data ?? null
      setResult({
        dxf_url: '',
        preview_url: savedPreview,
        structure: project.structure,
        quality_metrics: {},
        review_flags: [],
        needs_review: false,
        scale_status: 'loaded',
      })
      setStatus('done')
    }
  }, [project?.id])

  // Notify parent when annotations change (for auto-save)
  const notifySceneChange = useCallback((newAnnotations: Annotation[]) => {
    if (!onSceneChange || !project) return
    onSceneChange({
      annotations2d: newAnnotations,
      placedItems3d: project.scene.placedItems3d,
      floorMaterial: project.scene.floorMaterial,
      wallMaterial: project.scene.wallMaterial,
    })
  }, [onSceneChange, project])

  const handleFile = useCallback((f: File) => {
    setFile(f)
    setResult(null)
    setStatus('idle')
    setStatusMsg('')
    setAnnotations([])
    setAutoLoaded(false)
    // Create preview + save image to DB as base64
    const reader = new FileReader()
    reader.onload = () => {
      const dataUrl = reader.result as string
      setPreview(dataUrl)
      if (onSaveNow) onSaveNow({ imageData: dataUrl })
    }
    reader.readAsDataURL(f)
  }, [onSaveNow])

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
    if (!file && !preview) { setStatus('error'); setStatusMsg('Upload a floor plan image first.'); return }
    setStatus('loading'); setStatusMsg('Processing floor plan...'); setResult(null)

    try {
      // Use file if available, otherwise use saved base64 preview
      const imageBase64 = file ? await fileToBase64(file) : preview!.replace(/^data:image\/\w+;base64,/, '')
      const body: Record<string, unknown> = { image: imageBase64, model_variant: 'ensemble' }
      if (totalSqft) body.total_sqft = Number(totalSqft)
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
      // Fetch the preview image and convert to base64 for persistence
      if (data.preview_url) {
        try {
          const previewRes = await fetch(data.preview_url)
          const blob = await previewRes.blob()
          const reader = new FileReader()
          const previewDataUrl = await new Promise<string>((resolve) => {
            reader.onload = () => resolve(reader.result as string)
            reader.readAsDataURL(blob)
          })
          data.structure = { ...data.structure, _preview_data: previewDataUrl }
        } catch { /* preview fetch failed, continue without */ }
      }
      setResult(data); setStatus('done'); setStatusMsg('')
      if (onStructureChange) onStructureChange(data.structure)

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

      // Merge computed sqft into existing label annotations
      if (data.computed_rooms?.length) {
        setAnnotations(prev => prev.map(ann => {
          if (ann.type !== 'label' || !ann.roomName) return ann
          const match = data.computed_rooms!.find(
            r => r.roomName === ann.roomName!.toUpperCase()
              && Math.abs(r.x1 - ann.x1) < 5 && Math.abs(r.y1 - ann.y1) < 5
          )
          return match ? { ...ann, sqft: match.sqft } : ann
        }))
      }
    } catch (e) {
      setStatus('error')
      setStatusMsg(e instanceof Error ? e.message : 'Unknown error')
    }
  }, [file, preview, annotations, autoLoaded, totalSqft])

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

      {/* Total sq ft input */}
      <div className="mt-3">
        <input
          type="number"
          placeholder="Total SQ FT (e.g. 2000)"
          value={totalSqft}
          onChange={e => setTotalSqft(e.target.value)}
          className="w-full px-3 py-2.5 sm:py-2 rounded-lg text-sm
                     bg-zinc-950 border border-zinc-800/60 text-zinc-300
                     placeholder:text-zinc-600 outline-none
                     focus:border-zinc-600 transition-colors"
        />
        <p className="text-[10px] text-zinc-600 mt-1 ml-1">
          {totalSqft ? `Scale from ${totalSqft} sq ft` : 'Optional — enables precise measurements'}
        </p>
      </div>

      {/* Generate button */}
      <motion.button
        whileTap={{ scale: 0.98 }}
        onClick={generate}
        disabled={status === 'loading' || (!file && !preview)}
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

            {/* 2D/3D toggle */}
            {result.preview_url && (
              <div className="flex items-center gap-1 mb-1">
                <button
                  onClick={() => setView3D(false)}
                  className={`px-3 py-1 rounded-l-md text-[10px] font-medium border cursor-pointer transition-colors
                    ${!view3D ? 'bg-zinc-700/60 text-zinc-200 border-zinc-600/60' : 'bg-zinc-900/40 text-zinc-500 border-zinc-800/40 hover:text-zinc-400'}`}
                >
                  2D Edit
                </button>
                <button
                  onClick={() => setView3D(true)}
                  className={`px-3 py-1 rounded-r-md text-[10px] font-medium border cursor-pointer transition-colors
                    ${view3D ? 'bg-zinc-700/60 text-zinc-200 border-zinc-600/60' : 'bg-zinc-900/40 text-zinc-500 border-zinc-800/40 hover:text-zinc-400'}`}
                >
                  3D Preview
                </button>
              </div>
            )}

            {/* Editor / 3D view */}
            {result.preview_url && (
              <Suspense fallback={<div className="h-64 bg-zinc-950 animate-pulse rounded-lg" />}>
                {view3D ? (
                  <FloorPlan3D
                    structure={result.structure}
                    annotations={annotations}
                    initialScene={project?.scene}
                    onSceneChange={onSceneChange}
                  />
                ) : (
                  <OverlayEditor
                    previewUrl={result.preview_url}
                    regionOverlay={result.region_overlay}
                    annotations={annotations}
                    setAnnotations={(a) => {
                      const next = typeof a === 'function' ? a(annotations) : a
                      setAnnotations(next)
                      notifySceneChange(next)
                    }}
                  />
                )}
              </Suspense>
            )}

            {/* Download — only show when a real DXF was generated */}
            {result.dxf_url ? (
              <DownloadButton href={result.dxf_url} />
            ) : (
              <p className="text-[10px] text-zinc-600 text-center">
                Hit "Generate DXF" to create a downloadable file
              </p>
            )}


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
