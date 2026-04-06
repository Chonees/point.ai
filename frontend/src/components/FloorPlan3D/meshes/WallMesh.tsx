import type { Wall3D } from '../structureTo3D'
import type { MaterialPreset } from '../catalog'
import type { PlacementSurface } from '../types'
import { usePlacementHandlers } from '../hooks/usePlacementHandlers'

export function WallMesh({
  wall,
  material,
  ...placement
}: {
  wall: Wall3D
  material: MaterialPreset
} & PlacementSurface) {
  const { handleClick, handlePointerMove, handlePointerOver, handlePointerOut } = usePlacementHandlers(placement)

  return (
    <mesh
      position={[wall.x, wall.height / 2, wall.z]}
      castShadow
      receiveShadow
      onClick={handleClick}
      onPointerMove={handlePointerMove}
      onPointerOver={handlePointerOver}
      onPointerOut={handlePointerOut}
    >
      <boxGeometry args={[wall.width, wall.height, wall.depth]} />
      <meshStandardMaterial
        color={material.color}
        roughness={material.roughness}
        metalness={material.id === 'navy' ? 0.08 : 0.02}
        envMapIntensity={0.8}
      />
    </mesh>
  )
}
