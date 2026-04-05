import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, type ThreeEvent, useThree } from '@react-three/fiber'
import { Environment, Grid, OrbitControls, Sky, calcPosFromAngles, useGLTF } from '@react-three/drei'
import { Bloom, EffectComposer, SSAO, ToneMapping } from '@react-three/postprocessing'
import { ToneMappingMode } from 'postprocessing'
import * as THREE from 'three'

import { WalkControls } from './WalkControls'
import { FurnitureSidebar } from './FurnitureSidebar'
import type { Opening3D, Wall3D } from './structureTo3D'
import { MATERIALS } from './catalog'
import type { FurnitureItem, MaterialPreset } from './catalog'
import { FURNITURE } from './catalog'
import type { Annotation } from '../../types'
import type { PlanScene } from '../../hooks/useProject'
import type { PlacedItemDB } from '../../lib/database.types'

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const WALL_HEIGHT = 96
const BACKGROUND_COLOR = '#dbeaf7'
const SKY_INCLINATION = 0.56
const SKY_AZIMUTH = 0.18
const SKY_DISTANCE = 4500

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface FloorBounds {
  x: number; z: number; w: number; d: number
}

interface PlacedFurniture {
  item: FurnitureItem
  x: number
  y: number
  z: number
  rotation: number
  scaleW: number  // width (X axis)
  scaleD: number  // depth (Z axis)
  scaleH: number  // height (Y axis)
  tintColor?: string
}

/* ------------------------------------------------------------------ */
/*  GLB model with optional color tint                                 */
/* ------------------------------------------------------------------ */

function tuneSceneMaterial(material: THREE.Material) {
  if ('envMapIntensity' in material) {
    const shaded = material as THREE.MeshStandardMaterial
    shaded.envMapIntensity = 1.2
    shaded.needsUpdate = true
  }
}

