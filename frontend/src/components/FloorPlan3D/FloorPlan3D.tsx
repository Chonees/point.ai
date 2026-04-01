import { useState, useMemo, useRef, useCallback, Suspense } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Grid, useGLTF } from '@react-three/drei'
import { WalkControls } from './WalkControls'
import type { Wall3D, Opening3D } from './structureTo3D'
import { FURNITURE, MATERIALS, CATEGORIES } from './catalog'
import type { Annotation } from '../../types'
import type { FurnitureItem, MaterialPreset } from './catalog'

const WALL_HEIGHT = 96

interface PlacedFurniture {
  item: FurnitureItem
  x: number; z: number
  rotation: number
}

function GLBModel({ url, scale }: { url: string; scale: number }) {
  const { scene } = useGLTF(url)
  const cloned = useMemo(() => scene.clone(), [scene])
  return <primitive object={cloned} scale={[scale, scale, scale]} />
}

export default function FloorPlan3D({ structure, annotations = [] }: { structure: Record<string, unknown>; annotations?: Annotation[] }) {
  // Build 3D scene ONLY from annotations (the editable 2D elements)
  const { walls3D, openings3D, floorBounds, center } = useMemo(() => {
    const meta = (structure.structure_meta as any) || {}
    const rp = meta.dxf_region_plan || {}
    const rpMeta = rp.meta || {}
    const transform = rpMeta.transform || {}
    const imageShape = rpMeta.image_shape || {}
    const imgH = Number(imageShape.height || 0)
    const sc = Number(transform.scale || 1)
    const offX = Number(transform.offset_x || 0)
    const offY = Number(transform.offset_y || 0)

    const toDxf = (ix: number, iy: number) => ({
      x: ix * sc + offX,
      y: (imgH - iy) * sc + offY,
    })

    const walls: Wall3D[] = []
    const openings: Opening3D[] = []
    let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity
    const track = (x: number, z: number) => {
      if (x < minX) minX = x; if (x > maxX) maxX = x
      if (z < minZ) minZ = z; if (z > maxZ) maxZ = z
    }

    for (const a of annotations) {
      if (a.type === 'eraser') continue
      const p1 = toDxf(a.x1, a.y1)
      const p2 = toDxf(a.x2, a.y2)
      const cx = (p1.x + p2.x) / 2
      const cz = -(p1.y + p2.y) / 2
      const adx = Math.abs(p2.x - p1.x)
      const ady = Math.abs(p2.y - p1.y)
      const isH = adx >= ady
      const span = Math.sqrt(adx * adx + ady * ady)

      if (a.type === 'wall') {
        const thickness = 4 * sc
        const w = isH ? span : thickness
        const d = isH ? thickness : span
        track(cx - w / 2, cz - d / 2)
        track(cx + w / 2, cz + d / 2)
        walls.push({
          id: `w-${walls.length}`,
          x: cx, z: cz, width: w, depth: d,
          height: WALL_HEIGHT, isExterior: false,
        })
      } else if ((a.type === 'door' || a.type === 'window') && a.swing) {
        track(cx, cz)
        openings.push({
          kind: a.type,
          x: cx, z: cz,
          width: isH ? span : 4,
          depth: isH ? 4 : span,
          height: a.type === 'door' ? 80 : 36,
          windowHeight: a.type === 'window' ? 36 : undefined,
        })
      }
    }

    if (minX === Infinity) { minX = -100; maxX = 100; minZ = -100; maxZ = 100 }
    const pad = 30
    const fx = (minX + maxX) / 2, fz = (minZ + maxZ) / 2
    const fw = maxX - minX + pad * 2, fd = maxZ - minZ + pad * 2
    return {
      walls3D: walls,
      openings3D: openings,
      floorBounds: { x: fx, z: fz, w: fw, d: fd },
      center: { x: fx, z: fz },
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
  const [wallMat, setWallMat] = useState<MaterialPreset>(MATERIALS.find(m => m.category === 'wall')!)
  const [selectedPlaced, setSelectedPlaced] = useState<number>(-1)

  const removePlaced = (idx: number) => setPlaced(p => p.filter((_, i) => i !== idx))
  const rotatePlaced = (idx: number) => setPlaced(p => p.map((f, i) => i === idx ? { ...f, rotation: f.rotation + Math.PI / 2 } : f))

  const containerClass = fullscreen
    ? 'fixed inset-0 z-50 flex bg-zinc-950'
    : 'w-full h-80 sm:h-96 rounded-lg overflow-hidden bg-zinc-950 border border-zinc-800/40 relative'

  return (
    <div className={containerClass}>
      {/* Sidebar — only in fullscreen */}
      {fullscreen && (
        <div className="w-56 flex-shrink-0 bg-zinc-900 border-r border-zinc-800/60 flex flex-col overflow-hidden">
          {/* Tabs */}
          <div className="flex border-b border-zinc-800/40">
            <button onClick={() => setTab('furniture')}
              className={`flex-1 py-2 text-[10px] font-medium cursor-pointer transition-colors
                ${tab === 'furniture' ? 'text-zinc-200 bg-zinc-800/40' : 'text-zinc-500 hover:text-zinc-400'}`}>
              Furniture
            </button>
            <button onClick={() => setTab('materials')}
              className={`flex-1 py-2 text-[10px] font-medium cursor-pointer transition-colors
                ${tab === 'materials' ? 'text-zinc-200 bg-zinc-800/40' : 'text-zinc-500 hover:text-zinc-400'}`}>
              Materials
            </button>
          </div>

          {tab === 'furniture' ? (
            <>
              {/* Category pills */}
              <div className="flex flex-wrap gap-1 p-2 border-b border-zinc-800/30">
                {CATEGORIES.map(c => (
                  <button key={c} onClick={() => setCategory(c)}
                    className={`px-2 py-0.5 rounded text-[9px] cursor-pointer transition-colors
                      ${c === category ? 'bg-zinc-700 text-zinc-200' : 'bg-zinc-800/40 text-zinc-500 hover:text-zinc-400'}`}>
                    {c}
                  </button>
                ))}
              </div>
              {/* Items */}
              <div className="flex-1 overflow-y-auto p-1.5 space-y-0.5">
                {FURNITURE.filter(f => f.category === category).map(item => (
                  <button key={item.id} onClick={() => setSelectedItem(selectedItem?.id === item.id ? null : item)}
                    className={`w-full flex items-center gap-2 px-2 py-1.5 rounded text-left cursor-pointer transition-colors
                      ${selectedItem?.id === item.id ? 'bg-blue-900/30 border border-blue-700/40' : 'hover:bg-zinc-800/40 border border-transparent'}`}>
                    <span className="text-sm">{item.icon}</span>
                    <div>
                      <p className="text-[10px] text-zinc-300">{item.name}</p>
                      <p className="text-[8px] text-zinc-600">{item.width}"×{item.depth}"</p>
                    </div>
                  </button>
                ))}
              </div>
              {selectedItem && (
                <div className="p-2 border-t border-zinc-800/40 text-[9px] text-zinc-500 text-center">
                  Click on floor to place {selectedItem.name}
                </div>
              )}
            </>
          ) : (
            <div className="flex-1 overflow-y-auto p-1.5 space-y-2">
              <p className="text-[9px] text-zinc-600 px-1">Floor</p>
              <div className="grid grid-cols-2 gap-1">
                {MATERIALS.filter(m => m.category === 'floor').map(m => (
                  <button key={m.id} onClick={() => setFloorMat(m)}
                    className={`flex items-center gap-1.5 px-2 py-1.5 rounded text-left cursor-pointer transition-colors
                      ${m.id === floorMat.id ? 'bg-blue-900/30 border border-blue-700/40' : 'hover:bg-zinc-800/40 border border-transparent'}`}>
                    <span className="w-4 h-4 rounded-sm" style={{ background: m.color }} />
                    <span className="text-[9px] text-zinc-400">{m.name}</span>
                  </button>
                ))}
              </div>
              <p className="text-[9px] text-zinc-600 px-1 mt-2">Walls</p>
              <div className="grid grid-cols-2 gap-1">
                {MATERIALS.filter(m => m.category === 'wall').map(m => (
                  <button key={m.id} onClick={() => setWallMat(m)}
                    className={`flex items-center gap-1.5 px-2 py-1.5 rounded text-left cursor-pointer transition-colors
                      ${m.id === wallMat.id ? 'bg-blue-900/30 border border-blue-700/40' : 'hover:bg-zinc-800/40 border border-transparent'}`}>
                    <span className="w-4 h-4 rounded-sm" style={{ background: m.color }} />
                    <span className="text-[9px] text-zinc-400">{m.name}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Placed items list */}
          {placed.length > 0 && (
            <div className="border-t border-zinc-800/40 p-1.5 max-h-32 overflow-y-auto">
              <p className="text-[8px] text-zinc-600 px-1 mb-1">Placed ({placed.length})</p>
              {placed.map((p, i) => (
                <div key={i} className={`flex items-center justify-between px-2 py-1 rounded text-[9px]
                  ${selectedPlaced === i ? 'bg-zinc-800/60 text-zinc-300' : 'text-zinc-500'}`}>
                  <span className="cursor-pointer hover:text-zinc-300" onClick={() => setSelectedPlaced(selectedPlaced === i ? -1 : i)}>
                    {p.item.icon} {p.item.name}
                  </span>
                  <div className="flex gap-1">
                    <button onClick={() => rotatePlaced(i)} className="hover:text-zinc-300 cursor-pointer" title="Rotate">↻</button>
                    <button onClick={() => { removePlaced(i); setSelectedPlaced(-1) }} className="hover:text-red-400 cursor-pointer" title="Remove">×</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 3D Canvas */}
      <div className="flex-1 relative">
        <Canvas
          camera={{
            position: [center.x + camDist * 0.5, camDist * 0.6, center.z + camDist * 0.5],
            fov: 45, near: 1, far: camDist * 10,
          }}
        >
          <ambientLight intensity={0.6} />
          <directionalLight position={[camDist, camDist * 1.5, camDist * 0.5]} intensity={0.8} />
          <hemisphereLight args={['#b1e1ff', '#b97a20', 0.3]} />

          {walkMode ? (
            <WalkControls center={center} />
          ) : (
            <OrbitControls
              target={[center.x, WALL_HEIGHT * 0.3, center.z]}
              enableDamping dampingFactor={0.1}
              minDistance={camDist * 0.1} maxDistance={camDist * 3}
            />
          )}

          {/* Floor */}
          <FloorMesh floorBounds={floorBounds} material={floorMat} selectedItem={selectedItem}
            onPlace={(x, z) => {
              if (selectedItem) {
                setPlaced([...placed, { item: selectedItem, x, z, rotation: 0 }])
              }
            }}
          />

          <Grid
            position={[center.x, 0.1, center.z]}
            args={[floorBounds.w, floorBounds.d]}
            cellSize={12} cellColor="#333333"
            sectionSize={48} sectionColor="#444444"
            fadeDistance={camDist * 2} infiniteGrid={false}
          />

          {/* Walls */}
          {/* Walls from annotations */}
          {walls3D.map(wall => (
            <WallMesh key={wall.id} wall={wall} material={wallMat} />
          ))}

          {/* Doors/windows from annotations */}
          {openings3D.map((op, i) => (
            <OpeningMesh key={`op-${i}`} opening={op} />
          ))}

          {/* Placed furniture */}
          {placed.map((p, i) => (
            <Suspense key={i} fallback={<FurnitureBoxFallback placed={p} />}>
              <FurnitureMesh placed={p} selected={selectedPlaced === i}
                onClick={() => setSelectedPlaced(selectedPlaced === i ? -1 : i)} />
            </Suspense>
          ))}
        </Canvas>

        {/* Edit / Done button */}
        <div className="absolute top-2 right-2 flex gap-1.5">
          {fullscreen && selectedPlaced >= 0 && (
            <>
              <button onClick={() => rotatePlaced(selectedPlaced)}
                className="px-2 py-1 rounded text-[10px] bg-zinc-800/80 border border-zinc-700/40 text-zinc-400 hover:text-zinc-200 cursor-pointer">
                ↻ Rotate
              </button>
              <button onClick={() => { removePlaced(selectedPlaced); setSelectedPlaced(-1) }}
                className="px-2 py-1 rounded text-[10px] bg-red-900/40 border border-red-700/40 text-red-400 hover:text-red-300 cursor-pointer">
                × Remove
              </button>
            </>
          )}
          {fullscreen && (
            <button onClick={() => setWalkMode(!walkMode)}
              className={`px-2 py-1 rounded text-[10px] font-medium border cursor-pointer transition-colors
                ${walkMode ? 'bg-green-900/50 border-green-700/40 text-green-300' : 'bg-zinc-800/80 border-zinc-700/40 text-zinc-400 hover:text-zinc-200'}`}>
              {walkMode ? '🚶 Walking (ESC to exit)' : '🚶 Walk'}
            </button>
          )}
          <button onClick={() => { setFullscreen(!fullscreen); setSelectedItem(null); setSelectedPlaced(-1); setWalkMode(false) }}
            className="px-3 py-1 rounded text-[10px] font-medium bg-zinc-800/80 border border-zinc-700/40
                       text-zinc-400 hover:text-zinc-200 cursor-pointer transition-colors">
            {fullscreen ? 'Done' : 'Edit'}
          </button>
        </div>

        {/* Hint */}
        <div className="absolute bottom-2 left-2 text-[9px] text-zinc-600">
          {walkMode ? 'Click to lock mouse · WASD to move · ESC to unlock' :
           !fullscreen ? 'Click Edit to add furniture & materials' : null}
        </div>
      </div>
    </div>
  )
}

// ─── Sub-components ──────────────────────────────────────────────────

function FloorMesh({ floorBounds, material, selectedItem, onPlace }: {
  floorBounds: { x: number; z: number; w: number; d: number }
  material: MaterialPreset
  selectedItem: FurnitureItem | null
  onPlace: (x: number, z: number) => void
}) {
  const handleClick = useCallback((e: any) => {
    if (!selectedItem) return
    e.stopPropagation()
    onPlace(e.point.x, e.point.z)
  }, [selectedItem, onPlace])

  return (
    <mesh position={[floorBounds.x, -0.5, floorBounds.z]}
      rotation={[-Math.PI / 2, 0, 0]} receiveShadow onClick={handleClick}
      onPointerOver={() => { if (selectedItem) document.body.style.cursor = 'crosshair' }}
      onPointerOut={() => { document.body.style.cursor = 'default' }}
    >
      <planeGeometry args={[floorBounds.w, floorBounds.d]} />
      <meshStandardMaterial color={material.color} roughness={material.roughness} />
    </mesh>
  )
}

function WallMesh({ wall, material }: { wall: Wall3D; material: MaterialPreset }) {
  return (
    <mesh position={[wall.x, wall.height / 2, wall.z]} castShadow receiveShadow>
      <boxGeometry args={[wall.width, wall.height, wall.depth]} />
      <meshStandardMaterial color={material.color} roughness={material.roughness} />
    </mesh>
  )
}

function OpeningMesh({ opening }: { opening: Opening3D }) {
  if (opening.kind === 'window') {
    const winBottom = opening.windowHeight || 36
    return (
      <mesh position={[opening.x, winBottom + opening.height / 2, opening.z]}>
        <boxGeometry args={[opening.width + 1, opening.height, opening.depth + 1]} />
        <meshPhysicalMaterial color="#88ccff" transparent opacity={0.25} roughness={0.05} metalness={0.1} />
      </mesh>
    )
  }
  return (
    <mesh position={[opening.x, opening.height / 2, opening.z]}>
      <boxGeometry args={[opening.width, opening.height, 1.5]} />
      <meshStandardMaterial color="#8B6914" roughness={0.7} />
    </mesh>
  )
}

function FurnitureMesh({ placed, selected, onClick }: {
  placed: PlacedFurniture; selected: boolean; onClick: () => void
}) {
  const { item, x, z, rotation } = placed
  return (
    <group position={[x, 0, z]} rotation={[0, rotation, 0]} onClick={(e) => { e.stopPropagation(); onClick() }}>
      <GLBModel url={`/models/${item.glb}`} scale={item.scale} />
      {selected && (
        <mesh position={[0, item.scale * 0.5, 0]}>
          <boxGeometry args={[item.scale, item.scale, item.scale]} />
          <meshBasicMaterial color="#4488ff" wireframe transparent opacity={0.4} />
        </mesh>
      )}
    </group>
  )
}

function FurnitureBoxFallback({ placed }: { placed: PlacedFurniture }) {
  const s = placed.item.scale * 0.3
  return (
    <mesh position={[placed.x, s / 2, placed.z]}>
      <boxGeometry args={[s, s, s]} />
      <meshStandardMaterial color="#666" />
    </mesh>
  )
}
