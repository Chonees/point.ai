import { useMemo } from 'react'
import { useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import type { FurnitureItem } from '../catalog'

export function GhostPreview({
  item,
  x,
  y,
  z,
  rotation,
  scaleW,
  scaleD,
  scaleH,
}: {
  item: FurnitureItem
  x: number
  y: number
  z: number
  rotation: number
  scaleW: number
  scaleD: number
  scaleH: number
}) {
  const { scene } = useGLTF(`/models/${item.glb}`)

  const cloned = useMemo(() => {
    const copy = scene.clone(true)
    copy.traverse((obj) => {
      if (!(obj as THREE.Mesh).isMesh) return
      const mesh = obj as THREE.Mesh
      mesh.castShadow = false
      mesh.receiveShadow = false
      const applyGhost = (mat: THREE.Material) => {
        const ghost = mat.clone() as THREE.MeshStandardMaterial
        ghost.transparent = true
        ghost.opacity = 0.5
        ghost.depthWrite = false
        ghost.color = new THREE.Color('#60a5fa')
        ghost.emissive = new THREE.Color('#1d4ed8')
        ghost.emissiveIntensity = 0.3
        return ghost
      }
      if (Array.isArray(mesh.material)) {
        mesh.material = mesh.material.map(applyGhost)
      } else {
        mesh.material = applyGhost(mesh.material)
      }
    })
    return copy
  }, [scene])

  return (
    <group position={[x, 0, z]}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.2, 0]}>
        <ringGeometry args={[item.scale * 0.3, item.scale * 0.35, 48]} />
        <meshBasicMaterial color="#3b82f6" transparent opacity={0.6} toneMapped={false} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.15, 0]}>
        <circleGeometry args={[item.scale * 0.05, 16]} />
        <meshBasicMaterial color="#60a5fa" transparent opacity={0.8} toneMapped={false} />
      </mesh>

      {y > 0 && (
        <mesh position={[0, y / 2, 0]}>
          <cylinderGeometry args={[0.3, 0.3, y, 8]} />
          <meshBasicMaterial color="#3b82f6" transparent opacity={0.3} toneMapped={false} />
        </mesh>
      )}

      <group position={[0, y, 0]} rotation={[0, rotation, 0]}>
        <group rotation={item.wallMount ? [-Math.PI / 2, 0, 0] : [0, 0, 0]}>
          <primitive object={cloned} scale={[item.scale * scaleW, item.scale * scaleH, item.scale * scaleD]} />
        </group>
      </group>
    </group>
  )
}
