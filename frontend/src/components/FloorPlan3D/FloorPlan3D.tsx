import { useMemo } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Grid } from '@react-three/drei'
import { structureTo3D } from './structureTo3D'
import type { Wall3D, Opening3D, Scene3D } from './structureTo3D'

export default function FloorPlan3D({ structure }: { structure: Record<string, unknown> }) {
  const scene = useMemo(() => structureTo3D(structure), [structure])
  const camDist = Math.max(scene.floor.width, scene.floor.depth) * 1.2

  return (
    <div className="w-full h-80 sm:h-96 rounded-lg overflow-hidden bg-zinc-950 border border-zinc-800/40">
      <Canvas
        camera={{
          position: [scene.center.x + camDist * 0.5, camDist * 0.6, scene.center.z + camDist * 0.5],
          fov: 45,
          near: 1,
          far: camDist * 10,
        }}
      >
        <ambientLight intensity={0.5} />
        <directionalLight position={[camDist, camDist, camDist * 0.5]} intensity={0.8} castShadow />

        <OrbitControls
          target={[scene.center.x, WALL_HEIGHT * 0.3, scene.center.z]}
          enableDamping
          dampingFactor={0.1}
          minDistance={camDist * 0.2}
          maxDistance={camDist * 3}
        />

        {/* Floor */}
        <mesh position={[scene.floor.x, -0.5, scene.floor.z]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
          <planeGeometry args={[scene.floor.width, scene.floor.depth]} />
          <meshStandardMaterial color="#1a1a1a" />
        </mesh>

        {/* Grid */}
        <Grid
          position={[scene.center.x, 0, scene.center.z]}
          args={[scene.floor.width, scene.floor.depth]}
          cellSize={12}
          cellColor="#333333"
          sectionSize={48}
          sectionColor="#444444"
          fadeDistance={camDist * 2}
          infiniteGrid={false}
        />

        {/* Walls */}
        {scene.walls.map((wall) => (
          <WallMesh key={wall.id} wall={wall} />
        ))}

        {/* Openings */}
        {scene.openings.map((op, i) => (
          <OpeningMesh key={`op-${i}`} opening={op} />
        ))}
      </Canvas>
    </div>
  )
}

const WALL_HEIGHT = 96

function WallMesh({ wall }: { wall: Wall3D }) {
  return (
    <mesh position={[wall.x, wall.height / 2, wall.z]} castShadow receiveShadow>
      <boxGeometry args={[wall.width, wall.height, wall.depth]} />
      <meshStandardMaterial
        color={wall.isExterior ? '#e8e0d4' : '#f0ebe4'}
        roughness={0.9}
      />
    </mesh>
  )
}

function OpeningMesh({ opening }: { opening: Opening3D }) {
  if (opening.kind === 'window') {
    // Glass pane
    const winBottom = opening.windowHeight || 36
    return (
      <mesh position={[opening.x, winBottom + opening.height / 2, opening.z]}>
        <boxGeometry args={[opening.width + 1, opening.height, opening.depth + 1]} />
        <meshPhysicalMaterial
          color="#88ccff"
          transparent
          opacity={0.25}
          roughness={0.05}
          metalness={0.1}
        />
      </mesh>
    )
  }

  // Door: thin slab
  return (
    <mesh position={[opening.x, opening.height / 2, opening.z]}>
      <boxGeometry args={[opening.width, opening.height, 1.5]} />
      <meshStandardMaterial color="#8B6914" roughness={0.7} />
    </mesh>
  )
}
