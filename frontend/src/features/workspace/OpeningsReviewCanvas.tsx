import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { OpeningAnnotation, SwingDir } from '../../types'
import {
  getOpeningMoveHandle,
  getOpeningPreviewGeometry,
  getOpeningSwingOptions,
  getOpeningSwingTargetPoint,
  setOpeningSwing,
  translateOpeningAnnotation,
} from './openingsReview'

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

  const handleSetSwing = useCallback((index: number, swing: SwingDir) => {
    onChange(annotations.map((annotation, annotationIndex) => (
      annotationIndex === index ? setOpeningSwing(annotation, swing) : annotation
    )))
  }, [annotations, onChange])

  const handleStartMove = useCallback((event: React.PointerEvent<SVGCircleElement>, index: number) => {
    event.stopPropagation()
    const point = clientToImage(event.clientX, event.clientY)
    if (!point) return
    setSelectedIndex(index)
    setDragState({
      index,
      start: point,
      origin: annotations[index],
    })
  }, [annotations, clientToImage])

  return (
    <div className="rounded-[24px] border border-white/6 bg-white/[0.02] p-4">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Openings review</p>
          <p className="mt-2 text-sm text-zinc-400">
            {annotations.length > 0
              ? `${reviewCountLabel}. Seleccioná una opening, arrastrá el punto central para moverla y tocá el lado dibujado que querés dejar.`
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
              const moveHandle = getOpeningMoveHandle(annotation)
              const swingOptions = getOpeningSwingOptions(annotation)
              const previewSwings = isSelected
                ? swingOptions
                : (annotation.swing ? [annotation.swing] : [])
              const anchorColor = annotation.swing ? '#22c55e' : '#f59e0b'

              return (
                <g key={`${annotation.type}-${index}`}>
                  <line
                    x1={annotation.x1}
                    y1={annotation.y1}
                    x2={annotation.x2}
                    y2={annotation.y2}
                    stroke="transparent"
                    strokeWidth={24}
                    strokeLinecap="round"
                    onPointerDown={(event) => {
                      event.stopPropagation()
                      setSelectedIndex(index)
                    }}
                  />

                  <line
                    x1={annotation.x1}
                    y1={annotation.y1}
                    x2={annotation.x2}
                    y2={annotation.y2}
                    stroke={anchorColor}
                    strokeWidth={isSelected ? 2.5 : 3}
                    strokeLinecap="round"
                    opacity={0.35}
                    strokeDasharray={annotation.swing ? undefined : '6 6'}
                  />

                  {previewSwings.map((swing) => {
                    const preview = getOpeningPreviewGeometry(annotation, swing)
                    const isCurrent = annotation.swing === swing
                    const previewColor = isCurrent
                      ? '#22c55e'
                      : '#38bdf8'
                    const dash = isCurrent ? undefined : '8 6'
                    const target = getOpeningSwingTargetPoint(annotation, swing)

                    return (
                      <g key={`${annotation.type}-${index}-${swing}`}>
                        {preview.lines.map((line, lineIndex) => (
                          <line
                            key={`${swing}-line-${lineIndex}`}
                            x1={line.x1}
                            y1={line.y1}
                            x2={line.x2}
                            y2={line.y2}
                            stroke={previewColor}
                            strokeWidth={isCurrent ? 3.5 : 2.75}
                            strokeLinecap="round"
                            strokeDasharray={dash}
                            opacity={isCurrent ? 1 : 0.9}
                          />
                        ))}
                        {preview.arc && (
                          <path
                            d={`M ${preview.arc.startX} ${preview.arc.startY} Q ${preview.arc.controlX} ${preview.arc.controlY} ${preview.arc.endX} ${preview.arc.endY}`}
                            fill="none"
                            stroke={previewColor}
                            strokeWidth={isCurrent ? 3 : 2.5}
                            strokeLinecap="round"
                            strokeDasharray={dash}
                            opacity={isCurrent ? 1 : 0.9}
                          />
                        )}

                        {isSelected && (
                          <>
                            <circle
                              cx={target.x}
                              cy={target.y}
                              r={11}
                              fill={isCurrent ? 'rgba(34,197,94,0.20)' : 'rgba(56,189,248,0.18)'}
                              stroke={isCurrent ? '#22c55e' : '#38bdf8'}
                              strokeWidth={1.75}
                              data-testid={`opening-swing-target-${swing}`}
                              onPointerDown={(event) => {
                                event.stopPropagation()
                                handleSetSwing(index, swing)
                              }}
                            />
                            <text
                              x={target.x}
                              y={target.y + 4}
                              textAnchor="middle"
                              fill={isCurrent ? '#dcfce7' : '#bae6fd'}
                              fontSize="10"
                              fontWeight="700"
                              pointerEvents="none"
                            >
                              {swing[0].toUpperCase()}
                            </text>
                          </>
                        )}
                      </g>
                    )
                  })}

                  {isSelected && (
                    <>
                      <circle
                        cx={moveHandle.x}
                        cy={moveHandle.y}
                        r={10}
                        fill="rgba(8,47,73,0.94)"
                        stroke="#38bdf8"
                        strokeWidth={2}
                        data-testid="opening-move-handle"
                        onPointerDown={(event) => handleStartMove(event, index)}
                      />
                      <text
                        x={moveHandle.x}
                        y={moveHandle.y + 3}
                        textAnchor="middle"
                        fill="#38bdf8"
                        fontSize="9"
                        fontWeight="700"
                        fontFamily="'Segoe UI Symbol', 'Noto Sans Symbols', sans-serif"
                        pointerEvents="none"
                        data-testid="opening-move-glyph"
                      >
                        ✋
                      </text>
                    </>
                  )}
                </g>
              )
            })}
          </svg>
        </div>
      </div>
    </div>
  )
}
