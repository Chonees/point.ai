import { lazy, Suspense, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { OpeningAnnotation, V2Result } from '../../types'
import type { PlanScene } from '../projects/project.types'
import { DownloadButton } from '../../components/DownloadButton'
import { apiUrl } from '../../lib/api'
import { OpeningsReviewCanvas } from './OpeningsReviewCanvas'
import { Spinner } from '../../components/Spinner'

const ENABLE_3D = false

const FloorPlan3D = lazy(() => import('../../components/FloorPlan3D'))

interface WorkspaceOutputProps {
  result: V2Result
  sourceImage?: string | null
  initialScene?: PlanScene
  onSceneChange?: (scene: PlanScene) => void
  openingAnnotations?: OpeningAnnotation[]
  onOpeningAnnotationsChange?: (annotations: OpeningAnnotation[]) => void
  onRegenerate?: () => void
  isRegenerating?: boolean
}

export function WorkspaceOutput({
  result,
  sourceImage,
  initialScene,
  onSceneChange,
  openingAnnotations = [],
  onOpeningAnnotationsChange,
  onRegenerate,
  isRegenerating = false,
}: WorkspaceOutputProps) {
  const [view3D, setView3D] = useState(false)
  const [showDetails, setShowDetails] = useState(false)

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      className="overflow-hidden rounded-[28px] border border-white/6 bg-zinc-950/80 shadow-[0_0_0_1px_rgba(255,255,255,0.02)]"
    >
      <div className="border-b border-white/6 px-5 py-4 sm:px-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-zinc-600">Workspace output</p>
            <h3 className="mt-2 text-xl font-semibold tracking-tight text-zinc-100">Preview and export</h3>
          </div>
          <div className="flex items-center gap-3">
            {result.preview_url && (
              <div className="inline-flex items-center rounded-2xl border border-white/8 bg-white/[0.03] p-1">
                <button
                  onClick={() => setView3D(false)}
                  className={`rounded-xl px-3 py-2 text-xs font-medium transition-colors ${
                    !view3D ? 'bg-white/[0.08] text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
                  }`}
                >
                  2D Preview
                </button>
                {ENABLE_3D ? (
                  <button
                    onClick={() => setView3D(true)}
                    className={`rounded-xl px-3 py-2 text-xs font-medium transition-colors ${
                      view3D ? 'bg-white/[0.08] text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
                    }`}
                  >
                    3D Preview
                  </button>
                ) : (
                  <span className="flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-medium text-zinc-600 cursor-default" title="In development — coming soon">
                    3D Preview
                    <span className="rounded-full bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-400/80">Soon</span>
                  </span>
                )}
              </div>
            )}
            {result.dxf_url ? (
              <DownloadButton href={result.dxf_url} />
            ) : (
              <span className="text-xs text-zinc-500">Generate to unlock DXF download</span>
            )}
          </div>
        </div>
      </div>

      <div className="p-5 sm:p-6">
        {result.preview_url && (
          <Suspense fallback={<div className="h-64 animate-pulse rounded-[24px] bg-zinc-950" />}>
            {ENABLE_3D && view3D ? (
              <FloorPlan3D
                structure={result.structure}
                initialScene={initialScene}
                onSceneChange={onSceneChange}
              />
            ) : (
              <div className="overflow-hidden rounded-[24px] border border-white/6 bg-zinc-950">
                <img
                  src={apiUrl(result.preview_url)}
                  alt="Generated floor plan preview"
                  className="max-h-[640px] w-full object-contain"
                />
              </div>
            )}
          </Suspense>
        )}

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <button
            onClick={() => setShowDetails(!showDetails)}
            className="rounded-2xl border border-white/8 px-4 py-2 text-xs text-zinc-400 transition-colors hover:border-white/14 hover:text-zinc-200"
          >
            {showDetails ? 'Hide' : 'Show'} raw structure
          </button>
          <p className="text-xs text-zinc-500">
            {result.dxf_url ? 'DXF ready for download.' : 'Generate DXF to export the current workspace.'}
          </p>
        </div>

        {sourceImage && onOpeningAnnotationsChange && (
          <div className="mt-5 space-y-3">
            <OpeningsReviewCanvas
              imageSrc={sourceImage}
              annotations={openingAnnotations}
              onChange={onOpeningAnnotationsChange}
            />

            {onRegenerate && (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-[20px] border border-white/6 bg-white/[0.02] px-4 py-3">
                <p className="text-xs leading-5 text-zinc-500">
                  Cuando termines de mover o borrar openings, regenerá el DXF para aplicar la sesión actual.
                </p>
                <button
                  type="button"
                  onClick={onRegenerate}
                  disabled={isRegenerating}
                  className="rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-2 text-xs font-medium text-zinc-200 transition-all duration-200 hover:bg-white/[0.1] disabled:cursor-not-allowed disabled:opacity-30"
                >
                  {isRegenerating
                    ? <span className="flex items-center gap-2"><Spinner />Regenerating…</span>
                    : 'Regenerate DXF with openings'}
                </button>
              </div>
            )}
          </div>
        )}

        <AnimatePresence>
          {showDetails && (
            <motion.pre
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="mt-4 max-h-80 overflow-auto rounded-2xl border border-white/6 bg-[#0b0b0b] p-4 font-mono text-[11px] leading-relaxed text-zinc-500"
            >
              {JSON.stringify(result.structure, null, 2)}
            </motion.pre>
          )}
        </AnimatePresence>
      </div>
    </motion.section>
  )
}
