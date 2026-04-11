import { useCallback, useEffect, useRef, useState } from 'react'
import { useThumbnail } from './useThumbnail'
import type { FurnitureItem } from './catalog'

interface ThumbnailCardProps {
  item: FurnitureItem
  selected: boolean
  onClick: () => void
}

export function ThumbnailCard({ item, selected, onClick }: ThumbnailCardProps) {
  const thumbs = useThumbnail(`/models/${item.glb}`)
  const [frame, setFrame] = useState(0)
  const rafRef = useRef<number | null>(null)
  const lastTimeRef = useRef(0)
  const hovering = useRef(false)

  // ~80ms per frame = 24 frames × 80ms ≈ 2 seconds per full rotation
  const FRAME_INTERVAL = 80

  const animate = useCallback((time: number) => {
    if (!hovering.current || !thumbs) return
    if (time - lastTimeRef.current >= FRAME_INTERVAL) {
      lastTimeRef.current = time
      setFrame((f) => (f + 1) % thumbs.length)
    }
    rafRef.current = requestAnimationFrame(animate)
  }, [thumbs])

  const startRotation = useCallback(() => {
    if (!thumbs || thumbs.length < 2) return
    hovering.current = true
    lastTimeRef.current = 0
    rafRef.current = requestAnimationFrame(animate)
  }, [thumbs, animate])

  const stopRotation = useCallback(() => {
    hovering.current = false
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    setFrame(0)
  }, [])

  useEffect(() => () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
  }, [])

  return (
    <button
      onClick={onClick}
      onMouseEnter={startRotation}
      onMouseLeave={stopRotation}
      className={`group cursor-pointer overflow-hidden rounded-lg border transition-all ${
        selected
          ? 'border-blue-600/50 bg-blue-900/30 ring-1 ring-blue-600/30'
          : 'border-zinc-800/40 bg-zinc-800/20 hover:border-zinc-600/60 hover:bg-zinc-800/50'
      }`}
    >
      <div className="flex aspect-square items-center justify-center overflow-hidden bg-zinc-950/50">
        {thumbs ? (
          <img
            src={thumbs[frame]}
            alt={item.name}
            className="h-full w-full object-cover"
            draggable={false}
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-700 border-t-zinc-400" />
          </div>
        )}
      </div>
      <p className="truncate px-1 py-1 text-[8px] leading-tight text-zinc-500 group-hover:text-zinc-400">
        {item.name}
      </p>
    </button>
  )
}
