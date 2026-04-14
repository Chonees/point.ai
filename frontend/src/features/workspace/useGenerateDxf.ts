import { useState, useCallback } from 'react'
import type { Annotation, AnnotationType, DimensionOrientation, DimensionSubtype, SwingDir, V2Result } from '../../types'
import { fileToBase64 } from '../../utils/fileToBase64'
import { apiUrl } from '../../lib/api'
import { snapEndpointsToWallEdges } from '../../components/OverlayEditor/geometry'

const _randomId = (): string =>
  typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `ann-${Math.random().toString(36).slice(2, 10)}-${Date.now().toString(36)}`

/**
 * Normalize a backend annotation payload into the frontend `Annotation` shape.
 * - Guarantees an `id` (generates one if backend didn't ship it).
 * - Converts snake_case dimension fields to camelCase.
 */
function _toAnnotation(payload: NonNullable<V2Result['auto_annotations']>[number]): Annotation {
  const ann: Annotation = {
    id: payload.id ?? _randomId(),
    type: payload.type as AnnotationType,
    x1: payload.x1,
    y1: payload.y1,
    x2: payload.x2,
    y2: payload.y2,
  }
  if (payload.swing) ann.swing = payload.swing as SwingDir
  if (payload.thickness) ann.thickness = payload.thickness
  if (payload._source) ann._source = payload._source
  if (payload.type === 'dimension') {
    if (payload.subtype) ann.subtype = payload.subtype as DimensionSubtype
    if (payload.offset_px != null) ann.offsetPx = payload.offset_px
    if (payload.orientation) ann.orientation = payload.orientation as DimensionOrientation
    if (payload.outward != null) ann.outward = payload.outward
    if (payload.value_inches != null) ann.valueInches = payload.value_inches
    if (payload.value_text) ann.valueText = payload.value_text
    if (payload.wall_ids) ann.wallIds = payload.wall_ids
    if (payload.window_ids) ann.windowIds = payload.window_ids
  }
  return ann
}

interface UseGenerateDxfOptions {
  file: File | null
  preview: string | null
  annotations: Annotation[]
  autoLoaded: boolean
  totalSqft: string
  onStructureChange?: (structure: Record<string, unknown>) => void
  onAnnotationsUpdate: (updater: (prev: Annotation[]) => Annotation[]) => void
  onAutoLoaded: () => void
}

export function useGenerateDxf({
  file,
  preview,
  annotations,
  autoLoaded,
  totalSqft,
  onStructureChange,
  onAnnotationsUpdate,
  onAutoLoaded,
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
      if (totalSqft) body.total_sqft = Number(totalSqft)

      if (autoLoaded || annotations.length > 0) {
        body.annotations = annotations.map(({ _source, ...rest }) => rest)
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

      if (!autoLoaded && data.auto_annotations?.length) {
        onAnnotationsUpdate(() => {
          const raw: Annotation[] = data.auto_annotations!.map((annotation) => {
            const ann = _toAnnotation(annotation)
            if (!ann._source && ann.type !== 'dimension') ann._source = 'ensemble_cubicasa'
            return ann
          })
          // Dimensions are not wall/opening geometry — they piggyback on walls
          // whose endpoints already got junction-snapped by the backend. Keep
          // them intact; only snap the rest.
          const dims = raw.filter((a) => a.type === 'dimension')
          const rest = snapEndpointsToWallEdges(raw.filter((a) => a.type !== 'dimension'))
          return [...rest, ...dims]
        })
        onAutoLoaded()
      } else if (autoLoaded && data.auto_annotations?.length) {
        // On subsequent calls, merge backend-computed dimensions into the
        // user's current annotations — but never overwrite user-edited
        // dimensions (those carry locked=true or simply already exist and
        // the backend respects them by NOT recomputing). See
        // backend/services/generate_dxf_service.py::_enrich_with_dimensions.
        const incomingDims = data.auto_annotations.filter((a) => a.type === 'dimension')
        if (incomingDims.length) {
          onAnnotationsUpdate((prev) => {
            const hasUserDims = prev.some((a) => a.type === 'dimension')
            if (hasUserDims) return prev
            return [...prev, ...incomingDims.map((a) => _toAnnotation(a))]
          })
        }
      }

      // Always enrich wall annotations with thickness from backend response
      const wallsWithThickness = (data.auto_annotations ?? []).filter(
        (a) => a.type === 'wall' && a.thickness,
      )
      if (wallsWithThickness.length > 0) {
        onAnnotationsUpdate((prev) =>
          prev.map((ann) => {
            if (ann.type !== 'wall') return ann
            if (ann.thickness) return ann
            // Find closest matching wall by midpoint distance
            const mx = (ann.x1 + ann.x2) / 2
            const my = (ann.y1 + ann.y2) / 2
            let bestDist = 15 // tolerance in pixels
            let bestThickness: number | undefined
            for (const w of wallsWithThickness) {
              const wmx = (w.x1 + w.x2) / 2
              const wmy = (w.y1 + w.y2) / 2
              const d = Math.abs(mx - wmx) + Math.abs(my - wmy)
              if (d < bestDist) {
                bestDist = d
                bestThickness = w.thickness
              }
            }
            return bestThickness ? { ...ann, thickness: bestThickness } : ann
          }),
        )
      }

      if (data.computed_rooms?.length) {
        onAnnotationsUpdate((previous) =>
          previous.map((annotation) => {
            if (annotation.type !== 'label' || !annotation.roomName) return annotation
            // Preserve user-edited sqft — only fill in when empty.
            // Also preserve labelScale / labelRotation via the spread below.
            if (annotation.sqft != null) return annotation
            const match = data.computed_rooms!.find(
              (room) => room.roomName === annotation.roomName!.toUpperCase()
                && Math.abs(room.x1 - annotation.x1) < 5
                && Math.abs(room.y1 - annotation.y1) < 5,
            )
            return match ? { ...annotation, sqft: match.sqft } : annotation
          }),
        )
      }
    } catch (error) {
      setStatus('error')
      setStatusMsg(error instanceof Error ? error.message : 'Unknown error')
    }
  }, [annotations, autoLoaded, file, onAnnotationsUpdate, onAutoLoaded, onStructureChange, preview, totalSqft])

  return { status, statusMsg, result, setResult, setStatus, setStatusMsg, generate }
}
