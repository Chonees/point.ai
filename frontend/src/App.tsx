import { useState, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

// ─── Types ────────────────────────────────────────────────────────────────────

type Mode = 'describe' | 'upload'
type Status = 'idle' | 'loading' | 'done' | 'error'
type ModelVariant = 'baseline' | 'finetuned' | 'segformer'

interface V1Result {
  dxf_url: string
  plan: Record<string, unknown>
}

interface V2Result {
  dxf_url: string
  preview_url: string | null
  structure: Record<string, unknown>
  quality_metrics: Record<string, unknown>
  review_flags: string[]
  needs_review: boolean
  scale_status: string
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

function Spinner() {
  return (
    <motion.span
      animate={{ rotate: 360 }}
      transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
      className="inline-block w-3.5 h-3.5 border border-zinc-600 border-t-zinc-400 rounded-full"
    />
  )
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function App() {
  const [mode, setMode] = useState<Mode>('describe')

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-5 py-16">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="text-center mb-10"
      >
        <h1 className="text-4xl font-light tracking-tight text-white/90">
          Pointe<span className="text-white/30">.ai</span>
        </h1>
        <p className="text-xs tracking-[0.2em] uppercase text-zinc-600 mt-2">
          Floor Plan Generator
        </p>
      </motion.div>

      {/* Mode Toggle */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.1 }}
        className="flex gap-1 p-1 bg-zinc-900 border border-zinc-800/60 rounded-lg mb-8"
      >
        {(['describe', 'upload'] as Mode[]).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`px-5 py-1.5 rounded-md text-xs font-medium transition-all duration-200 cursor-pointer ${
              mode === m
                ? 'bg-white/[0.08] text-zinc-300'
                : 'text-zinc-600 hover:text-zinc-400'
            }`}
          >
            {m === 'describe' ? 'Describe' : 'Upload Plan'}
          </button>
        ))}
      </motion.div>

      {/* Panel */}
      <div className="w-full max-w-[640px]">
        <AnimatePresence mode="wait">
          {mode === 'describe' ? (
            <motion.div
              key="describe"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.2 }}
            >
              <DescribePanel />
            </motion.div>
          ) : (
            <motion.div
              key="upload"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.2 }}
            >
              <UploadPanel />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}

// ─── Describe Panel (v1) ──────────────────────────────────────────────────────

function DescribePanel() {
  const [prompt, setPrompt] = useState('')
  const [fileName, setFileName] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [statusMsg, setStatusMsg] = useState('')
  const [result, setResult] = useState<V1Result | null>(null)
  const [showJson, setShowJson] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const analyzeImage = useCallback(async (file: File) => {
    setAnalyzing(true)
    setStatusMsg('Analyzing image...')
    try {
      const base64 = await fileToBase64(file)
      const res = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image: base64 }),
      })
      if (!res.ok) throw new Error((await res.json()).detail ?? `Error ${res.status}`)
      const data = await res.json()
      setPrompt(data.description)
      setStatusMsg('')
    } catch (e) {
      setStatus('error')
      setStatusMsg(e instanceof Error ? e.message : 'Failed to analyze image')
    } finally {
      setAnalyzing(false)
    }
  }, [])

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) { setFileName(file.name); analyzeImage(file) }
  }, [analyzeImage])

  const generate = useCallback(async () => {
    if (!prompt.trim()) { setStatus('error'); setStatusMsg('Enter a description.'); return }
    setStatus('loading'); setStatusMsg('Generating floor plan...'); setResult(null)

    let imageBase64: string | null = null
    const file = fileRef.current?.files?.[0]
    if (file) imageBase64 = await fileToBase64(file)

    try {
      const res = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: prompt.trim(), image: imageBase64 }),
      })
      if (!res.ok) throw new Error((await res.json()).detail ?? `Error ${res.status}`)
      const data: V1Result = await res.json()
      setResult(data); setStatus('done'); setStatusMsg('')
    } catch (e) {
      setStatus('error')
      setStatusMsg(e instanceof Error ? e.message : 'Unknown error')
    }
  }, [prompt])

  return (
    <>
      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) generate() }}
        placeholder="Describe your floor plan — rooms, dimensions, layout..."
        className="w-full h-36 bg-zinc-950 border border-zinc-800/60 rounded-lg
                   text-zinc-300 text-sm px-4 py-3 resize-none
                   placeholder:text-zinc-700
                   focus:outline-none focus:border-zinc-600
                   transition-colors duration-200"
      />

      <div className="flex items-center gap-3 mt-3">
        <label className="flex items-center gap-2 px-3 py-2 border border-zinc-800/60 rounded-md
                          text-xs text-zinc-600 cursor-pointer
                          hover:border-zinc-600 hover:text-zinc-400 transition-colors duration-200">
          <UploadIcon />
          Upload reference
          <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleFileChange} />
        </label>
        {fileName && (
          <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="text-xs text-zinc-600 flex items-center gap-2">
            {fileName}
            {analyzing && <Spinner />}
          </motion.span>
        )}
      </div>

      <motion.button
        whileTap={{ scale: 0.98 }}
        onClick={generate}
        disabled={status === 'loading' || analyzing}
        className="w-full mt-4 py-3 rounded-lg text-sm font-medium
                   bg-white/[0.06] text-zinc-400 border border-zinc-800/60
                   hover:bg-white/[0.09] hover:text-zinc-300
                   disabled:opacity-30 disabled:cursor-not-allowed
                   transition-all duration-200 cursor-pointer"
      >
        {status === 'loading'
          ? <span className="flex items-center justify-center gap-2"><Spinner />Generating...</span>
          : 'Generate DXF'}
      </motion.button>

      <AnimatePresence>
        {statusMsg && (
          <motion.p initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className={`text-center text-xs mt-4 ${status === 'error' ? 'text-red-500/70' : 'text-zinc-600'}`}>
            {statusMsg}
          </motion.p>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {result && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }} className="mt-6 p-5 border border-zinc-800/60 rounded-lg">
            <DownloadButton href={result.dxf_url} />
            <button onClick={() => setShowJson(!showJson)}
              className="block mt-4 text-xs text-zinc-600 hover:text-zinc-500 transition-colors cursor-pointer">
              {showJson ? 'Hide' : 'Show'} JSON
            </button>
            <AnimatePresence>
              {showJson && (
                <motion.pre initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }}
                  className="mt-3 p-3 bg-zinc-950 border border-zinc-800/40 rounded-md
                             text-[11px] leading-relaxed text-zinc-600 font-mono overflow-auto max-h-80">
                  {JSON.stringify(result.plan, null, 2)}
                </motion.pre>
              )}
            </AnimatePresence>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}

