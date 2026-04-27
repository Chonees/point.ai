import { Suspense, useMemo, useRef, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import { Grid, OrbitControls } from '@react-three/drei'

import { WalkControls } from './WalkControls'
import { FurnitureSidebar } from './FurnitureSidebar'
import type { FurnitureItem, MaterialPreset } from './catalog'
import type { PlanScene } from '../../hooks/useProject'
import type { PlacedFurniture } from './types'

import { SceneRenderer, SceneEffects } from './scene/SceneRenderer'
import { SceneWorld } from './scene/SceneWorld'
import { SceneLighting } from './scene/SceneLighting'
import { FloorMesh } from './meshes/FloorMesh'
import { WallMesh } from './meshes/WallMesh'
import { OpeningMesh } from './meshes/OpeningMesh'
import { FurnitureMesh, FurnitureBoxFallback } from './meshes/FurnitureMesh'
import { GhostPreview } from './meshes/GhostPreview'
import { structureTo3D } from './structureTo3D'
import { useAutoSave, resolveInitialMaterials, dbToPlaced } from './hooks/useScenePersistence'
import { useGhostControls } from './hooks/useGhostControls'

const WALL_HEIGHT = 96

function PlacementHint({ ghostHeight, ghostScaleW, ghostScaleD, ghostScaleH }: { ghostHeight: number; ghostScaleW: number; ghostScaleD: number; ghostScaleH: number }) {
  return (
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
}

export default function FloorPlan3D({
  structure,
  initialScene,
  onSceneChange,
}: {
  structure: Record<string, unknown>
  initialScene?: PlanScene
  onSceneChange?: (scene: PlanScene) => void
}) {
  const scene = useMemo(() => structureTo3D(structure), [structure])
  const walls3D = scene.walls
  const openings3D = scene.openings
  const floorBounds = { x: scene.floor.x, z: scene.floor.z, w: scene.floor.width, d: scene.floor.depth }
  const center = scene.center
  const camDist = Math.max(floorBounds.w, floorBounds.d) * 1.2
  const initMats = useMemo(() => resolveInitialMaterials(initialScene), [])

  const [fullscreen, setFullscreen] = useState(false)
  const [walkMode, setWalkMode] = useState(false)
  const [tab, setTab] = useState<'furniture' | 'materials'>('furniture')
  const [selectedItem, setSelectedItem] = useState<FurnitureItem | null>(null)
  const [floorMat, setFloorMat] = useState<MaterialPreset>(initMats.floorMat)
  const [wallMat, setWallMat] = useState<MaterialPreset>(initMats.wallMat)
  const [placed, setPlaced] = useState<PlacedFurniture[]>(() =>
    initialScene?.placedItems3d ? dbToPlaced(initialScene.placedItems3d) : [],
  )
  const [selectedPlaced, setSelectedPlaced] = useState(-1)

  const ghost = useGhostControls({ selectedItem, setSelectedItem, setPlaced, setSelectedPlaced })

  const removePlaced = (index: number) => {
    setPlaced((cur) => cur.filter((_, i) => i !== index))
    if (selectedPlaced === index) setSelectedPlaced(-1)
  }
  const rotatePlaced = (index: number) =>
    setPlaced((cur) => cur.map((f, i) => i === index ? { ...f, rotation: f.rotation + Math.PI / 2 } : f))
  const setPlacedTint = (index: number, color: string | undefined) =>
    setPlaced((cur) => cur.map((f, i) => i === index ? { ...f, tintColor: color } : f))
  const pickUpPlaced = (index: number) => {
    const p = placed[index]
    if (!p) return
    setSelectedItem(p.item)
    ghost.setGhostRotation(p.rotation)
    ghost.setGhostHeight(p.y)
    ghost.setGhostScaleW(p.scaleW)
    ghost.setGhostScaleD(p.scaleD)
    ghost.setGhostScaleH(p.scaleH)
    setPlaced((cur) => cur.filter((_, i) => i !== index))
    setSelectedPlaced(-1)
  }

  useAutoSave({ placed, floorMat, wallMat, onSceneChange })

  const canvasContainerRef = useRef<HTMLDivElement>(null)
  const containerClass = fullscreen
    ? 'fixed inset-0 z-50 flex bg-zinc-950'
    : 'relative h-80 w-full overflow-hidden rounded-lg border border-zinc-800/40 bg-zinc-950 sm:h-96'

  return (
    <div className={containerClass} tabIndex={0} onKeyDown={ghost.handlePlaceKey} style={{ outline: 'none' }}>
      {fullscreen && (
        <FurnitureSidebar
          tab={tab} setTab={setTab}
          selectedItem={selectedItem} setSelectedItem={setSelectedItem}
          placed={placed} selectedPlaced={selectedPlaced} setSelectedPlaced={setSelectedPlaced}
          rotatePlaced={rotatePlaced} removePlaced={removePlaced} setPlacedTint={setPlacedTint}
          floorMat={floorMat} setFloorMat={setFloorMat} wallMat={wallMat} setWallMat={setWallMat}
        />
      )}

      <div ref={canvasContainerRef} className="relative flex-1">
        <Canvas shadows dpr={[1, 2]} gl={{ antialias: true, alpha: false }}
          camera={{ position: [center.x + camDist * 0.5, camDist * 0.6, center.z + camDist * 0.5], fov: 45, near: 1, far: camDist * 10 }}
        >
          <SceneRenderer camDist={camDist} />
          <Suspense fallback={null}><SceneWorld center={center} floorBounds={floorBounds} /></Suspense>
          <SceneLighting center={center} floorBounds={floorBounds} camDist={camDist} />
          <SceneEffects />
          {walkMode
            ? <WalkControls center={center} />
            : <OrbitControls target={[center.x, WALL_HEIGHT * 0.3, center.z]} enableDamping dampingFactor={0.1} minDistance={camDist * 0.1} maxDistance={camDist * 3} />}
          <FloorMesh floorBounds={floorBounds} material={floorMat} {...ghost.placementProps} />
          {selectedItem && ghost.ghostPos && (
            <Suspense fallback={null}>
              <GhostPreview item={selectedItem} x={ghost.ghostPos.x} y={ghost.ghostHeight > 0 ? ghost.ghostHeight : ghost.ghostPos.y} z={ghost.ghostPos.z} rotation={(ghost.ghostPos.wallRotation ?? 0) + ghost.ghostRotation} scaleW={ghost.ghostScaleW} scaleD={ghost.ghostScaleD} scaleH={ghost.ghostScaleH} />
            </Suspense>
          )}
          {fullscreen && <Grid position={[center.x, 0.1, center.z]} args={[floorBounds.w, floorBounds.d]} cellSize={12} cellColor="#72809b" sectionSize={48} sectionColor="#8d9ab4" fadeDistance={camDist * 1.2} infiniteGrid={false} />}
          {walls3D.map((wall) => <WallMesh key={wall.id} wall={wall} material={wallMat} {...ghost.placementProps} />)}
          {false && openings3D.map((opening, i) => <OpeningMesh key={`op-${i}`} opening={opening} />)}
          {placed.map((item, index) => (
            <Suspense key={`${item.item.id}-${index}`} fallback={<FurnitureBoxFallback placed={item} />}>
              <FurnitureMesh placed={item} selected={selectedPlaced === index} placing={!!selectedItem} onClick={() => pickUpPlaced(index)} />
            </Suspense>
          ))}
        </Canvas>

        <div className="absolute right-3 top-3 flex gap-2">
          {fullscreen && selectedPlaced >= 0 && (
            <>
              <button onClick={() => rotatePlaced(selectedPlaced)} className="cursor-pointer rounded-md border border-zinc-700/40 bg-zinc-800/90 px-3 py-1.5 text-[11px] font-medium text-zinc-400 backdrop-blur-sm hover:text-zinc-200">Rotate</button>
              <button onClick={() => removePlaced(selectedPlaced)} className="cursor-pointer rounded-md border border-red-700/40 bg-red-900/50 px-3 py-1.5 text-[11px] font-medium text-red-400 backdrop-blur-sm hover:text-red-300">Remove</button>
            </>
          )}
          {fullscreen && (
            <button onClick={() => setWalkMode(!walkMode)} className={`cursor-pointer rounded-md border px-3 py-1.5 text-[11px] font-medium backdrop-blur-sm transition-colors ${walkMode ? 'border-green-600/40 bg-green-900/60 text-green-300' : 'border-zinc-700/40 bg-zinc-800/90 text-zinc-400 hover:text-zinc-200'}`}>
              {walkMode ? 'Walking (ESC)' : 'Walk'}
            </button>
          )}
          <button onClick={() => { setFullscreen(!fullscreen); setSelectedItem(null); setSelectedPlaced(-1); setWalkMode(false) }} className="cursor-pointer rounded-md border border-zinc-700/40 bg-zinc-800/90 px-4 py-1.5 text-[11px] font-semibold text-zinc-400 backdrop-blur-sm transition-colors hover:text-zinc-200">
            {fullscreen ? 'Done' : 'Edit'}
          </button>
        </div>

        <div className="absolute bottom-3 left-3 text-[10px] text-zinc-600">
          {walkMode
            ? 'Click to lock mouse, WASD to move, ESC to unlock'
            : selectedItem
              ? <PlacementHint ghostHeight={ghost.ghostHeight} ghostScaleW={ghost.ghostScaleW} ghostScaleD={ghost.ghostScaleD} ghostScaleH={ghost.ghostScaleH} />
              : !fullscreen ? 'Click Edit to add furniture and materials' : null}
        </div>
      </div>
    </div>
  )
}
