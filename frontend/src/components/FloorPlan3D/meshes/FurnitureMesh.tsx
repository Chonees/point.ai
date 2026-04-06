import { useMemo } from 'react'
import { useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import type { PlacedFurniture } from '../types'

function tuneSceneMaterial(material: THREE.Material) {
  if ('envMapIntensity' in material) {
    const shaded = material as THREE.MeshStandardMaterial
    shaded.envMapIntensity = 1.2
    shaded.needsUpdate = true
  }
}

export function GLBModel({ url, scale, tintColor }: { url: string; scale: number; tintColor?: string }) {
  const { scene } = useGLTF(url)
  const cloned = useMemo(() => {
    const copy = scene.clone(true)
    copy.traverse((object) => {
      if (!(object as THREE.Mesh).isMesh) return
      const mesh = object as THREE.Mesh

      mesh.castShadow = true
      mesh.receiveShadow = true

      const applyMaterial = (material: THREE.Material) => {
        const next = material.clone()
        tuneSceneMaterial(next)

        if (tintColor && 'color' in next) {
          const std = next as THREE.MeshStandardMaterial
          const tint = new THREE.Color(tintColor)
          std.color.lerp(tint, 0.7)
          std.needsUpdate = true
        }

        return next
      }

      if (Array.isArray(mesh.material)) {
        mesh.material = mesh.material.map(applyMaterial)
      } else if (mesh.material) {
        mesh.material = applyMaterial(mesh.material)
      }
    })
    return copy
  }, [scene, tintColor])

  return <primitive object={cloned} scale={[scale, scale, scale]} />
}

export function FurnitureMesh({
  placed,
  selected,
  placing,
  onClick,
}: {
  placed: PlacedFurniture
  selected: boolean
  placing: boolean
  onClick: () => void
}) {
  const { item, x, y, z, rotation, scaleW, scaleD, scaleH, tintColor } = placed

  return (
    <group
      position={[x, y, z]}
      rotation={[0, rotation, 0]}
      raycast={placing ? () => {} : undefined}
      onClick={placing ? undefined : (event) => {
        event.stopPropagation()
        onClick()
      }}
    >
      <group scale={[scaleW, scaleH, scaleD]} rotation={item.wallMount ? [-Math.PI / 2, 0, 0] : [0, 0, 0]}>
        <GLBModel url={`/models/${item.glb}`} scale={item.scale} tintColor={tintColor} />
      </group>
      {selected && (
        <mesh position={[0, item.scale * scaleH * 0.5, 0]}>
          <boxGeometry args={[item.scale * scaleW, item.scale * scaleH, item.scale * scaleD]} />
          <meshBasicMaterial color="#60a5fa" wireframe transparent opacity={0.4} toneMapped={false} />
        </mesh>
      )}
    </group>
  )
}

export function FurnitureBoxFallback({ placed }: { placed: PlacedFurniture }) {
  const size = placed.item.scale * 0.3
  return (
    <mesh position={[placed.x, size / 2, placed.z]} castShadow receiveShadow>
      <boxGeometry args={[size, size, size]} />
      <meshStandardMaterial color="#666666" roughness={0.7} envMapIntensity={0.6} />
    </mesh>
  )
}
