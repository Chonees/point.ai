import { useState, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

type Status = 'idle' | 'loading' | 'done' | 'error'

interface Result {
  dxf_url: string
  plan: Record<string, unknown>
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

export default function App() {
  const [prompt, setPrompt] = useState('')
  const [fileName, setFileName] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [statusMsg, setStatusMsg] = useState('')
  const [result, setResult] = useState<Result | null>(null)
  const [showJson, setShowJson] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const generate = useCallback(async () => {
    if (!prompt.trim()) {
      setStatus('error')
      setStatusMsg('Enter a description.')
      return
    }

    setStatus('loading')
    setStatusMsg('Generating floor plan...')
    setResult(null)
    setShowJson(false)

    let imageBase64: string | null = null
    const file = fileRef.current?.files?.[0]
    if (file) {
      imageBase64 = await fileToBase64(file)
    }

    try {
      const res = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: prompt.trim(), image: imageBase64 }),
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || `Error ${res.status}`)
      }

      const data: Result = await res.json()
      setResult(data)
      setStatus('done')
      setStatusMsg('')
    } catch (e: unknown) {
      setStatus('error')
      setStatusMsg(e instanceof Error ? e.message : 'Unknown error')
    }
  }, [prompt])

  const analyzeImage = useCallback(async (file: File) => {
    setAnalyzing(true)
    setStatusMsg('Analyzing image...')
    setStatus('idle')

    try {
      const base64 = await fileToBase64(file)
      const res = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image: base64 }),
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || `Error ${res.status}`)
      }

      const data = await res.json()
      setPrompt(data.description)
      setStatusMsg('')
    } catch (e: unknown) {
      setStatus('error')
      setStatusMsg(e instanceof Error ? e.message : 'Failed to analyze image')
    } finally {
      setAnalyzing(false)
    }
  }, [])

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setFileName(file.name)
      analyzeImage(file)
    }
  }, [analyzeImage])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      generate()
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-5 py-16">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="text-center mb-12"
      >
        <h1 className="text-4xl font-light tracking-tight text-white/90">
          Pointe<span className="text-white/30">.ai</span>
        </h1>
        <p className="text-xs tracking-[0.2em] uppercase text-zinc-600 mt-2">
          Floor Plan Generator
        </p>
      </motion.div>

      {/* Main Card */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.1 }}
        className="w-full max-w-[640px]"
      >
        {/* Prompt */}
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Describe your floor plan..."
          className="w-full h-36 bg-zinc-950 border border-zinc-800/60 rounded-lg
                     text-zinc-300 text-sm px-4 py-3 resize-none
                     placeholder:text-zinc-700
                     focus:outline-none focus:border-zinc-600
                     transition-colors duration-200"
        />

        {/* Upload Row */}
        <div className="flex items-center gap-3 mt-3">
          <label
            className="flex items-center gap-2 px-3 py-2
                       border border-zinc-800/60 rounded-md
                       text-xs text-zinc-600 cursor-pointer
                       hover:border-zinc-600 hover:text-zinc-400
                       transition-colors duration-200"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            Upload image
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleFileChange}
            />
          </label>
          {fileName && (
            <motion.span
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-xs text-zinc-600 flex items-center gap-2"
            >
              {fileName}
              {analyzing && (
                <motion.span
                  animate={{ rotate: 360 }}
                  transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
                  className="inline-block w-3 h-3 border border-zinc-700 border-t-zinc-400 rounded-full"
                />
              )}
            </motion.span>
          )}
        </div>

        {/* Generate Button */}
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
          {status === 'loading' ? (
            <span className="flex items-center justify-center gap-2">
              <motion.span
                animate={{ rotate: 360 }}
                transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
                className="inline-block w-3.5 h-3.5 border border-zinc-600 border-t-zinc-400 rounded-full"
              />
              Generating...
            </span>
          ) : (
            'Generate'
          )}
        </motion.button>

        {/* Status */}
        <AnimatePresence>
          {statusMsg && (
            <motion.p
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className={`text-center text-xs mt-4 ${
                status === 'error' ? 'text-red-500/70' : 'text-zinc-600'
              }`}
            >
              {statusMsg}
            </motion.p>
          )}
        </AnimatePresence>

        {/* Result */}
        <AnimatePresence>
          {result && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.3 }}
              className="mt-6 p-5 border border-zinc-800/60 rounded-lg"
            >
              <a
                href={result.dxf_url}
                download
                className="inline-flex items-center gap-2 px-4 py-2.5
                           bg-white/[0.04] border border-zinc-800/60 rounded-md
                           text-sm text-zinc-400
                           hover:bg-white/[0.08] hover:text-zinc-300
                           transition-colors duration-200"
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="7 10 12 15 17 10" />
                  <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
                Download DXF
              </a>

              {/* JSON Toggle */}
              <button
                onClick={() => setShowJson(!showJson)}
                className="block mt-4 text-xs text-zinc-600 hover:text-zinc-500
                           transition-colors duration-200 cursor-pointer"
              >
                {showJson ? 'Hide' : 'Show'} JSON
              </button>

              <AnimatePresence>
                {showJson && (
                  <motion.pre
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="mt-3 p-3 bg-zinc-950 border border-zinc-800/40 rounded-md
                               text-[11px] leading-relaxed text-zinc-600 font-mono
                               overflow-auto max-h-80"
                  >
                    {JSON.stringify(result.plan, null, 2)}
                  </motion.pre>
                )}
              </AnimatePresence>
            </motion.div>
          )}
        </AnimatePresence>

      </motion.div>
    </div>
  )
}
