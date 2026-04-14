import { lazy, Suspense, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { V2Result, Annotation, Visibility } from '../../types'
import type { PlanScene } from '../projects/project.types'
import { DownloadButton } from '../../components/DownloadButton'
import { apiUrl } from '../../lib/api'

const ENABLE_3D = false

const OverlayEditor = lazy(() => import('../../components/OverlayEditor'))
const FloorPlan3D = lazy(() => import('../../components/FloorPlan3D'))

interface WorkspaceOutputProps {
  result: V2Result
  annotations: Annotation[]
  setAnnotations: (annotations: Annotation[]) => void
  visibility: Visibility
  onVisibilityChange: (v: Visibility) => void
  initialScene?: PlanScene
  onSceneChange?: (scene: PlanScene) => void
}

export function WorkspaceOutput({
  result,
  annotations,
  setAnnotations,
  visibility,
  onVisibilityChange,
  initialScene,
  onSceneChange,
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
            <h3 className="mt-2 text-xl font-semibold tracking-tight text-zinc-100">Preview, annotate and export</h3>
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
                  2D Edit
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
                annotations={annotations}
                initialScene={initialScene}
                onSceneChange={onSceneChange}
              />
            ) : (
              <OverlayEditor
                previewUrl={apiUrl(result.preview_url)}
                regionOverlay={result.region_overlay}
                annotations={annotations}
                setAnnotations={setAnnotations}
                initialVisibility={visibility}
                onVisibilityChange={onVisibilityChange}
                scaleIpp={result.scale_ipp}
              />
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
