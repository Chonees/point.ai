import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { OpeningAnnotation } from '../../types'
import { translateOpeningAnnotation } from './openingsReview'

interface OpeningsReviewCanvasProps {
  imageSrc: string
  annotations: OpeningAnnotation[]
  onChange: (annotations: OpeningAnnotation[]) => void
}

interface DragState {
  index: number
  start: { x: number; y: number }
  origin: OpeningAnnotation
}

export function OpeningsReviewCanvas({
  imageSrc,
  annotations,
  onChange,
}: OpeningsReviewCanvasProps) {
  const imageRef = useRef<HTMLImageElement>(null)
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)
  const [imageSize, setImageSize] = useState({ width: 1, height: 1 })
  const [dragState, setDragState] = useState<DragState | null>(null)

  useEffect(() => {
    if (selectedIndex === null) return
    if (selectedIndex < annotations.length) return
    setSelectedIndex(null)
  }, [annotations.length, selectedIndex])

  const clientToImage = useCallback((clientX: number, clientY: number) => {
    const rect = imageRef.current?.getBoundingClientRect()
    if (!rect) return null
    const scaleX = imageSize.width / rect.width
    const scaleY = imageSize.height / rect.height
    return {
      x: (clientX - rect.left) * scaleX,
      y: (clientY - rect.top) * scaleY,
    }
  }, [imageSize.height, imageSize.width])

  useEffect(() => {
    if (!dragState) return

    const handlePointerMove = (event: PointerEvent) => {
      const point = clientToImage(event.clientX, event.clientY)
      if (!point) return

      const dx = point.x - dragState.start.x
      const dy = point.y - dragState.start.y
      onChange(annotations.map((annotation, index) => (
        index === dragState.index
          ? translateOpeningAnnotation(dragState.origin, { dx, dy })
          : annotation
      )))
    }

    const handlePointerUp = () => {
      setDragState(null)
    }

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', handlePointerUp)
    return () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', handlePointerUp)
    }
  }, [annotations, clientToImage, dragState, onChange])

  const selectedAnnotation = selectedIndex === null ? null : annotations[selectedIndex] ?? null
  const reviewCountLabel = useMemo(() => (
    annotations.length === 1 ? '1 opening ready to review' : `${annotations.length} openings ready to review`
  ), [annotations.length])

  const handleDeleteSelected = useCallback(() => {
    if (selectedIndex === null) return
    onChange(annotations.filter((_, index) => index !== selectedIndex))
    setSelectedIndex(null)
  }, [annotations, onChange, selectedIndex])

  return (
    <div className="rounded-[24px] border border-white/6 bg-white/[0.02] p-4">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Openings review</p>
          <p className="mt-2 text-sm text-zinc-400">
            {annotations.length > 0
              ? `${reviewCountLabel}. Seleccioná una puerta o ventana para moverla libremente o borrarla.`
              : 'No hay openings activas en esta sesión. Si borraste todas, podés regenerar el DXF para confirmar ese estado.'}
          </p>
        </div>
        <button
          type="button"
          onClick={handleDeleteSelected}
          disabled={selectedAnnotation == null}
          className="rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-2 text-xs font-medium text-red-200 transition-colors hover:bg-red-500/15 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Eliminar seleccionada
        </button>
      </div>

      <div className="flex justify-center overflow-hidden rounded-[20px] border border-white/6 bg-zinc-950 p-3">
        <div className="relative">
          <img
            ref={imageRef}
            src={imageSrc}
            alt="Openings review source"
            className="block max-h-[640px] max-w-full select-none"
            onLoad={(event) => {
              setImageSize({
                width: event.currentTarget.naturalWidth || 1,
                height: event.currentTarget.naturalHeight || 1,
              })
            }}
            draggable={false}
          />

          <svg
            viewBox={`0 0 ${imageSize.width} ${imageSize.height}`}
            className="absolute inset-0 h-full w-full"
            onPointerDown={() => setSelectedIndex(null)}
          >
            {annotations.map((annotation, index) => {
              const isSelected = selectedIndex === index
              const color = annotation.type === 'door' ? '#22c55e' : '#f59e0b'
              const midX = (annotation.x1 + annotation.x2) / 2
              const midY = (annotation.y1 + annotation.y2) / 2

              return (
                <g key={`${annotation.type}-${index}`}>
                  <line
                    x1={annotation.x1}
                    y1={annotation.y1}
                    x2={annotation.x2}
                    y2={annotation.y2}
                    stroke="transparent"
                    strokeWidth={18}
                    strokeLinecap="round"
                    onPointerDown={(event) => {
                      event.stopPropagation()
                      const point = clientToImage(event.clientX, event.clientY)
                      if (!point) return
                      setSelectedIndex(index)
                      setDragState({
                        index,
                        start: point,
                        origin: annotation,
                      })
                    }}
                  />
                  <line
                    x1={annotation.x1}
                    y1={annotation.y1}
                    x2={annotation.x2}
                    y2={annotation.y2}
                    stroke={color}
                    strokeWidth={isSelected ? 5 : 4}
                    strokeLinecap="round"
                    opacity={isSelected ? 1 : 0.9}
                  />
                  <circle cx={annotation.x1} cy={annotation.y1} r={isSelected ? 5 : 4} fill={color} />
                  <circle cx={annotation.x2} cy={annotation.y2} r={isSelected ? 5 : 4} fill={color} />
                  <text
                    x={midX}
                    y={midY - 8}
                    textAnchor="middle"
                    fill={color}
                    fontSize="14"
                    fontWeight="700"
                  >
                    {annotation.type === 'door' ? 'D' : 'W'}
                  </text>
                </g>
              )
            })}
          </svg>
        </div>
      </div>
    </div>
  )
}
