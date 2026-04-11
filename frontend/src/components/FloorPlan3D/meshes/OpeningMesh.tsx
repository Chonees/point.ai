import type { Opening3D } from '../structureTo3D'

export function OpeningMesh({ opening }: { opening: Opening3D }) {
  if (opening.kind === 'window') {
    const windowBottom = opening.windowHeight || 36
    return (
      <mesh position={[opening.x, windowBottom + opening.height / 2, opening.z]} castShadow receiveShadow>
        <boxGeometry args={[opening.width + 1, opening.height, opening.depth + 1]} />
        <meshPhysicalMaterial
          color="#b7e6ff"
          transparent
          opacity={0.3}
          transmission={0.72}
          thickness={2.5}
          roughness={0.05}
          clearcoat={0.9}
          clearcoatRoughness={0.08}
          envMapIntensity={1.5}
        />
      </mesh>
    )
  }

  return (
    <mesh position={[opening.x, opening.height / 2, opening.z]} castShadow receiveShadow>
      <boxGeometry args={[opening.width, opening.height, 1.5]} />
      <meshStandardMaterial color="#8b6914" roughness={0.55} metalness={0.05} envMapIntensity={0.7} />
    </mesh>
  )
}
