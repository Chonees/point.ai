import { useCallback, useEffect, useRef, useState } from 'react'
import type { FurnitureItem } from '../catalog'
import type { PlacedFurniture, PlacementSurface } from '../types'
import * as THREE from 'three'

function normalToRotation(normal: THREE.Vector3): number {
  return Math.atan2(normal.x, normal.z)
}

export function useGhostControls({
  selectedItem,
  setSelectedItem,
  setPlaced,
  setSelectedPlaced,
}: {
  selectedItem: FurnitureItem | null
  setSelectedItem: (item: FurnitureItem | null) => void
  setPlaced: React.Dispatch<React.SetStateAction<PlacedFurniture[]>>
  setSelectedPlaced: React.Dispatch<React.SetStateAction<number>>
}) {
  const [ghostPos, setGhostPos] = useState<{ x: number; y: number; z: number; wallRotation: number | null } | null>(null)
  const [ghostRotation, setGhostRotation] = useState(0)
  const [ghostHeight, setGhostHeight] = useState(0)
  const [ghostScaleW, setGhostScaleW] = useState(1)
  const [ghostScaleD, setGhostScaleD] = useState(1)
  const [ghostScaleH, setGhostScaleH] = useState(1)

  const selectedItemRef = useRef(selectedItem)
  selectedItemRef.current = selectedItem
  const ghostPosRef = useRef(ghostPos)
  ghostPosRef.current = ghostPos
  const ghostRotationRef = useRef(ghostRotation)
  ghostRotationRef.current = ghostRotation
  const ghostHeightRef = useRef(ghostHeight)
  ghostHeightRef.current = ghostHeight
  const ghostScaleWRef = useRef(ghostScaleW)
  ghostScaleWRef.current = ghostScaleW
  const ghostScaleDRef = useRef(ghostScaleD)
  ghostScaleDRef.current = ghostScaleD
  const ghostScaleHRef = useRef(ghostScaleH)
  ghostScaleHRef.current = ghostScaleH

  const handlePlaceKey = useCallback((e: React.KeyboardEvent) => {
    if ((e.target as HTMLElement)?.tagName === 'INPUT') return
    if (selectedItem) {
      if (e.key === 'ArrowLeft') { e.preventDefault(); setGhostRotation((r) => r - Math.PI / 12); return }
      if (e.key === 'ArrowRight') { e.preventDefault(); setGhostRotation((r) => r + Math.PI / 12); return }
      if ((e.key === 'e' || e.key === 'E') && ghostPos) {
        e.preventDefault()
        const rot = (ghostPos.wallRotation ?? 0) + ghostRotation
        setPlaced((cur) => {
          const next = [...cur, { item: selectedItem, x: ghostPos.x, y: ghostHeight > 0 ? ghostHeight : ghostPos.y, z: ghostPos.z, rotation: rot, scaleW: ghostScaleW, scaleD: ghostScaleD, scaleH: ghostScaleH }]
          setSelectedPlaced(next.length - 1)
          return next
        })
        setSelectedItem(null)
      }
      return
    }
  }, [selectedItem, ghostPos, ghostRotation, ghostHeight, ghostScaleW, ghostScaleD, ghostScaleH, setPlaced, setSelectedItem, setSelectedPlaced])

  useEffect(() => {
    const handleWheel = (e: WheelEvent) => {
      if (!selectedItemRef.current) return
      if (e.shiftKey) {
        e.preventDefault(); e.stopImmediatePropagation()
        setGhostHeight((h) => Math.max(0, h + (e.deltaY < 0 ? 4 : -4)))
      } else if (e.ctrlKey) {
        e.preventDefault(); e.stopImmediatePropagation()
        setGhostScaleW((s) => Math.max(0.1, Math.min(5, s + (e.deltaY < 0 ? 0.02 : -0.02))))
      } else if (e.altKey) {
        e.preventDefault(); e.stopImmediatePropagation()
        setGhostScaleD((s) => Math.max(0.1, Math.min(5, s + (e.deltaY < 0 ? 0.02 : -0.02))))
      }
    }
    const handleContext = (e: MouseEvent) => {
      if (!selectedItemRef.current) return
      e.preventDefault()
      setGhostRotation((r) => r + Math.PI / 12)
    }
    const handleKey = (e: KeyboardEvent) => {
      if (!selectedItemRef.current) return
      if ((e.target as HTMLElement)?.tagName === 'INPUT') return
      if (e.key === 'ArrowUp') { e.preventDefault(); setGhostScaleH((s) => Math.min(5, s + 0.02)) }
      if (e.key === 'ArrowDown') { e.preventDefault(); setGhostScaleH((s) => Math.max(0.1, s - 0.02)) }
    }
    document.addEventListener('wheel', handleWheel, { passive: false, capture: true })
    document.addEventListener('contextmenu', handleContext)
    document.addEventListener('keydown', handleKey, { capture: true })
    return () => {
      document.removeEventListener('wheel', handleWheel, { capture: true })
      document.removeEventListener('contextmenu', handleContext)
      document.removeEventListener('keydown', handleKey, { capture: true })
    }
  }, [])

  useEffect(() => {
    setGhostRotation(0); setGhostHeight(0)
    setGhostScaleW(1); setGhostScaleD(1); setGhostScaleH(1)
    setGhostPos(null)
  }, [selectedItem])

  const GRID_SIZE = 3
  const snap = (v: number) => Math.round(v / GRID_SIZE) * GRID_SIZE
  const snapY = (v: number) => Math.round(v / 2) * 2

  const placementProps: PlacementSurface = {
    selectedItem,
    onPointerMove: (hit) => {
      const isWallHit = hit.normal && Math.abs(hit.normal.y) < 0.5
      const wallRot = isWallHit && hit.normal ? normalToRotation(hit.normal) : null
      if (isWallHit && hit.normal) {
        const nx = Math.abs(hit.normal.x)
        const nz = Math.abs(hit.normal.z)
        setGhostPos({ x: nx > 0.5 ? hit.x : snap(hit.x), y: snapY(hit.y), z: nz > 0.5 ? hit.z : snap(hit.z), wallRotation: wallRot })
      } else {
        setGhostPos({ x: snap(hit.x), y: snapY(hit.y), z: snap(hit.z), wallRotation: null })
      }
    },
    onPointerLeave: () => setGhostPos(null),
  }

  return {
    ghostPos,
    ghostRotation,
    ghostHeight,
    ghostScaleW,
    ghostScaleD,
    ghostScaleH,
    handlePlaceKey,
    placementProps,
    setGhostRotation,
    setGhostHeight,
    setGhostScaleW,
    setGhostScaleD,
    setGhostScaleH,
  }
}
