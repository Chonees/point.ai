import { useCallback, useMemo, useState } from 'react'
import type { CadWorkspaceExtractResult, CadWorkspaceStatus } from './types'

function isSupportedCadFile(file: File | null) {
  if (!file) return false
  const lower = file.name.toLowerCase()
  return lower.endsWith('.dxf') || lower.endsWith('.dwg')
}

export function useCadWorkspace() {
  const [file, setFile] = useState<File | null>(null)
  const [status, setStatus] = useState<CadWorkspaceStatus>('idle')
  const [statusMsg, setStatusMsg] = useState('')
  const [result, setResult] = useState<CadWorkspaceExtractResult | null>(null)

  const canExtract = useMemo(() => isSupportedCadFile(file), [file])

  const selectFile = useCallback((nextFile: File | null) => {
    setFile(nextFile)
    setResult(null)
    setStatus('idle')
    if (!nextFile) {
      setStatusMsg('')
      return
    }
    if (isSupportedCadFile(nextFile)) {
      setStatusMsg(`CAD ready: ${nextFile.name}`)
      return
    }
    setStatus('error')
    setStatusMsg('Subí un .dxf o .dwg de AutoCAD.')
  }, [])

  const extract = useCallback(async () => {
    if (!file) {
      setStatus('error')
      setStatusMsg('Primero subí un .dxf o .dwg.')
      return
    }
    if (!isSupportedCadFile(file)) {
      setStatus('error')
      setStatusMsg('Solo soportamos .dxf y .dwg en este workspace CAD.')
      return
    }

    setStatus('loading')
    setStatusMsg('Extrayendo floor plan y site plan...')
    setResult(null)

    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await fetch('/api/cad-workspace/extract', {
        method: 'POST',
        body: formData,
      })
      const payload = await response.json()
      if (!response.ok) {
        throw new Error(payload?.detail || 'No se pudo extraer el CAD.')
      }
      setResult(payload)
      setStatus('done')
      setStatusMsg('Extracción lista. Floor plan y site plan quedaron normalizados a la misma unidad.')
    } catch (error) {
      setStatus('error')
      setStatusMsg(error instanceof Error ? error.message : 'No se pudo extraer el CAD.')
    }
  }, [file])

  return {
    file,
    status,
    statusMsg,
    result,
    canExtract,
    selectFile,
    extract,
  }
}
