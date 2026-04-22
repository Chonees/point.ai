import { useEffect, useMemo, useState } from 'react'

import type {
  CatalogInspectorBoundary,
  CatalogInspectorBoundaryNode,
  CatalogInspectorOpening,
  CatalogInspectorRoom,
  CatalogInspectorTopology,
  CatalogInspectorWall,
} from './types'
import { CatalogInspectorCanvas } from './CatalogInspectorCanvas'
import { CatalogInspectorSidebar } from './CatalogInspectorSidebar'

interface CatalogInspectorPageProps {
  topology: CatalogInspectorTopology
}

type FocusMode = 'all' | 'shared' | 'exact' | 'snapped' | 'unsupported'

const FOCUS_MODES: Array<{ value: FocusMode; label: string }> = [
  { value: 'all', label: 'All walls' },
  { value: 'shared', label: 'Shared' },
  { value: 'exact', label: 'Exact' },
  { value: 'snapped', label: 'Snapped' },
  { value: 'unsupported', label: 'Unsupported' },
]

function formatRatio(total: number, subset: number) {
  if (total === 0) return '0%'
  return `${Math.round((subset / total) * 100)}%`
}

function filterWalls(walls: CatalogInspectorWall[], focusMode: FocusMode) {
  switch (focusMode) {
    case 'shared':
      return walls.filter((wall) => !wall.is_exterior)
    case 'exact':
      return walls.filter((wall) => !wall.is_exterior && wall.trace_support_status === 'exact_trace_supported')
    case 'snapped':
      return walls.filter((wall) => !wall.is_exterior && wall.trace_support_status === 'snapped_to_trace')
    case 'unsupported':
      return walls.filter((wall) => !wall.is_exterior && wall.trace_support_status === 'unsupported')
    case 'all':
    default:
      return walls
  }
}

function buildFocusQueue(walls: CatalogInspectorWall[], focusMode: FocusMode) {
  if (focusMode !== 'all') return filterWalls(walls, focusMode)
  return walls.filter((wall) => !wall.is_exterior && wall.trace_support_status !== 'exact_trace_supported')
}

