import type { MaterialPreset } from '../catalog'
import type { FloorBounds, PlacementSurface } from '../types'
import { usePlacementHandlers } from '../hooks/usePlacementHandlers'

export function FloorMesh({
  floorBounds,
  material,
  ...placement
}: {
  floorBounds: FloorBounds
  material: MaterialPreset
} & PlacementSurface) {
  const { handleClick, handlePointerMove, handlePointerOver, handlePointerOut } = usePlacementHandlers(placement)

  return (
    <mesh
      position={[floorBounds.x, -0.5, floorBounds.z]}
      rotation={[-Math.PI / 2, 0, 0]}
      receiveShadow
      onClick={handleClick}
      onPointerMove={handlePointerMove}
      onPointerOver={handlePointerOver}
      onPointerOut={handlePointerOut}
    >
      <planeGeometry args={[floorBounds.w, floorBounds.d]} />
      <meshPhysicalMaterial
        color={material.color}
        roughness={material.roughness}
        metalness={material.roughness < 0.35 ? 0.08 : 0.03}
        clearcoat={material.roughness < 0.45 ? 0.7 : 0.2}
        clearcoatRoughness={Math.min(material.roughness, 0.4)}
        envMapIntensity={1.45}
      />
    </mesh>
  )
}
