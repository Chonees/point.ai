import { useCallback } from 'react'
import type { ThreeEvent } from '@react-three/fiber'
import * as THREE from 'three'
import type { PlacementSurface, SurfaceHit } from '../types'

function extractHit(event: ThreeEvent<MouseEvent> | ThreeEvent<PointerEvent>): SurfaceHit {
  let normal: THREE.Vector3 | null = null
  if (event.face && event.object) {
    normal = event.face.normal.clone()
      .applyQuaternion(event.object.getWorldQuaternion(new THREE.Quaternion()))
  }
  return { x: event.point.x, y: event.point.y, z: event.point.z, normal }
}

export function usePlacementHandlers({ selectedItem, onPointerMove, onPointerLeave }: PlacementSurface) {
  const handleClick = useCallback(
    (_event: ThreeEvent<MouseEvent>) => {
      // Placement is done via E key, not click
    },
    [],
  )
  const handlePointerMove = useCallback(
    (event: ThreeEvent<PointerEvent>) => {
      if (!selectedItem) return
      onPointerMove(extractHit(event))
    },
    [selectedItem, onPointerMove],
  )
  const handlePointerOver = useCallback(() => {
    if (selectedItem) document.body.style.cursor = 'crosshair'
  }, [selectedItem])
  const handlePointerOut = useCallback(() => {
    document.body.style.cursor = 'default'
    onPointerLeave()
  }, [onPointerLeave])

  return { handleClick, handlePointerMove, handlePointerOver, handlePointerOut }
}