export function CatalogInspectorPage({ topology }: CatalogInspectorPageProps) {
  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(topology.rooms[0]?.room_id ?? null)
  const [selectedWallId, setSelectedWallId] = useState<string | null>(null)
  const [selectedBoundaryId, setSelectedBoundaryId] = useState<string | null>(null)
  const [selectedOpeningId, setSelectedOpeningId] = useState<string | null>(null)
  const [focusMode, setFocusMode] = useState<FocusMode>('all')
  const [showIds, setShowIds] = useState(false)
  const [showAdjacency, setShowAdjacency] = useState(false)
  const [showWalls, setShowWalls] = useState(true)
  const [showExactBoundaries, setShowExactBoundaries] = useState(false)
  const [showRawWallTraces, setShowRawWallTraces] = useState(true)
  const [showDoorTraces, setShowDoorTraces] = useState(true)
  const [showWindowTraces, setShowWindowTraces] = useState(true)
  const [showHostedOpenings, setShowHostedOpenings] = useState(true)

  const roomById = useMemo(() => new Map(topology.rooms.map((room) => [room.room_id, room])), [topology.rooms])
  const wallById = useMemo(() => new Map(topology.walls.map((wall) => [wall.wall_id, wall])), [topology.walls])
  const boundaries = topology.boundaries ?? []
  const boundaryNodes = topology.boundary_nodes ?? []
  const boundaryById = useMemo(() => new Map(boundaries.map((boundary) => [boundary.boundary_id, boundary])), [boundaries])
  const openingById = useMemo(() => new Map((topology.openings ?? []).map((opening) => [opening.opening_id, opening])), [topology.openings])
  const cadTraces = topology.cad_traces ?? []
  const hostedOpenings = topology.openings ?? []
  const rawWallTraces = useMemo(() => cadTraces.filter((trace) => trace.trace_kind === 'wall'), [cadTraces])
  const doorTraces = useMemo(() => cadTraces.filter((trace) => trace.trace_kind === 'door'), [cadTraces])
  const windowTraces = useMemo(() => cadTraces.filter((trace) => trace.trace_kind === 'window'), [cadTraces])
  const visibleWalls = useMemo(() => filterWalls(topology.walls, focusMode), [topology.walls, focusMode])
  const focusQueue = useMemo(() => buildFocusQueue(topology.walls, focusMode), [topology.walls, focusMode])

  useEffect(() => {
    if (topology.rooms.length === 0) {
      if (selectedRoomId !== null) setSelectedRoomId(null)
      return
    }

    if (!selectedRoomId || !roomById.has(selectedRoomId)) {
      setSelectedRoomId(topology.rooms[0].room_id)
    }
  }, [roomById, selectedRoomId, topology.rooms])

  useEffect(() => {
    if (focusQueue.length === 0) {
      if (selectedWallId !== null) setSelectedWallId(null)
      return
    }

    if (!selectedWallId || !focusQueue.some((wall) => wall.wall_id === selectedWallId)) {
      setSelectedWallId(focusQueue[0].wall_id)
    }
  }, [focusQueue, selectedWallId])

  const selectedRoom = useMemo<CatalogInspectorRoom | null>(() => {
    if (!selectedRoomId) return null
    return roomById.get(selectedRoomId) ?? null
  }, [roomById, selectedRoomId])

  const selectedWall = useMemo<CatalogInspectorWall | null>(() => {
    if (!selectedWallId) return null
    return wallById.get(selectedWallId) ?? null
  }, [selectedWallId, wallById])

  const selectedBoundary = useMemo<CatalogInspectorBoundary | null>(() => {
    if (!selectedBoundaryId) return null
    return boundaryById.get(selectedBoundaryId) ?? null
  }, [boundaryById, selectedBoundaryId])

  const selectedBoundaryNodes = useMemo<CatalogInspectorBoundaryNode[]>(() => {
    if (!selectedBoundary) return []
    const nodeIds = new Set([selectedBoundary.start_node_id, selectedBoundary.end_node_id])
    return boundaryNodes.filter((node) => nodeIds.has(node.node_id))
  }, [boundaryNodes, selectedBoundary])

  const selectedOpening = useMemo<CatalogInspectorOpening | null>(() => {
    if (!selectedOpeningId) return null
    return openingById.get(selectedOpeningId) ?? null
  }, [openingById, selectedOpeningId])

  const categorizedRooms = topology.rooms.filter((room) => room.category !== 'unknown').length
  const exteriorRooms = topology.rooms.filter((room) => room.is_exterior_touching).length
  const roomsWithAdjacency = topology.rooms.filter((room) => room.adjacent_room_ids.length > 0).length
  const expectedIsolatedRooms = topology.rooms.filter((room) => room.isolation_status === 'expected_isolated').length
  const roomsWithOwnedWalls = topology.rooms.filter((room) => room.owned_wall_ids.length > 0).length
  const heuristicAdjacencyEdges = topology.rooms.reduce(
    (count, room) => count + (room.heuristic_adjacent_room_ids?.length ?? 0),
    0,
  ) / 2
  const openingAdjacencyEdges = topology.rooms.reduce(
    (count, room) => count + (room.opening_adjacent_room_ids?.length ?? 0),
    0,
  ) / 2
  const sharedWalls = topology.walls.filter((wall) => !wall.is_exterior).length
  const inferredWalls = topology.walls.filter((wall) => !wall.is_exterior && wall.provenance === 'bbox_inferred').length
  const exactSharedWalls = topology.walls.filter((wall) => !wall.is_exterior && wall.trace_support_status === 'exact_trace_supported').length
  const snappedSharedWalls = topology.walls.filter((wall) => !wall.is_exterior && wall.trace_support_status === 'snapped_to_trace').length
  const unsupportedSharedWalls = topology.walls.filter((wall) => !wall.is_exterior && wall.trace_support_status === 'unsupported').length
  const exactBoundarySharedCount = boundaries.filter((boundary) => boundary.boundary_kind === 'shared').length
  const unknownBoundaryCount = boundaries.filter((boundary) => boundary.boundary_kind === 'unknown').length
  const hostedDoorCount = hostedOpenings.filter((opening) => opening.opening_kind === 'door' && opening.host_wall_id).length
  const hostedWindowCount = hostedOpenings.filter((opening) => opening.opening_kind === 'window' && opening.host_wall_id).length
  const unhostedOpeningCount = hostedOpenings.filter((opening) => !opening.host_wall_id).length

  const cycleFocusedWall = (delta: number) => {
    if (focusQueue.length === 0) return
    const currentIndex = selectedWallId ? focusQueue.findIndex((wall) => wall.wall_id === selectedWallId) : -1
    const startIndex = currentIndex >= 0 ? currentIndex : 0
    const nextIndex = (startIndex + delta + focusQueue.length) % focusQueue.length
    setSelectedWallId(focusQueue[nextIndex].wall_id)
  }

  return (
    <div className="min-h-screen bg-[#090909] text-zinc-100">
      <header className="border-b border-white/6 bg-zinc-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-5 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <div>
            <p className="text-[11px] uppercase tracking-[0.26em] text-zinc-600">Temporary screen</p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-50">Topology inspector</h1>
            <p className="mt-1 text-sm text-zinc-400">
              Validación visual temporal del plano real de <span className="font-medium text-zinc-200">{topology.name}</span>.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-11">
            <div className="rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Rooms</p>
              <p className="mt-1 text-lg font-semibold text-zinc-100">{topology.rooms.length}</p>
            </div>
            <div className="rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Categorized</p>
              <p className="mt-1 text-lg font-semibold text-zinc-100">{formatRatio(topology.rooms.length, categorizedRooms)}</p>
            </div>
            <div className="rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Exterior touch</p>
              <p className="mt-1 text-lg font-semibold text-zinc-100">{exteriorRooms}</p>
            </div>
            <div className="rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Shared walls</p>
              <p className="mt-1 text-lg font-semibold text-zinc-100">{sharedWalls}</p>
            </div>
            <div className="rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Inferred walls</p>
              <p className="mt-1 text-lg font-semibold text-zinc-100">{inferredWalls}</p>
            </div>
            <div className="rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Wall traces</p>
              <p className="mt-1 text-lg font-semibold text-zinc-100">{rawWallTraces.length}</p>
            </div>
            <div className="rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Door traces</p>
              <p className="mt-1 text-lg font-semibold text-fuchsia-200">{doorTraces.length}</p>
            </div>
            <div className="rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Window traces</p>
              <p className="mt-1 text-lg font-semibold text-indigo-200">{windowTraces.length}</p>
            </div>
            <div className="rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Shared exact</p>
              <p className="mt-1 text-lg font-semibold text-emerald-300">{exactSharedWalls}</p>
            </div>
            <div className="rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Shared snapped</p>
              <p className="mt-1 text-lg font-semibold text-amber-300">{snappedSharedWalls}</p>
            </div>
            <div className="rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Shared unsupported</p>
              <p className="mt-1 text-lg font-semibold text-rose-300">{unsupportedSharedWalls}</p>
            </div>
            <div className="rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Unknown boundaries</p>
              <p className="mt-1 text-lg font-semibold text-orange-200">{unknownBoundaryCount}</p>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <section className="mb-6 rounded-[24px] border border-white/6 bg-zinc-950/70 p-4">
          <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr_auto_auto_auto_auto] xl:items-start">
            <div>
              <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Validation</p>
              <p className="mt-1 text-sm text-zinc-300">
                {roomsWithAdjacency} rooms with wall-backed adjacency, {openingAdjacencyEdges} opening-backed adjacency edges, {heuristicAdjacencyEdges} heuristic adjacency edges, {roomsWithOwnedWalls} rooms with owned walls, {hostedDoorCount} hosted doors, {hostedWindowCount} hosted windows, {unhostedOpeningCount} unhosted openings, {expectedIsolatedRooms} expected isolated rooms, {topology.topology_issues.length} topology issues, {topology.wall_graph_issues.length} wall graph issues, {cadTraces.length} CAD traces split into {rawWallTraces.length} walls, {doorTraces.length} doors, {windowTraces.length} windows, {unsupportedSharedWalls} unsupported shared walls, {exactBoundarySharedCount} exact-graph shared boundaries, {unknownBoundaryCount} unknown boundaries.
              </p>
              <p className="mt-1 text-sm text-zinc-500">
                Readiness: <span className="font-medium text-zinc-200">{topology.topology_readiness.status}</span> / <span className="font-medium text-zinc-200">{topology.wall_graph_readiness.status}</span> / <span className="font-medium text-zinc-200">{topology.opening_graph_readiness?.status ?? 'opening_graph_unavailable'}</span> / <span className="font-medium text-zinc-200">{topology.boundary_graph_readiness?.status ?? 'boundary_graph_unavailable'}</span>
              </p>
              <p className="mt-1 text-xs text-zinc-500">
                Importante: doors/windows se renderizan aparte y NO cuentan como soporte de wall graph.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                {FOCUS_MODES.map((mode) => (
                  <button
                    key={mode.value}
                    type="button"
                    onClick={() => setFocusMode(mode.value)}
                    aria-pressed={focusMode === mode.value}
                    className={focusMode === mode.value
                      ? 'rounded-xl border border-cyan-400/50 bg-cyan-400/10 px-3 py-2 text-sm font-medium text-cyan-200'
                      : 'rounded-xl border border-white/6 bg-white/[0.03] px-3 py-2 text-sm text-zinc-300'}
                  >
                    {mode.label}
                  </button>
                ))}
              </div>
              <p className="mt-3 text-xs text-zinc-500">
                Focus mode: <span data-testid="focus-mode-value" className="font-medium text-zinc-300">{focusMode}</span>
              </p>
            </div>

            <label className="inline-flex items-center gap-3 rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3 text-sm text-zinc-200">
              <input
                type="checkbox"
                checked={showIds}
                onChange={(event) => setShowIds(event.target.checked)}
                className="h-4 w-4 rounded border-zinc-600 bg-zinc-900 text-cyan-400 focus:ring-cyan-500"
              />
              Room IDs
            </label>

            <label className="inline-flex items-center gap-3 rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3 text-sm text-zinc-200">
              <input
                type="checkbox"
                checked={showAdjacency}
                onChange={(event) => setShowAdjacency(event.target.checked)}
                className="h-4 w-4 rounded border-zinc-600 bg-zinc-900 text-cyan-400 focus:ring-cyan-500"
              />
              Adjacency
            </label>

            <label className="inline-flex items-center gap-3 rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3 text-sm text-zinc-200">
              <input
                type="checkbox"
                checked={showWalls}
                onChange={(event) => setShowWalls(event.target.checked)}
                className="h-4 w-4 rounded border-zinc-600 bg-zinc-900 text-cyan-400 focus:ring-cyan-500"
              />
              Walls
            </label>

            <label className="inline-flex items-center gap-3 rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3 text-sm text-zinc-200">
              <input
                type="checkbox"
                checked={showExactBoundaries}
                onChange={(event) => setShowExactBoundaries(event.target.checked)}
                className="h-4 w-4 rounded border-zinc-600 bg-zinc-900 text-cyan-400 focus:ring-cyan-500"
              />
              Exact boundaries
            </label>

            <label className="inline-flex items-center gap-3 rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3 text-sm text-zinc-200">
              <input
                type="checkbox"
                checked={showRawWallTraces}
                onChange={(event) => setShowRawWallTraces(event.target.checked)}
                className="h-4 w-4 rounded border-zinc-600 bg-zinc-900 text-cyan-400 focus:ring-cyan-500"
              />
              Raw wall traces
            </label>

            <label className="inline-flex items-center gap-3 rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3 text-sm text-zinc-200">
              <input
                type="checkbox"
                checked={showDoorTraces}
                onChange={(event) => setShowDoorTraces(event.target.checked)}
                className="h-4 w-4 rounded border-zinc-600 bg-zinc-900 text-cyan-400 focus:ring-cyan-500"
              />
              Door traces
            </label>

            <label className="inline-flex items-center gap-3 rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3 text-sm text-zinc-200">
              <input
                type="checkbox"
                checked={showWindowTraces}
                onChange={(event) => setShowWindowTraces(event.target.checked)}
                className="h-4 w-4 rounded border-zinc-600 bg-zinc-900 text-cyan-400 focus:ring-cyan-500"
              />
              Window traces
            </label>

            <label className="inline-flex items-center gap-3 rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3 text-sm text-zinc-200">
              <input
                type="checkbox"
                checked={showHostedOpenings}
                onChange={(event) => setShowHostedOpenings(event.target.checked)}
                className="h-4 w-4 rounded border-zinc-600 bg-zinc-900 text-cyan-400 focus:ring-cyan-500"
              />
              Hosted openings
            </label>

            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => cycleFocusedWall(-1)}
                disabled={focusQueue.length < 2}
                className="rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3 text-sm text-zinc-200 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Previous issue
              </button>
              <button
                type="button"
                onClick={() => cycleFocusedWall(1)}
                disabled={focusQueue.length < 2}
                className="rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3 text-sm text-zinc-200 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next issue
              </button>
            </div>
          </div>
        </section>

        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
          <CatalogInspectorCanvas
            topology={topology}
            visibleWalls={visibleWalls}
            selectedRoomId={selectedRoomId}
            selectedWallId={selectedWallId}
            selectedBoundaryId={selectedBoundaryId}
            selectedOpeningId={selectedOpeningId}
            onSelectRoom={setSelectedRoomId}
            onSelectWall={setSelectedWallId}
            onSelectBoundary={setSelectedBoundaryId}
            onSelectOpening={(openingId, hostWallId) => {
              setSelectedOpeningId(openingId)
              if (hostWallId) setSelectedWallId(hostWallId)
            }}
            showIds={showIds}
            showAdjacency={showAdjacency}
            showWalls={showWalls}
            showExactBoundaries={showExactBoundaries}
            showRawWallTraces={showRawWallTraces}
            showDoorTraces={showDoorTraces}
            showWindowTraces={showWindowTraces}
            showHostedOpenings={showHostedOpenings}
          />

          <CatalogInspectorSidebar
            topology={topology}
            selectedRoom={selectedRoom}
            selectedWall={selectedWall}
            selectedBoundary={selectedBoundary}
            selectedBoundaryNodes={selectedBoundaryNodes}
            selectedOpening={selectedOpening}
            focusMode={focusMode}
            focusWalls={focusQueue}
            onSelectWall={setSelectedWallId}
            onPreviousWall={() => cycleFocusedWall(-1)}
            onNextWall={() => cycleFocusedWall(1)}
          />
        </div>
      </main>
    </div>
  )
}
