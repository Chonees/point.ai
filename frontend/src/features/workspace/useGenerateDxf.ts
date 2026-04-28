import { useState, useCallback } from 'react'
import type { OpeningAnnotation, V2Result } from '../../types'
import { fileToBase64 } from '../../utils/fileToBase64'
import { apiUrl } from '../../lib/api'

interface UseGenerateDxfOptions {
  file: File | null
  preview: string | null
  onStructureChange?: (structure: Record<string, unknown>) => void
  reviewedAnnotations?: OpeningAnnotation[]
  useReviewedAnnotations?: boolean
}

export function useGenerateDxf({
  file,
  preview,
  onStructureChange,
  reviewedAnnotations = [],
  useReviewedAnnotations = false,
}: UseGenerateDxfOptions) {
  const [status, setStatus] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [statusMsg, setStatusMsg] = useState('')
  const [result, setResult] = useState<V2Result | null>(null)

  const generate = useCallback(async () => {
    if (!file && !preview) {
      setStatus('error')
      setStatusMsg('Upload a floor plan image first.')
      return
    }
    setStatus('loading')
    setStatusMsg('Processing floor plan...')
    setResult(null)

    try {
      const imageBase64 = file ? await fileToBase64(file) : preview!.replace(/^data:image\/\w+;base64,/, '')
      const body: Record<string, unknown> = { image: imageBase64, model_variant: 'ensemble' }
      if (useReviewedAnnotations) {
        body.annotations = reviewedAnnotations.map(({ _source, ...annotation }) => annotation)
      }

      const response = await fetch(apiUrl('/api/v2/generate-dxf'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!response.ok) throw new Error((await response.json()).detail ?? `Error ${response.status}`)
      const data: V2Result = await response.json()

      if (data.preview_url) {
        try {
          const previewResponse = await fetch(apiUrl(data.preview_url))
          const blob = await previewResponse.blob()
          const reader = new FileReader()
          const previewDataUrl = await new Promise<string>((resolve) => {
            reader.onload = () => resolve(reader.result as string)
            reader.readAsDataURL(blob)
          })
          data.structure = { ...data.structure, _preview_data: previewDataUrl }
        } catch {
          // ignore preview fetch failures
        }
      }

      setResult(data)
      setStatus('done')
      setStatusMsg('')
      if (onStructureChange) onStructureChange(data.structure)
    } catch (error) {
      setStatus('error')
      setStatusMsg(error instanceof Error ? error.message : 'Unknown error')
    }
  }, [file, onStructureChange, preview, reviewedAnnotations, useReviewedAnnotations])

  return { status, statusMsg, result, setResult, setStatus, setStatusMsg, generate }
}
