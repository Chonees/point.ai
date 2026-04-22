import { useEffect, useMemo, useState } from 'react'

import type { CatalogInspectorRoom, CatalogInspectorTopology } from './types'
import { CatalogInspectorCanvas } from './CatalogInspectorCanvas'
import { CatalogInspectorSidebar } from './CatalogInspectorSidebar'

interface CatalogInspectorPageProps {
  topology: CatalogInspectorTopology
}

function formatRatio(total: number, subset: number) {
  if (total === 0) return '0%'
  return `${Math.round((subset / total) * 100)}%`
}

export function CatalogInspectorPage({ topology }: CatalogInspectorPageProps) {
  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(topology.rooms[0]?.room_id ?? null)
  const [showIds, setShowIds] = useState(false)
  const [showAdjacency, setShowAdjacency] = useState(false)
  const [showWalls, setShowWalls] = useState(true)
  const [showRawTraces, setShowRawTraces] = useState(true)
  const roomById = useMemo(() => new Map(topology.rooms.map((room) => [room.room_id, room])), [topology.rooms])
  const rawTraces = topology.wall_traces ?? []

  useEffect(() => {
    if (topology.rooms.length === 0) {
      if (selectedRoomId !== null) setSelectedRoomId(null)
      return
    }

    if (!selectedRoomId || !roomById.has(selectedRoomId)) {
      setSelectedRoomId(topology.rooms[0].room_id)
    }
  }, [roomById, selectedRoomId, topology.rooms])

  const selectedRoom = useMemo<CatalogInspectorRoom | null>(() => {
    if (!selectedRoomId) return null
    return roomById.get(selectedRoomId) ?? null
  }, [roomById, selectedRoomId])

  const categorizedRooms = topology.rooms.filter((room) => room.category !== 'unknown').length
  const exteriorRooms = topology.rooms.filter((room) => room.is_exterior_touching).length
  const roomsWithAdjacency = topology.rooms.filter((room) => room.adjacent_room_ids.length > 0).length
  const sharedWalls = topology.walls.filter((wall) => !wall.is_exterior).length
  const inferredWalls = topology.walls.filter((wall) => wall.issues.includes('inferred_from_bbox')).length
  const exactSharedWalls = topology.walls.filter((wall) => !wall.is_exterior && wall.trace_support_status === 'exact_trace_supported').length
  const snappedSharedWalls = topology.walls.filter((wall) => !wall.is_exterior && wall.trace_support_status === 'snapped_to_trace').length
  const unsupportedSharedWalls = topology.walls.filter((wall) => !wall.is_exterior && wall.trace_support_status === 'unsupported').length

  return (
    <div className="min-h-screen bg-[#090909] text-zinc-100">
      <header className="border-b border-white/6 bg-zinc-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-5 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <div>
            <p className="text-[11px] uppercase tracking-[0.26em] text-zinc-600">Temporary screen</p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-50">Topology inspector</h1>
            <p className="mt-1 text-sm text-zinc-400">
              Validaci?n visual temporal del plano real de <span className="font-medium text-zinc-200">{topology.name}</span>.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-9">
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
              <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Raw traces</p>
              <p className="mt-1 text-lg font-semibold text-zinc-100">{rawTraces.length}</p>
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
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <section className="mb-6 rounded-[24px] border border-white/6 bg-zinc-950/70 p-4">
          <div className="grid gap-4 lg:grid-cols-[1fr_auto_auto_auto_auto] lg:items-center">
            <div>
              <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Validation</p>
              <p className="mt-1 text-sm text-zinc-300">
                {roomsWithAdjacency} rooms with adjacency, {topology.topology_issues.length} topology issues, {topology.wall_graph_issues.length} wall graph issues, {rawTraces.length} raw wall traces, {unsupportedSharedWalls} unsupported shared walls.
              </p>
              <p className="mt-1 text-sm text-zinc-500">
                Readiness: <span className="font-medium text-zinc-200">{topology.topology_readiness.status}</span> / <span className="font-medium text-zinc-200">{topology.wall_graph_readiness.status}</span>
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
                checked={showRawTraces}
                onChange={(event) => setShowRawTraces(event.target.checked)}
                className="h-4 w-4 rounded border-zinc-600 bg-zinc-900 text-cyan-400 focus:ring-cyan-500"
              />
              Raw traces
            </label>
          </div>
        </section>

        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
          <CatalogInspectorCanvas
            topology={topology}
            selectedRoomId={selectedRoomId}
            onSelectRoom={setSelectedRoomId}
            showIds={showIds}
            showAdjacency={showAdjacency}
            showWalls={showWalls}
            showRawTraces={showRawTraces}
          />

          <CatalogInspectorSidebar topology={topology} selectedRoom={selectedRoom} />
        </div>
      </main>
    </div>
  )
}
