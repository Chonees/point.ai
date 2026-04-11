import { useMemo } from 'react'
import { calcPosFromAngles } from '@react-three/drei'
import * as THREE from 'three'
import type { FloorBounds } from '../types'

const SKY_INCLINATION = 0.56
const SKY_AZIMUTH = 0.18

export function SceneLighting({
  center,
  floorBounds,
  camDist,
}: {
  center: { x: number; z: number }
  floorBounds: FloorBounds
  camDist: number
}) {
  const sunDirection = useMemo(
    () => calcPosFromAngles(SKY_INCLINATION, SKY_AZIMUTH, new THREE.Vector3()).normalize(),
    [],
  )
  const lightPosition = useMemo(
    () => [
      center.x + sunDirection.x * camDist * 2.6,
      Math.max(camDist * 1.8, sunDirection.y * camDist * 3.4),
      center.z + sunDirection.z * camDist * 2.6,
    ] as const,
    [camDist, center.x, center.z, sunDirection],
  )
  const shadowExtent = Math.max(floorBounds.w, floorBounds.d) * 1.2

  return (
    <>
      <ambientLight intensity={0.08} />
      <hemisphereLight args={['#dcecff', '#7b6d52', 0.32]} />
      <directionalLight
        castShadow
        position={lightPosition}
        intensity={3.4}
        color="#fff5da"
        shadow-mapSize-width={4096}
        shadow-mapSize-height={4096}
        shadow-camera-left={-shadowExtent}
        shadow-camera-right={shadowExtent}
        shadow-camera-top={shadowExtent}
        shadow-camera-bottom={-shadowExtent}
        shadow-camera-near={1}
        shadow-camera-far={camDist * 8}
        shadow-bias={-0.0002}
        shadow-normalBias={0.02}
      />
      <directionalLight
        position={[center.x - camDist * 1.8, camDist * 0.95, center.z - camDist * 1.4]}
        intensity={0.2}
        color="#b8d7ff"
      />
    </>
  )
}
