import { Suspense, useMemo, useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, useGLTF } from '@react-three/drei'
import * as THREE from 'three'

/**
 * Standalone 3D preview of a single GLB model.
 * Uses its own Canvas (1 extra WebGL context — safe alongside the main scene).
 */

function AutoRotatingModel({ url }: { url: string }) {
  const { scene } = useGLTF(url)
  const groupRef = useRef<THREE.Group>(null)

  // Clone, center, and normalize the model to fit in a unit sphere
  const cloned = useMemo(() => {
    const copy = scene.clone(true)

    // Compute bounding box to center and scale
    const box = new THREE.Box3().setFromObject(copy)
    const center = box.getCenter(new THREE.Vector3())
    const size = box.getSize(new THREE.Vector3())
    const maxDim = Math.max(size.x, size.y, size.z)
    const scale = maxDim > 0 ? 2.2 / maxDim : 1

    copy.position.set(-center.x * scale, -center.y * scale, -center.z * scale)
    copy.scale.setScalar(scale)

    copy.traverse((obj) => {
      if ((obj as THREE.Mesh).isMesh) {
        const mesh = obj as THREE.Mesh
        mesh.castShadow = false
        mesh.receiveShadow = false
      }
    })

    return copy
  }, [scene])

  // Gentle auto-rotation
  useFrame((_, delta) => {
    if (groupRef.current) {
      groupRef.current.rotation.y += delta * 0.8
    }
  })

  return (
    <group ref={groupRef}>
      <primitive object={cloned} />
    </group>
  )
}

function Fallback() {
  const ref = useRef<THREE.Mesh>(null)
  useFrame((_, delta) => {
    if (ref.current) ref.current.rotation.y += delta * 2
  })
  return (
    <mesh ref={ref}>
      <boxGeometry args={[0.8, 0.8, 0.8]} />
      <meshStandardMaterial color="#444" wireframe />
    </mesh>
  )
}

export function ModelPreview({ glbPath, name }: { glbPath: string; name: string }) {
  return (
    <div className="flex flex-col items-center">
      <div className="h-36 w-full overflow-hidden rounded-lg border border-zinc-700/40 bg-zinc-950">
        <Canvas
          dpr={[1, 2]}
          gl={{ antialias: true, alpha: true, powerPreference: 'low-power' }}
          camera={{ position: [3.2, 2.2, 3.2], fov: 35, near: 0.1, far: 50 }}
          style={{ background: 'transparent' }}
        >
          <color attach="background" args={['#0a0a0f']} />
          <ambientLight intensity={0.5} />
          <directionalLight position={[3, 4, 2]} intensity={1.8} color="#fff8ee" />
          <directionalLight position={[-2, 2, -1]} intensity={0.4} color="#a0c0ff" />
          <Suspense fallback={<Fallback />}>
            <AutoRotatingModel url={glbPath} />
          </Suspense>
          <OrbitControls
            enableZoom={false}
            enablePan={false}
            autoRotate={false}
          />
        </Canvas>
      </div>
      <p className="mt-1.5 text-[10px] font-medium text-zinc-400">{name}</p>
    </div>
  )
}