// ─── Upload Panel (v2) ────────────────────────────────────────────────────────

function UploadPanel() {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [scaleHint, setScaleHint] = useState('')
  const [modelVariant, setModelVariant] = useState<ModelVariant>('baseline')
  const [status, setStatus] = useState<Status>('idle')
  const [statusMsg, setStatusMsg] = useState('')
  const [result, setResult] = useState<V2Result | null>(null)
  const [showDetails, setShowDetails] = useState(false)
  const [dragging, setDragging] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFile = useCallback((f: File) => {
    setFile(f)
    setResult(null)
    setStatus('idle')
    setStatusMsg('')
    const url = URL.createObjectURL(f)
    setPreview(url)
  }, [])

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
    if (!file) { setStatus('error'); setStatusMsg('Upload a floor plan image first.'); return }
    setStatus('loading'); setStatusMsg('Processing floor plan...'); setResult(null)

    try {
      const imageBase64 = await fileToBase64(file)
      const body: Record<string, unknown> = { image: imageBase64, model_variant: modelVariant }
      if (scaleHint) {
        const parsed = parseFloat(scaleHint)
        if (!isNaN(parsed) && parsed > 0) body.scale_hint = parsed
      }

      const res = await fetch('/api/v2/generate-dxf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!res.ok) throw new Error((await res.json()).detail ?? `Error ${res.status}`)
      const data: V2Result = await res.json()
      setResult(data); setStatus('done'); setStatusMsg('')
    } catch (e) {
      setStatus('error')
      setStatusMsg(e instanceof Error ? e.message : 'Unknown error')
    }
  }, [file, modelVariant, scaleHint])

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
                      : 'border-zinc-800/60 bg-zinc-950 hover:border-zinc-700'}`}
        style={{ minHeight: preview ? 'auto' : '160px' }}
      >
        <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleFileChange} />

        {preview ? (
          <div className="relative">
            <img src={preview} alt="floor plan" className="w-full object-contain max-h-64 rounded-lg" />
            <div className="absolute inset-0 bg-black/40 opacity-0 hover:opacity-100 transition-opacity
                            flex items-center justify-center rounded-lg">
              <span className="text-xs text-zinc-300">Click to change</span>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-40 gap-3">
            <UploadIcon size={20} className="text-zinc-700" />
            <div className="text-center">
              <p className="text-xs text-zinc-500">Drop a floor plan image here</p>
              <p className="text-xs text-zinc-700 mt-1">PNG, JPG, JPEG</p>
            </div>
          </div>
        )}
      </div>

      {/* Scale hint */}
      <div className="flex items-center gap-3 mt-3">
        <div className="flex items-center gap-2 flex-1">
          <label className="text-xs text-zinc-600 whitespace-nowrap">Scale hint</label>
          <input
            type="number"
            value={scaleHint}
            onChange={(e) => setScaleHint(e.target.value)}
            placeholder="px → inch (e.g. 0.083)"
            step="0.001"
            min="0"
            className="flex-1 bg-zinc-950 border border-zinc-800/60 rounded-md
                       text-xs text-zinc-400 px-3 py-2
                       placeholder:text-zinc-700
                       focus:outline-none focus:border-zinc-600
                       transition-colors duration-200"
          />
        </div>
        <span className="text-xs text-zinc-700">optional</span>
      </div>

      <div className="mt-3">
        <p className="text-xs text-zinc-600 mb-2">Model variant</p>
        <div className="grid grid-cols-3 gap-2">
          {([
            { value: 'baseline'  as const, label: 'Baseline',      note: 'CubiCasa5k original' },
            { value: 'finetuned' as const, label: 'Fine-tuned',     note: 'CubiCasa fine-tuned' },
            { value: 'segformer' as const, label: 'SegFormer',      note: 'Modelo moderno 2021' },
          ]).map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => {
                setModelVariant(option.value)
                setResult(null)
              }}
              className={`p-3 rounded-lg border text-left transition-all duration-200 cursor-pointer ${
                modelVariant === option.value
                  ? 'border-zinc-500 bg-white/[0.05]'
                  : 'border-zinc-800/60 bg-zinc-950 hover:border-zinc-700'
              }`}
            >
              <p className="text-xs text-zinc-300">{option.label}</p>
              <p className="text-[10px] text-zinc-600 mt-1">{option.note}</p>
            </button>
          ))}
        </div>
      </div>

      <motion.button
        whileTap={{ scale: 0.98 }}
        onClick={generate}
        disabled={status === 'loading' || !file}
        className="w-full mt-4 py-3 rounded-lg text-sm font-medium
                   bg-white/[0.06] text-zinc-400 border border-zinc-800/60
                   hover:bg-white/[0.09] hover:text-zinc-300
                   disabled:opacity-30 disabled:cursor-not-allowed
                   transition-all duration-200 cursor-pointer"
      >
        {status === 'loading'
          ? <span className="flex items-center justify-center gap-2"><Spinner />Processing...</span>
          : 'Generate DXF from Image'}
      </motion.button>

      <AnimatePresence>
        {statusMsg && (
          <motion.p initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className={`text-center text-xs mt-4 ${status === 'error' ? 'text-red-500/70' : 'text-zinc-600'}`}>
            {statusMsg}
          </motion.p>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {result && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="mt-6 space-y-4">

            {/* Preview overlay */}
            {result.preview_url && (
              <div className="rounded-lg overflow-hidden border border-zinc-800/60">
                <img
                  src={result.preview_url}
                  alt="structure preview"
                  className="w-full object-contain max-h-64"
                />
                <p className="text-[10px] text-zinc-700 text-center py-1.5">
                  Detected structure overlay
                </p>
              </div>
            )}

            {/* Stats row */}
            <div className="grid grid-cols-3 gap-2">
              <Stat label="Walls" value={String(result.quality_metrics.wall_count ?? '—')} />
              <Stat label="Openings" value={String(result.quality_metrics.opening_count ?? '—')} />
              <Stat
                label="Scale"
                value={result.scale_status === 'calibrated' ? 'Calibrated' : 'Pixel'}
                dim={result.scale_status !== 'calibrated'}
              />
            </div>

            <div className="flex items-center justify-between text-[11px] text-zinc-600 px-1">
              <span>Variant: {String(result.quality_metrics.model_variant ?? modelVariant)}</span>
              <span>Backend: {String(result.quality_metrics.inference_backend ?? '—')}</span>
            </div>

            {/* Review flags */}
            {result.needs_review && result.review_flags.length > 0 && (
              <div className="p-3 bg-amber-950/20 border border-amber-900/30 rounded-lg">
                <p className="text-xs text-amber-600/80 font-medium mb-1.5">Review needed</p>
                <ul className="space-y-1">
                  {result.review_flags.map((flag, i) => (
                    <li key={i} className="text-[11px] text-amber-700/70">• {flag}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Download */}
            <DownloadButton href={result.dxf_url} />

            {/* Details toggle */}
            <button onClick={() => setShowDetails(!showDetails)}
              className="text-xs text-zinc-600 hover:text-zinc-500 transition-colors cursor-pointer">
              {showDetails ? 'Hide' : 'Show'} structure details
            </button>

            <AnimatePresence>
              {showDetails && (
                <motion.pre initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }}
                  className="p-3 bg-zinc-950 border border-zinc-800/40 rounded-md
                             text-[11px] leading-relaxed text-zinc-600 font-mono overflow-auto max-h-80">
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

// ─── Shared components ────────────────────────────────────────────────────────

function Stat({ label, value, dim = false }: { label: string; value: string; dim?: boolean }) {
  return (
    <div className="p-3 bg-zinc-900/50 border border-zinc-800/40 rounded-lg text-center">
      <p className={`text-lg font-light ${dim ? 'text-zinc-600' : 'text-zinc-300'}`}>{value}</p>
      <p className="text-[10px] text-zinc-700 mt-0.5">{label}</p>
    </div>
  )
}

function DownloadButton({ href }: { href: string }) {
  return (
    <a href={href} download
      className="inline-flex items-center gap-2 px-4 py-2.5
                 bg-white/[0.04] border border-zinc-800/60 rounded-md
                 text-sm text-zinc-400
                 hover:bg-white/[0.08] hover:text-zinc-300
                 transition-colors duration-200">
      <DownloadIcon />
      Download DXF
    </a>
  )
}

function UploadIcon({ size = 14, className = '' }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  )
}

function DownloadIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  )
}