function GLBModel({ url, scale, tintColor }: { url: string; scale: number; tintColor?: string }) {
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

        // Apply color tint by multiplying with existing color
        if (tintColor && 'color' in next) {
          const std = next as THREE.MeshStandardMaterial
          const tint = new THREE.Color(tintColor)
          // Blend: mix original color with tint (70% tint, 30% original for strong effect)
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

/* ------------------------------------------------------------------ */
/*  Scene helpers                                                      */
/* ------------------------------------------------------------------ */

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
        <meshStandardMaterial vertexColors roughness={1} metalness={0} envMapIntensity={0.18} />
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

/* ------------------------------------------------------------------ */
/*  Building meshes                                                    */
/* ------------------------------------------------------------------ */

/** Hit info passed from surfaces */
interface SurfaceHit {
  x: number; y: number; z: number
  /** Face normal in world space — null for floor hits */
  normal: THREE.Vector3 | null
}

/** Shared placement callbacks — used by FloorMesh and WallMesh */
interface PlacementSurface {
  selectedItem: FurnitureItem | null
  onPointerMove: (hit: SurfaceHit) => void
  onPointerLeave: () => void
}

function extractHit(event: ThreeEvent<MouseEvent> | ThreeEvent<PointerEvent>): SurfaceHit {
  let normal: THREE.Vector3 | null = null
  if (event.face && event.object) {
    // Transform face normal from object space to world space
    normal = event.face.normal.clone()
      .applyQuaternion(event.object.getWorldQuaternion(new THREE.Quaternion()))
  }
  return { x: event.point.x, y: event.point.y, z: event.point.z, normal }
}

function usePlacementHandlers({ selectedItem, onPointerMove, onPointerLeave }: PlacementSurface) {
  const handleClick = useCallback(
    (_event: ThreeEvent<MouseEvent>) => {
      // Placement is done via E key, not click
    },
    [],
  )
  const handlePointerMove = useCallback(
    (event: ThreeEvent<PointerEvent>) => {
      if (!selectedItem) return
      onPointerMove(extractHit(event))
    },
    [selectedItem, onPointerMove],
  )
  const handlePointerOver = useCallback(() => {
    if (selectedItem) document.body.style.cursor = 'crosshair'
  }, [selectedItem])
  const handlePointerOut = useCallback(() => {
    document.body.style.cursor = 'default'
    onPointerLeave()
  }, [onPointerLeave])

  return { handleClick, handlePointerMove, handlePointerOver, handlePointerOut }
}

/** Convert a wall face normal to a Y-axis rotation so the item faces outward */
function normalToRotation(normal: THREE.Vector3): number {
  // normal points outward from wall face
  // atan2 gives us the angle in the XZ plane
  return Math.atan2(normal.x, normal.z)
}

function FloorMesh({
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

/** Ghost preview: transparent model + ground ring + height pole following the cursor */
function GhostPreview({
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
      {/* Ground ring indicator (always on floor) */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.2, 0]}>
        <ringGeometry args={[item.scale * 0.3, item.scale * 0.35, 48]} />
        <meshBasicMaterial color="#3b82f6" transparent opacity={0.6} toneMapped={false} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.15, 0]}>
        <circleGeometry args={[item.scale * 0.05, 16]} />
        <meshBasicMaterial color="#60a5fa" transparent opacity={0.8} toneMapped={false} />
      </mesh>

      {/* Vertical pole from floor to item (shows height) */}
      {y > 0 && (
        <mesh position={[0, y / 2, 0]}>
          <cylinderGeometry args={[0.3, 0.3, y, 8]} />
          <meshBasicMaterial color="#3b82f6" transparent opacity={0.3} toneMapped={false} />
        </mesh>
      )}

      {/* Ghost model at height */}
      <group position={[0, y, 0]} rotation={[0, rotation, 0]}>
        <group rotation={item.wallMount ? [-Math.PI / 2, 0, 0] : [0, 0, 0]}>
          <primitive object={cloned} scale={[item.scale * scaleW, item.scale * scaleH, item.scale * scaleD]} />
        </group>
      </group>
    </group>
  )
}

function WallMesh({
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

/* ------------------------------------------------------------------ */
/*  Furniture meshes                                                   */
/* ------------------------------------------------------------------ */

function FurnitureMesh({
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
      // When placing new items, let pointer events pass through to the floor
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

function FurnitureBoxFallback({ placed }: { placed: PlacedFurniture }) {
  const size = placed.item.scale * 0.3
  return (
    <mesh position={[placed.x, size / 2, placed.z]} castShadow receiveShadow>
      <boxGeometry args={[size, size, size]} />
      <meshStandardMaterial color="#666666" roughness={0.7} envMapIntensity={0.6} />
    </mesh>
  )
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

export default function FloorPlan3D({
  structure,
  annotations = [],
  initialScene,
  onSceneChange,
}: {
  structure: Record<string, unknown>
  annotations?: Annotation[]
  initialScene?: PlanScene
  onSceneChange?: (scene: PlanScene) => void
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
      }
      // Doors/windows disabled in 3D — not yet producing correct results
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

  // Convert DB format to runtime format
  const dbToPlaced = (items: PlacedItemDB[]): PlacedFurniture[] =>
    items.map((db) => {
      const catalogItem = FURNITURE.find((f) => f.id === db.itemId)
      if (!catalogItem) return null
      return { item: catalogItem, x: db.x, y: db.y, z: db.z, rotation: db.rotation, scaleW: db.scaleW, scaleD: db.scaleD, scaleH: db.scaleH ?? 1, tintColor: db.tintColor }
    }).filter(Boolean) as PlacedFurniture[]

  const placedToDb = (items: PlacedFurniture[]): PlacedItemDB[] =>
    items.map((p) => ({ itemId: p.item.id, x: p.x, y: p.y, z: p.z, rotation: p.rotation, scaleW: p.scaleW, scaleD: p.scaleD, scaleH: p.scaleH, tintColor: p.tintColor }))

  /* State */
  const [fullscreen, setFullscreen] = useState(false)
  const [walkMode, setWalkMode] = useState(false)
  const [tab, setTab] = useState<'furniture' | 'materials'>('furniture')
  const [selectedItem, setSelectedItem] = useState<FurnitureItem | null>(null)
  const [placed, setPlaced] = useState<PlacedFurniture[]>(() =>
    initialScene?.placedItems3d ? dbToPlaced(initialScene.placedItems3d) : [],
  )
  const [floorMat, setFloorMat] = useState<MaterialPreset>(() =>
    MATERIALS.find((m) => m.id === initialScene?.floorMaterial) ?? MATERIALS[0],
  )
  const [wallMat, setWallMat] = useState<MaterialPreset>(() =>
    MATERIALS.find((m) => m.id === initialScene?.wallMaterial) ??
    MATERIALS.find((m) => m.category === 'wall') ?? MATERIALS[0],
  )

  // Auto-save: notify parent when 3D state changes
  useEffect(() => {
    if (!onSceneChange) return
    onSceneChange({
      annotations2d: annotations,
      placedItems3d: placedToDb(placed),
      floorMaterial: floorMat.id,
      wallMaterial: wallMat.id,
    })
  }, [placed, floorMat, wallMat]) // eslint-disable-line react-hooks/exhaustive-deps
  const [selectedPlaced, setSelectedPlaced] = useState(-1)
  const [ghostPos, setGhostPos] = useState<{ x: number; y: number; z: number; wallRotation: number | null } | null>(null)
  const [ghostRotation, setGhostRotation] = useState(0)
  const [ghostHeight, setGhostHeight] = useState(0)
  const [ghostScaleW, setGhostScaleW] = useState(1)
  const [ghostScaleD, setGhostScaleD] = useState(1)
  const [ghostScaleH, setGhostScaleH] = useState(1)

  const removePlaced = (index: number) => {
    setPlaced((cur) => cur.filter((_, i) => i !== index))
    if (selectedPlaced === index) setSelectedPlaced(-1)
  }
  const rotatePlaced = (index: number) =>
    setPlaced((cur) =>
      cur.map((f, i) =>
        i === index ? { ...f, rotation: f.rotation + Math.PI / 2 } : f,
      ),
    )
  const setPlacedTint = (index: number, color: string | undefined) =>
    setPlaced((cur) =>
      cur.map((f, i) => (i === index ? { ...f, tintColor: color } : f)),
    )
  // Pick up a placed item: remove it and set it as the active ghost to re-place
  const pickUpPlaced = (index: number) => {
    const p = placed[index]
    if (!p) return
    setSelectedItem(p.item)
    setGhostRotation(p.rotation)
    setGhostHeight(p.y)
    setGhostScaleW(p.scaleW)
    setGhostScaleD(p.scaleD)
    setGhostScaleH(p.scaleH)
    setPlaced((cur) => cur.filter((_, i) => i !== index))
    setSelectedPlaced(-1)
  }

  // Modifier+scroll for size/height — must block OrbitControls zoom
  const canvasContainerRef = useRef<HTMLDivElement>(null)
  const selectedItemRef = useRef(selectedItem)
  selectedItemRef.current = selectedItem
  const ghostPosRef = useRef(ghostPos)
  ghostPosRef.current = ghostPos
  const ghostRotationRef = useRef(ghostRotation)
  ghostRotationRef.current = ghostRotation
  const ghostHeightRef = useRef(ghostHeight)
  ghostHeightRef.current = ghostHeight
  const ghostScaleWRef = useRef(ghostScaleW)
  ghostScaleWRef.current = ghostScaleW
  const ghostScaleDRef = useRef(ghostScaleD)
  ghostScaleDRef.current = ghostScaleD
  const ghostScaleHRef = useRef(ghostScaleH)
  ghostScaleHRef.current = ghostScaleH
  const selectedPlacedRef = useRef(selectedPlaced)
  selectedPlacedRef.current = selectedPlaced

  // Keyboard controls: place (E), rotate (arrows when placing), move (arrows when selected)
  const handlePlaceKey = useCallback((e: React.KeyboardEvent) => {
    if ((e.target as HTMLElement)?.tagName === 'INPUT') return

    // --- Placing new item ---
    if (selectedItem) {
      if (e.key === 'ArrowLeft') { e.preventDefault(); setGhostRotation((r) => r - Math.PI / 12); return }
      if (e.key === 'ArrowRight') { e.preventDefault(); setGhostRotation((r) => r + Math.PI / 12); return }
      if ((e.key === 'e' || e.key === 'E') && ghostPos) {
        e.preventDefault()
        const rot = (ghostPos.wallRotation ?? 0) + ghostRotation
        setPlaced((cur) => {
          const next = [...cur, {
            item: selectedItem,
            x: ghostPos.x,
            y: ghostHeight > 0 ? ghostHeight : ghostPos.y,
            z: ghostPos.z,
            rotation: rot,
            scaleW: ghostScaleW,
            scaleD: ghostScaleD,
            scaleH: ghostScaleH,
          }]
          // Select the just-placed item so color picker shows
          setSelectedPlaced(next.length - 1)
          return next
        })
        // Deselect the catalog item so we exit placement mode
        setSelectedItem(null)
      }
      return
    }

  }, [selectedItem, ghostPos, ghostRotation, ghostHeight, ghostScaleW, ghostScaleD, ghostScaleH])

  // Modifier+scroll and right-click
  useEffect(() => {
    const handleWheel = (e: WheelEvent) => {
      if (!selectedItemRef.current) return
      if (e.shiftKey) {
        e.preventDefault()
        e.stopImmediatePropagation()
        setGhostHeight((h) => Math.max(0, h + (e.deltaY < 0 ? 4 : -4)))
      } else if (e.ctrlKey) {
        e.preventDefault()
        e.stopImmediatePropagation()
        setGhostScaleW((s) => Math.max(0.1, Math.min(5, s + (e.deltaY < 0 ? 0.02 : -0.02))))
      } else if (e.altKey) {
        e.preventDefault()
        e.stopImmediatePropagation()
        setGhostScaleD((s) => Math.max(0.1, Math.min(5, s + (e.deltaY < 0 ? 0.02 : -0.02))))
      }
    }
    const handleContext = (e: MouseEvent) => {
      if (!selectedItemRef.current) return
      e.preventDefault()
      setGhostRotation((r) => r + Math.PI / 12)
    }
    const handleKey = (e: KeyboardEvent) => {
      if (!selectedItemRef.current) return
      if ((e.target as HTMLElement)?.tagName === 'INPUT') return
      if (e.key === 'ArrowUp') { e.preventDefault(); setGhostScaleH((s) => Math.min(5, s + 0.02)) }
      if (e.key === 'ArrowDown') { e.preventDefault(); setGhostScaleH((s) => Math.max(0.1, s - 0.02)) }
    }
    document.addEventListener('wheel', handleWheel, { passive: false, capture: true })
    document.addEventListener('contextmenu', handleContext)
    document.addEventListener('keydown', handleKey, { capture: true })
    return () => {
      document.removeEventListener('wheel', handleWheel, { capture: true })
      document.removeEventListener('contextmenu', handleContext)
      document.removeEventListener('keydown', handleKey, { capture: true })
    }
  }, [])

  // Reset ghost when selecting a new item
  useEffect(() => {
    setGhostRotation(0)
    setGhostHeight(0)
    setGhostScaleW(1)
    setGhostScaleD(1)
    setGhostScaleH(1)
    setGhostPos(null)
  }, [selectedItem])

  // Grid snap — fine grid for precise placement
  const GRID_SIZE = 3
  const snap = (v: number) => Math.round(v / GRID_SIZE) * GRID_SIZE
  const snapY = (v: number) => Math.round(v / 2) * 2

  // Shared placement props for floor + walls
  const placementProps: PlacementSurface = {
    selectedItem,
    onPointerMove: (hit) => {
      const isWallHit = hit.normal && Math.abs(hit.normal.y) < 0.5
      const wallRot = isWallHit && hit.normal ? normalToRotation(hit.normal) : null
      if (isWallHit && hit.normal) {
        // Snap along the wall, but keep exact position on the perpendicular axis (flush to surface)
        const nx = Math.abs(hit.normal.x)
        const nz = Math.abs(hit.normal.z)
        setGhostPos({
          x: nx > 0.5 ? hit.x : snap(hit.x),  // if normal is X, keep X exact
          y: snapY(hit.y),
          z: nz > 0.5 ? hit.z : snap(hit.z),  // if normal is Z, keep Z exact
          wallRotation: wallRot,
        })
      } else {
        setGhostPos({
          x: snap(hit.x),
          y: snapY(hit.y),
          z: snap(hit.z),
          wallRotation: null,
        })
      }
    },
    onPointerLeave: () => setGhostPos(null),
  }

  const containerClass = fullscreen
    ? 'fixed inset-0 z-50 flex bg-zinc-950'
    : 'relative h-80 w-full overflow-hidden rounded-lg border border-zinc-800/40 bg-zinc-950 sm:h-96'

  return (
    <div className={containerClass} tabIndex={0} onKeyDown={handlePlaceKey} style={{ outline: 'none' }}>
      {/* Sidebar */}
      {fullscreen && (
        <FurnitureSidebar
          tab={tab}
          setTab={setTab}
          selectedItem={selectedItem}
          setSelectedItem={setSelectedItem}
          placed={placed}
          selectedPlaced={selectedPlaced}
          setSelectedPlaced={setSelectedPlaced}
          rotatePlaced={rotatePlaced}
          removePlaced={removePlaced}
          setPlacedTint={setPlacedTint}
          floorMat={floorMat}
          setFloorMat={setFloorMat}
          wallMat={wallMat}
          setWallMat={setWallMat}
        />
      )}

      {/* 3D Canvas */}
      <div ref={canvasContainerRef} className="relative flex-1">
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
            {...placementProps}
          />

          {/* Ghost preview following cursor */}
          {selectedItem && ghostPos && (
            <Suspense fallback={null}>
              <GhostPreview
                item={selectedItem}
                x={ghostPos.x}
                y={ghostHeight > 0 ? ghostHeight : ghostPos.y}
                z={ghostPos.z}
                rotation={(ghostPos.wallRotation ?? 0) + ghostRotation}
                scaleW={ghostScaleW}
                scaleD={ghostScaleD}
                scaleH={ghostScaleH}
              />
            </Suspense>
          )}

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
            <WallMesh key={wall.id} wall={wall} material={wallMat} {...placementProps} />
          ))}

          {/* Doors/windows disabled in 3D */}
          {false && openings3D.map((opening, index) => (
            <OpeningMesh key={`op-${index}`} opening={opening} />
          ))}

          {placed.map((item, index) => (
            <Suspense key={`${item.item.id}-${index}`} fallback={<FurnitureBoxFallback placed={item} />}>
              <FurnitureMesh
                placed={item}
                selected={selectedPlaced === index}
                placing={!!selectedItem}
                onClick={() => pickUpPlaced(index)}
              />
            </Suspense>
          ))}
        </Canvas>

        {/* Top-right controls */}
        <div className="absolute right-3 top-3 flex gap-2">
          {fullscreen && selectedPlaced >= 0 && (
            <>
              <button
                onClick={() => rotatePlaced(selectedPlaced)}
                className="cursor-pointer rounded-md border border-zinc-700/40 bg-zinc-800/90 px-3 py-1.5 text-[11px] font-medium text-zinc-400 backdrop-blur-sm hover:text-zinc-200"
              >
                Rotate
              </button>
              <button
                onClick={() => removePlaced(selectedPlaced)}
                className="cursor-pointer rounded-md border border-red-700/40 bg-red-900/50 px-3 py-1.5 text-[11px] font-medium text-red-400 backdrop-blur-sm hover:text-red-300"
              >
                Remove
              </button>
            </>
          )}

          {fullscreen && (
            <button
              onClick={() => setWalkMode(!walkMode)}
              className={`cursor-pointer rounded-md border px-3 py-1.5 text-[11px] font-medium backdrop-blur-sm transition-colors ${
                walkMode
                  ? 'border-green-600/40 bg-green-900/60 text-green-300'
                  : 'border-zinc-700/40 bg-zinc-800/90 text-zinc-400 hover:text-zinc-200'
              }`}
            >
              {walkMode ? 'Walking (ESC)' : 'Walk'}
            </button>
          )}

          <button
            onClick={() => {
              setFullscreen(!fullscreen)
              setSelectedItem(null)
              setSelectedPlaced(-1)
              setWalkMode(false)
            }}
            className="cursor-pointer rounded-md border border-zinc-700/40 bg-zinc-800/90 px-4 py-1.5 text-[11px] font-semibold text-zinc-400 backdrop-blur-sm transition-colors hover:text-zinc-200"
          >
            {fullscreen ? 'Done' : 'Edit'}
          </button>
        </div>

        {/* Bottom hint */}
        <div className="absolute bottom-3 left-3 text-[10px] text-zinc-600">
          {walkMode
            ? 'Click to lock mouse, WASD to move, ESC to unlock'
            : selectedItem
              ? (
                <div className="flex items-center gap-3 rounded-md border border-zinc-700/40 bg-zinc-900/90 px-3 py-2 backdrop-blur-sm">
                  <span className="text-zinc-400">E to place</span>
                  <span className="text-zinc-600">|</span>
                  <span><span className="text-zinc-400">← →</span> rotate</span>
                  <span className="text-zinc-600">|</span>
                  <span><span className="text-zinc-400">Ctrl+Scroll</span> width</span>
                  <span className="text-zinc-600">|</span>
                  <span><span className="text-zinc-400">Alt+Scroll</span> depth</span>
                  <span className="text-zinc-600">|</span>
                  <span><span className="text-zinc-400">↑ ↓</span> height</span>
                  <span className="text-zinc-600">|</span>
                  <span><span className="text-zinc-400">Shift+Scroll</span> elevate</span>
                  {(ghostHeight > 0 || ghostScaleW !== 1 || ghostScaleD !== 1 || ghostScaleH !== 1) && (
                    <>
                      <span className="text-zinc-600">|</span>
                      <span className="text-blue-400">
                        {ghostScaleW !== 1 && `W:${Math.round(ghostScaleW * 100)}%`}
                        {ghostScaleW !== 1 && (ghostScaleD !== 1 || ghostScaleH !== 1) && ' '}
                        {ghostScaleD !== 1 && `D:${Math.round(ghostScaleD * 100)}%`}
                        {ghostScaleD !== 1 && ghostScaleH !== 1 && ' '}
                        {ghostScaleH !== 1 && `H:${Math.round(ghostScaleH * 100)}%`}
                        {(ghostScaleW !== 1 || ghostScaleD !== 1 || ghostScaleH !== 1) && ghostHeight > 0 && ' · '}
                        {ghostHeight > 0 && `h: ${Math.round(ghostHeight)}`}
                      </span>
                    </>
                  )}
                </div>
              )
              : !fullscreen
                ? 'Click Edit to add furniture and materials'
                : null}
        </div>
      </div>
    </div>
  )
}
