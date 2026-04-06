import { useEffect, useMemo } from 'react'
import { Environment, Sky, calcPosFromAngles } from '@react-three/drei'
import * as THREE from 'three'
import type { FloorBounds } from '../types'

const SKY_INCLINATION = 0.56
const SKY_AZIMUTH = 0.18
const SKY_DISTANCE = 4500

function smoothstep(edge0: number, edge1: number, value: number) {
  const t = THREE.MathUtils.clamp((value - edge0) / (edge1 - edge0), 0, 1)
  return t * t * (3 - 2 * t)
}

export function SceneWorld({
  center,
  floorBounds,
}: {
  center: { x: number; z: number }
  floorBounds: FloorBounds
}) {
  const sunPosition = useMemo(
    () => calcPosFromAngles(SKY_INCLINATION, SKY_AZIMUTH, new THREE.Vector3()).multiplyScalar(SKY_DISTANCE),
    [],
  )

  const terrainGeometry = useMemo(() => {
    const size = Math.max(floorBounds.w, floorBounds.d) * 8
    const halfSize = size / 2
    const plateauRadius = Math.max(floorBounds.w, floorBounds.d) * 0.72
    const geometry = new THREE.PlaneGeometry(size, size, 180, 180)
    const positions = geometry.attributes.position as THREE.BufferAttribute
    const colors = new Float32Array(positions.count * 3)
    const color = new THREE.Color()

    for (let index = 0; index < positions.count; index += 1) {
      const localX = positions.getX(index)
      const localZ = positions.getY(index)
      const worldX = center.x + localX
      const worldZ = center.z + localZ
      const distance = Math.hypot(localX, localZ)
      const terrainMask = smoothstep(plateauRadius, halfSize * 0.9, distance)

      const broadShape =
        Math.sin(worldX / 180) * 5.5 +
        Math.cos(worldZ / 150) * 4.2 +
        Math.sin((worldX + worldZ) / 110) * 2.5
      const secondaryShape =
        Math.sin(worldX / 420 + 1.4) * 7.5 +
        Math.cos(worldZ / 360 - 0.8) * 6
      const edgeDrop = smoothstep(halfSize * 0.6, halfSize * 0.98, distance) * 8
      const height = -4.5 + terrainMask * (broadShape + secondaryShape) - edgeDrop

      positions.setZ(index, height)

      const grassMix = THREE.MathUtils.clamp(0.42 + height * 0.025 + terrainMask * 0.22, 0, 1)
      color.setRGB(0.34, 0.42, 0.24).lerp(new THREE.Color(0.6, 0.58, 0.42), grassMix)
      colors[index * 3] = color.r
      colors[index * 3 + 1] = color.g
      colors[index * 3 + 2] = color.b
    }

    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    geometry.computeVertexNormals()
    return geometry
  }, [center.x, center.z, floorBounds.d, floorBounds.w])

  useEffect(() => () => terrainGeometry.dispose(), [terrainGeometry])

  return (
    <>
      <Sky
        distance={SKY_DISTANCE}
        sunPosition={sunPosition}
        turbidity={5.5}
        rayleigh={2.4}
        mieCoefficient={0.006}
        mieDirectionalG={0.84}
      />
      <Environment files="/hdri/meadow_1k.hdr" environmentIntensity={0.5} />
      <mesh
        geometry={terrainGeometry}
        position={[center.x, -0.75, center.z]}
        rotation={[-Math.PI / 2, 0, 0]}
        receiveShadow
      >
        <meshStandardMaterial vertexColors roughness={1} metalness={0} envMapIntensity={0.18} />
      </mesh>
    </>
  )
}
