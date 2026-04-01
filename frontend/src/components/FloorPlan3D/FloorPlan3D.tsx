import { Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { Canvas, type ThreeEvent, useThree } from '@react-three/fiber'
import { Environment, Grid, OrbitControls, Sky, calcPosFromAngles, useGLTF } from '@react-three/drei'
import { Bloom, EffectComposer, SSAO, ToneMapping } from '@react-three/postprocessing'
import { ToneMappingMode } from 'postprocessing'
import * as THREE from 'three'

import { WalkControls } from './WalkControls'
import type { Opening3D, Wall3D } from './structureTo3D'
import { CATEGORIES, FURNITURE, MATERIALS } from './catalog'
import type { FurnitureItem, MaterialPreset } from './catalog'
import type { Annotation } from '../../types'

const WALL_HEIGHT = 96
const BACKGROUND_COLOR = '#dbeaf7'
const SKY_INCLINATION = 0.56
const SKY_AZIMUTH = 0.18
const SKY_DISTANCE = 4500

interface FloorBounds {
  x: number
  z: number
  w: number
  d: number
}

interface PlacedFurniture {
  item: FurnitureItem
  x: number
  z: number
  rotation: number
}

function tuneSceneMaterial(material: THREE.Material) {
  if ('envMapIntensity' in material) {
    const shaded = material as THREE.MeshStandardMaterial
    shaded.envMapIntensity = 1.2
    shaded.needsUpdate = true
  }
}

function GLBModel({ url, scale }: { url: string; scale: number }) {
  const { scene } = useGLTF(url)
  const cloned = useMemo(() => {
    const copy = scene.clone(true)
    copy.traverse((object) => {
      if (!(object as THREE.Mesh).isMesh) return

      const mesh = object as THREE.Mesh
      mesh.castShadow = true
      mesh.receiveShadow = true

      if (Array.isArray(mesh.material)) {
        mesh.material = mesh.material.map((material) => {
          const nextMaterial = material.clone()
          tuneSceneMaterial(nextMaterial)
          return nextMaterial
        })
      } else if (mesh.material) {
        const nextMaterial = mesh.material.clone()
        tuneSceneMaterial(nextMaterial)
        mesh.material = nextMaterial
      }
    })
    return copy
  }, [scene])

  return <primitive object={cloned} scale={[scale, scale, scale]} />
}

function smoothstep(edge0: number, edge1: number, value: number) {
  const t = THREE.MathUtils.clamp((value - edge0) / (edge1 - edge0), 0, 1)
  return t * t * (3 - 2 * t)
}

function SceneRenderer({ camDist }: { camDist: number }) {
  const { gl, scene } = useThree()

  useEffect(() => {
    const previousBackground = scene.background
    const previousFog = scene.fog

    scene.background = new THREE.Color(BACKGROUND_COLOR)
    scene.fog = new THREE.Fog(BACKGROUND_COLOR, camDist * 3.5, camDist * 11)
    gl.outputColorSpace = THREE.SRGBColorSpace
    gl.shadowMap.enabled = true
    gl.shadowMap.type = THREE.PCFSoftShadowMap

    return () => {
      scene.background = previousBackground
      scene.fog = previousFog
    }
  }, [camDist, gl, scene])

  return null
}

function SceneWorld({
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
        <meshStandardMaterial
          vertexColors
          roughness={1}
          metalness={0}
          envMapIntensity={0.18}
        />
      </mesh>
    </>
  )
}

function SceneLighting({
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

function SceneEffects() {
  const { gl } = useThree()

  return (
    <EffectComposer
      depthBuffer
      enableNormalPass
      multisampling={gl.capabilities.isWebGL2 ? 4 : 0}
      resolutionScale={0.65}
    >
      <SSAO
        samples={21}
        rings={4}
        radius={0.045}
        intensity={4.5}
        luminanceInfluence={0.72}
        bias={0.025}
      />
      <Bloom
        mipmapBlur
        intensity={0.035}
        luminanceThreshold={1.18}
        luminanceSmoothing={0.05}
        radius={0.42}
      />
      <ToneMapping
        mode={ToneMappingMode.ACES_FILMIC}
        whitePoint={5.5}
        middleGrey={0.72}
        minLuminance={0.02}
        averageLuminance={0.9}
        resolution={256}
      />
    </EffectComposer>
  )
}

export default function FloorPlan3D({
  structure,
  annotations = [],
}: {
  structure: Record<string, unknown>
  annotations?: Annotation[]
}) {
  const { walls3D, openings3D, floorBounds, center } = useMemo(() => {
    const meta = (structure.structure_meta as Record<string, any>) || {}
    const regionPlan = meta.dxf_region_plan || {}
    const regionMeta = regionPlan.meta || {}
    const transform = regionMeta.transform || {}
    const imageShape = regionMeta.image_shape || {}
    const imageHeight = Number(imageShape.height || 0)
    const scale = Number(transform.scale || 1)
    const offsetX = Number(transform.offset_x || 0)
    const offsetY = Number(transform.offset_y || 0)

    const toDxf = (imageX: number, imageY: number) => ({
      x: imageX * scale + offsetX,
      y: (imageHeight - imageY) * scale + offsetY,
    })

    const walls: Wall3D[] = []
    const openings: Opening3D[] = []

    let minX = Infinity
    let maxX = -Infinity
    let minZ = Infinity
    let maxZ = -Infinity

    const track = (x: number, z: number) => {
      if (x < minX) minX = x
      if (x > maxX) maxX = x
      if (z < minZ) minZ = z
      if (z > maxZ) maxZ = z
    }

    for (const annotation of annotations) {
      if (annotation.type === 'eraser') continue

      const p1 = toDxf(annotation.x1, annotation.y1)
      const p2 = toDxf(annotation.x2, annotation.y2)
      const centerX = (p1.x + p2.x) / 2
      const centerZ = -(p1.y + p2.y) / 2
      const absDx = Math.abs(p2.x - p1.x)
      const absDy = Math.abs(p2.y - p1.y)
      const isHorizontal = absDx >= absDy
      const span = Math.sqrt(absDx * absDx + absDy * absDy)

      if (annotation.type === 'wall') {
        const thickness = 4 * scale
        const width = isHorizontal ? span : thickness
        const depth = isHorizontal ? thickness : span

        track(centerX - width / 2, centerZ - depth / 2)
        track(centerX + width / 2, centerZ + depth / 2)

        walls.push({
          id: `w-${walls.length}`,
          x: centerX,
          z: centerZ,
          width,
          depth,
          height: WALL_HEIGHT,
          isExterior: false,
        })
      } else if ((annotation.type === 'door' || annotation.type === 'window') && annotation.swing) {
        track(centerX, centerZ)
        openings.push({
          kind: annotation.type,
          x: centerX,
          z: centerZ,
          width: isHorizontal ? span : 4,
          depth: isHorizontal ? 4 : span,
          height: annotation.type === 'door' ? 80 : 36,
          windowHeight: annotation.type === 'window' ? 36 : undefined,
        })
      }
    }

    if (minX === Infinity) {
      minX = -100
      maxX = 100
      minZ = -100
      maxZ = 100
    }

    const pad = 30
    const floorX = (minX + maxX) / 2
    const floorZ = (minZ + maxZ) / 2
    const floorWidth = maxX - minX + pad * 2
    const floorDepth = maxZ - minZ + pad * 2

    return {
      walls3D: walls,
      openings3D: openings,
      floorBounds: { x: floorX, z: floorZ, w: floorWidth, d: floorDepth },
      center: { x: floorX, z: floorZ },
    }
  }, [annotations, structure])

  const camDist = Math.max(floorBounds.w, floorBounds.d) * 1.2

  const [fullscreen, setFullscreen] = useState(false)
  const [walkMode, setWalkMode] = useState(false)
  const [tab, setTab] = useState<'furniture' | 'materials'>('furniture')
  const [category, setCategory] = useState(CATEGORIES[0])
  const [selectedItem, setSelectedItem] = useState<FurnitureItem | null>(null)
  const [placed, setPlaced] = useState<PlacedFurniture[]>([])
  const [floorMat, setFloorMat] = useState<MaterialPreset>(MATERIALS[0])
  const [wallMat, setWallMat] = useState<MaterialPreset>(
    MATERIALS.find((material) => material.category === 'wall') ?? MATERIALS[0],
  )
  const [selectedPlaced, setSelectedPlaced] = useState(-1)

  const removePlaced = (index: number) => setPlaced((current) => current.filter((_, itemIndex) => itemIndex !== index))
  const rotatePlaced = (index: number) =>
    setPlaced((current) =>
      current.map((furniture, itemIndex) =>
        itemIndex === index
          ? { ...furniture, rotation: furniture.rotation + Math.PI / 2 }
          : furniture,
      ),
    )

  const containerClass = fullscreen
    ? 'fixed inset-0 z-50 flex bg-zinc-950'
    : 'relative h-80 w-full overflow-hidden rounded-lg border border-zinc-800/40 bg-zinc-950 sm:h-96'

  return (
    <div className={containerClass}>
      {fullscreen && (
        <div className="flex w-56 flex-shrink-0 flex-col overflow-hidden border-r border-zinc-800/60 bg-zinc-900">
          <div className="flex border-b border-zinc-800/40">
            <button
              onClick={() => setTab('furniture')}
              className={`flex-1 cursor-pointer py-2 text-[10px] font-medium transition-colors ${
                tab === 'furniture' ? 'bg-zinc-800/40 text-zinc-200' : 'text-zinc-500 hover:text-zinc-400'
              }`}
            >
              Furniture
            </button>
            <button
              onClick={() => setTab('materials')}
              className={`flex-1 cursor-pointer py-2 text-[10px] font-medium transition-colors ${
                tab === 'materials' ? 'bg-zinc-800/40 text-zinc-200' : 'text-zinc-500 hover:text-zinc-400'
              }`}
            >
              Materials
            </button>
          </div>

          {tab === 'furniture' ? (
            <>
              <div className="flex flex-wrap gap-1 border-b border-zinc-800/30 p-2">
                {CATEGORIES.map((nextCategory) => (
                  <button
                    key={nextCategory}
                    onClick={() => setCategory(nextCategory)}
                    className={`cursor-pointer rounded px-2 py-0.5 text-[9px] transition-colors ${
                      nextCategory === category
                        ? 'bg-zinc-700 text-zinc-200'
                        : 'bg-zinc-800/40 text-zinc-500 hover:text-zinc-400'
                    }`}
                  >
                    {nextCategory}
                  </button>
                ))}
              </div>

              <div className="flex-1 space-y-0.5 overflow-y-auto p-1.5">
                {FURNITURE.filter((item) => item.category === category).map((item) => (
                  <button
                    key={item.id}
                    onClick={() => setSelectedItem(selectedItem?.id === item.id ? null : item)}
                    className={`flex w-full cursor-pointer items-center gap-2 rounded border px-2 py-1.5 text-left transition-colors ${
                      selectedItem?.id === item.id
                        ? 'border-blue-700/40 bg-blue-900/30'
                        : 'border-transparent hover:bg-zinc-800/40'
                    }`}
                  >
                    <span className="text-sm">{item.icon}</span>
                    <div>
                      <p className="text-[10px] text-zinc-300">{item.name}</p>
                      <p className="text-[8px] text-zinc-600">Ready to place</p>
                    </div>
                  </button>
                ))}
              </div>

              {selectedItem && (
                <div className="border-t border-zinc-800/40 p-2 text-center text-[9px] text-zinc-500">
                  Click on the floor to place {selectedItem.name}
                </div>
              )}
            </>
          ) : (
            <div className="flex-1 space-y-2 overflow-y-auto p-1.5">
              <p className="px-1 text-[9px] text-zinc-600">Floor</p>
              <div className="grid grid-cols-2 gap-1">
                {MATERIALS.filter((material) => material.category === 'floor').map((material) => (
                  <button
                    key={material.id}
                    onClick={() => setFloorMat(material)}
                    className={`flex cursor-pointer items-center gap-1.5 rounded border px-2 py-1.5 text-left transition-colors ${
                      material.id === floorMat.id
                        ? 'border-blue-700/40 bg-blue-900/30'
                        : 'border-transparent hover:bg-zinc-800/40'
                    }`}
                  >
                    <span className="h-4 w-4 rounded-sm" style={{ background: material.color }} />
                    <span className="text-[9px] text-zinc-400">{material.name}</span>
                  </button>
                ))}
              </div>

              <p className="mt-2 px-1 text-[9px] text-zinc-600">Walls</p>
              <div className="grid grid-cols-2 gap-1">
                {MATERIALS.filter((material) => material.category === 'wall').map((material) => (
                  <button
                    key={material.id}
                    onClick={() => setWallMat(material)}
                    className={`flex cursor-pointer items-center gap-1.5 rounded border px-2 py-1.5 text-left transition-colors ${
                      material.id === wallMat.id
                        ? 'border-blue-700/40 bg-blue-900/30'
                        : 'border-transparent hover:bg-zinc-800/40'
                    }`}
                  >
                    <span className="h-4 w-4 rounded-sm" style={{ background: material.color }} />
                    <span className="text-[9px] text-zinc-400">{material.name}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {placed.length > 0 && (
            <div className="max-h-32 overflow-y-auto border-t border-zinc-800/40 p-1.5">
              <p className="mb-1 px-1 text-[8px] text-zinc-600">Placed ({placed.length})</p>
              {placed.map((item, index) => (
                <div
                  key={`${item.item.id}-${index}`}
                  className={`flex items-center justify-between rounded px-2 py-1 text-[9px] ${
                    selectedPlaced === index ? 'bg-zinc-800/60 text-zinc-300' : 'text-zinc-500'
                  }`}
                >
                  <span
                    className="cursor-pointer hover:text-zinc-300"
                    onClick={() => setSelectedPlaced(selectedPlaced === index ? -1 : index)}
                  >
                    {item.item.icon} {item.item.name}
                  </span>
                  <div className="flex gap-1">
                    <button
                      onClick={() => rotatePlaced(index)}
                      className="cursor-pointer hover:text-zinc-300"
                      title="Rotate"
                    >
                      Rotate
                    </button>
                    <button
                      onClick={() => {
                        removePlaced(index)
                        setSelectedPlaced(-1)
                      }}
                      className="cursor-pointer hover:text-red-400"
                      title="Remove"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="relative flex-1">
        <Canvas
          shadows
          dpr={[1, 2]}
          gl={{ antialias: true, alpha: false }}
          camera={{
            position: [center.x + camDist * 0.5, camDist * 0.6, center.z + camDist * 0.5],
            fov: 45,
            near: 1,
            far: camDist * 10,
          }}
        >
          <SceneRenderer camDist={camDist} />
          <Suspense fallback={null}>
            <SceneWorld center={center} floorBounds={floorBounds} />
          </Suspense>
          <SceneLighting center={center} floorBounds={floorBounds} camDist={camDist} />
          <SceneEffects />

          {walkMode ? (
            <WalkControls center={center} />
          ) : (
            <OrbitControls
              target={[center.x, WALL_HEIGHT * 0.3, center.z]}
              enableDamping
              dampingFactor={0.1}
              minDistance={camDist * 0.1}
              maxDistance={camDist * 3}
            />
          )}

          <FloorMesh
            floorBounds={floorBounds}
            material={floorMat}
            selectedItem={selectedItem}
            onPlace={(x, z) => {
              if (!selectedItem) return
              setPlaced((current) => [...current, { item: selectedItem, x, z, rotation: 0 }])
            }}
          />

          {fullscreen && (
            <Grid
              position={[center.x, 0.1, center.z]}
              args={[floorBounds.w, floorBounds.d]}
              cellSize={12}
              cellColor="#72809b"
              sectionSize={48}
              sectionColor="#8d9ab4"
              fadeDistance={camDist * 1.2}
              infiniteGrid={false}
            />
          )}

          {walls3D.map((wall) => (
            <WallMesh key={wall.id} wall={wall} material={wallMat} />
          ))}

          {openings3D.map((opening, index) => (
            <OpeningMesh key={`op-${index}`} opening={opening} />
          ))}

          {placed.map((item, index) => (
            <Suspense key={`${item.item.id}-${index}`} fallback={<FurnitureBoxFallback placed={item} />}>
              <FurnitureMesh
                placed={item}
                selected={selectedPlaced === index}
                onClick={() => setSelectedPlaced(selectedPlaced === index ? -1 : index)}
              />
            </Suspense>
          ))}
        </Canvas>

        <div className="absolute right-2 top-2 flex gap-1.5">
          {fullscreen && selectedPlaced >= 0 && (
            <>
              <button
                onClick={() => rotatePlaced(selectedPlaced)}
                className="cursor-pointer rounded border border-zinc-700/40 bg-zinc-800/80 px-2 py-1 text-[10px] text-zinc-400 hover:text-zinc-200"
              >
                Rotate
              </button>
              <button
                onClick={() => {
                  removePlaced(selectedPlaced)
                  setSelectedPlaced(-1)
                }}
                className="cursor-pointer rounded border border-red-700/40 bg-red-900/40 px-2 py-1 text-[10px] text-red-400 hover:text-red-300"
              >
                Remove
              </button>
            </>
          )}

          {fullscreen && (
            <button
              onClick={() => setWalkMode(!walkMode)}
              className={`cursor-pointer rounded border px-2 py-1 text-[10px] font-medium transition-colors ${
                walkMode
                  ? 'border-green-700/40 bg-green-900/50 text-green-300'
                  : 'border-zinc-700/40 bg-zinc-800/80 text-zinc-400 hover:text-zinc-200'
              }`}
            >
              {walkMode ? 'Walking (ESC to exit)' : 'Walk'}
            </button>
          )}

          <button
            onClick={() => {
              setFullscreen(!fullscreen)
              setSelectedItem(null)
              setSelectedPlaced(-1)
              setWalkMode(false)
            }}
            className="cursor-pointer rounded border border-zinc-700/40 bg-zinc-800/80 px-3 py-1 text-[10px] font-medium text-zinc-400 transition-colors hover:text-zinc-200"
          >
            {fullscreen ? 'Done' : 'Edit'}
          </button>
        </div>

        <div className="absolute bottom-2 left-2 text-[9px] text-zinc-600">
          {walkMode
            ? 'Click to lock mouse, use WASD to move, press ESC to unlock'
            : !fullscreen
              ? 'Click Edit to add furniture and materials'
              : null}
        </div>
      </div>
    </div>
  )
}

function FloorMesh({
  floorBounds,
  material,
  selectedItem,
  onPlace,
}: {
  floorBounds: FloorBounds
  material: MaterialPreset
  selectedItem: FurnitureItem | null
  onPlace: (x: number, z: number) => void
}) {
  const handleClick = useCallback(
    (event: ThreeEvent<MouseEvent>) => {
      if (!selectedItem) return
      event.stopPropagation()
      onPlace(event.point.x, event.point.z)
    },
    [selectedItem, onPlace],
  )

  return (
    <mesh
      position={[floorBounds.x, -0.5, floorBounds.z]}
      rotation={[-Math.PI / 2, 0, 0]}
      receiveShadow
      onClick={handleClick}
      onPointerOver={() => {
        if (selectedItem) document.body.style.cursor = 'crosshair'
      }}
      onPointerOut={() => {
        document.body.style.cursor = 'default'
      }}
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

function WallMesh({ wall, material }: { wall: Wall3D; material: MaterialPreset }) {
  return (
    <mesh position={[wall.x, wall.height / 2, wall.z]} castShadow receiveShadow>
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

function OpeningMesh({ opening }: { opening: Opening3D }) {
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

function FurnitureMesh({
  placed,
  selected,
  onClick,
}: {
  placed: PlacedFurniture
  selected: boolean
  onClick: () => void
}) {
  const { item, x, z, rotation } = placed

  return (
    <group
      position={[x, 0, z]}
      rotation={[0, rotation, 0]}
      onClick={(event) => {
        event.stopPropagation()
        onClick()
      }}
    >
      <GLBModel url={`/models/${item.glb}`} scale={item.scale} />
      {selected && (
        <mesh position={[0, item.scale * 0.5, 0]}>
          <boxGeometry args={[item.scale, item.scale, item.scale]} />
          <meshBasicMaterial color="#60a5fa" wireframe transparent opacity={0.4} toneMapped={false} />
        </mesh>
      )}
    </group>
  )
}

function FurnitureBoxFallback({ placed }: { placed: PlacedFurniture }) {
  const size = placed.item.scale * 0.3

  return (
    <mesh position={[placed.x, size / 2, placed.z]} castShadow receiveShadow>
      <boxGeometry args={[size, size, size]} />
      <meshStandardMaterial color="#666666" roughness={0.7} envMapIntensity={0.6} />
    </mesh>
  )
}
