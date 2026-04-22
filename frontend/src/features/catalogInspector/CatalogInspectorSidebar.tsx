import type { CatalogInspectorOpening, CatalogInspectorRoom, CatalogInspectorTopology, CatalogInspectorWall } from './types'

interface CatalogInspectorSidebarProps {
  topology: CatalogInspectorTopology
  selectedRoom: CatalogInspectorRoom | null
  selectedWall: CatalogInspectorWall | null
  selectedOpening: CatalogInspectorOpening | null
  focusMode: string
  focusWalls: CatalogInspectorWall[]
  onSelectWall: (wallId: string) => void
  onPreviousWall: () => void
  onNextWall: () => void
}

function formatIssueList(issues: string[]) {
  if (issues.length === 0) return 'No issues'
  return issues.join(', ')
}

function formatTraceSupportStatus(status: string) {
  switch (status) {
    case 'exact_trace_supported':
      return 'Exact trace support'
    case 'snapped_to_trace':
      return 'Snapped to trace'
    case 'unsupported':
      return 'Unsupported by trace'
    default:
      return status
  }
}

function formatProvenance(provenance: string) {
  switch (provenance) {
    case 'exact_room_overlap':
      return 'Exact room overlap'
    case 'bbox_inferred':
      return 'BBox inferred'
    case 'room_exterior_boundary':
      return 'Room exterior boundary'
    default:
      return provenance
  }
}

function formatConfidence(confidence: string) {
  switch (confidence) {
    case 'geometric_exact':
      return 'Geometric exact'
    case 'exact':
      return 'Exact trace backed'
    case 'trace_supported':
      return 'Trace supported'
    case 'heuristic':
      return 'Heuristic'
    case 'unsupported':
      return 'Unsupported'
    case 'hosted':
      return 'Hosted'
    case 'unhosted':
      return 'Unhosted'
    default:
      return confidence
  }
}

function formatBoundaryKind(boundaryKind: string) {
  switch (boundaryKind) {
    case 'shared':
      return 'Shared'
    case 'exterior':
      return 'Exterior'
    default:
      return boundaryKind
  }
}

function formatIsolationStatus(status: string) {
  switch (status) {
    case 'connected':
      return 'Connected'
    case 'expected_isolated':
      return 'Expected isolated'
    case 'suspicious_isolated':
      return 'Suspicious isolated'
    default:
      return status
  }
}

function roomPairLabel(topology: CatalogInspectorTopology, wall: CatalogInspectorWall) {
  return wall.room_ids
    .map((roomId) => topology.rooms.find((room) => room.room_id === roomId)?.name ?? roomId)
    .join(' <-> ')
}

function roomNames(topology: CatalogInspectorTopology, roomIds: string[]) {
  if (roomIds.length === 0) return 'None'
  return roomIds.map((roomId) => topology.rooms.find((room) => room.room_id === roomId)?.name ?? roomId).join(', ')
}

export function CatalogInspectorSidebar({
  topology,
  selectedRoom,
  selectedWall,
  selectedOpening,
  focusMode,
  focusWalls,
  onSelectWall,
  onPreviousWall,
  onNextWall,
}: CatalogInspectorSidebarProps) {
  const selectedRoomWalls = selectedRoom
    ? topology.walls.filter((wall) => wall.owner_room_ids.includes(selectedRoom.room_id))
    : []

  return (
    <aside className="rounded-[24px] border border-white/6 bg-zinc-950/80 p-5">
      <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Inspector</p>
      <h2 className="mt-2 text-lg font-semibold text-zinc-100">Focus + room inspector</h2>

      <div className="mt-5 space-y-5">
        <div className="rounded-2xl border border-white/6 bg-white/[0.03] p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Focus mode</p>
              <p data-testid="sidebar-focus-mode-value" className="mt-1 text-sm font-medium text-zinc-100">{focusMode}</p>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={onPreviousWall}
                disabled={focusWalls.length < 2}
                className="rounded-xl border border-white/6 bg-black/20 px-3 py-2 text-sm text-zinc-200 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Previous issue
              </button>
              <button
                type="button"
                onClick={onNextWall}
                disabled={focusWalls.length < 2}
                className="rounded-xl border border-white/6 bg-black/20 px-3 py-2 text-sm text-zinc-200 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next issue
              </button>
            </div>
          </div>
          <p className="mt-3 text-sm text-zinc-400">{focusWalls.length} wall(s) in the current focus queue.</p>
        </div>

        {selectedWall ? (
          <div data-testid="selected-wall-panel" className="rounded-2xl border border-white/6 bg-white/[0.03] p-4">
            <h3 className="text-sm font-semibold uppercase tracking-[0.22em] text-zinc-400">Focused wall</h3>
            <p data-testid="selected-wall-id" className="mt-2 text-sm font-medium text-zinc-100">{selectedWall.wall_id}</p>
            <p className="mt-1 text-sm text-zinc-300">{roomPairLabel(topology, selectedWall)}</p>
            <p className="mt-1 text-xs text-sky-300">
              {formatTraceSupportStatus(selectedWall.trace_support_status)}
              {selectedWall.trace_support_gap != null ? ` · gap ${selectedWall.trace_support_gap.toFixed(3)}` : ''}
            </p>
            <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-xl bg-black/20 p-3">
                <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Provenance</p>
                <p className="mt-1 text-zinc-100">{formatProvenance(selectedWall.provenance)}</p>
              </div>
              <div className="rounded-xl bg-black/20 p-3">
                <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Confidence</p>
                <p className="mt-1 text-zinc-100">{formatConfidence(selectedWall.confidence)}</p>
              </div>
              <div className="rounded-xl bg-black/20 p-3">
                <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Boundary kind</p>
                <p className="mt-1 text-zinc-100">{formatBoundaryKind(selectedWall.boundary_kind)}</p>
              </div>
              <div className="rounded-xl bg-black/20 p-3">
                <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Owner rooms</p>
                <p className="mt-1 text-zinc-100">{roomNames(topology, selectedWall.owner_room_ids)}</p>
              </div>
            </div>
            {selectedWall.trace_support_ids.length > 0 ? (
              <p className="mt-3 text-xs text-zinc-500">{selectedWall.trace_support_ids.join(', ')}</p>
            ) : null}
            <p className="mt-2 text-xs text-amber-300">{formatIssueList(selectedWall.issues)}</p>
          </div>
        ) : null}

        {selectedOpening ? (
          <div data-testid="selected-opening-panel" className="rounded-2xl border border-white/6 bg-white/[0.03] p-4">
            <h3 className="text-sm font-semibold uppercase tracking-[0.22em] text-zinc-400">Selected opening</h3>
            <p className="mt-2 text-sm font-medium text-zinc-100">{selectedOpening.opening_id}</p>
            <p className="mt-1 text-sm text-zinc-300">{selectedOpening.opening_kind}</p>
            <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-xl bg-black/20 p-3">
                <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Host wall</p>
                <p className="mt-1 text-zinc-100">{selectedOpening.host_wall_id ?? 'Unhosted'}</p>
              </div>
              <div className="rounded-xl bg-black/20 p-3">
                <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Confidence</p>
                <p className="mt-1 text-zinc-100">{formatConfidence(selectedOpening.confidence)}</p>
              </div>
              <div className="rounded-xl bg-black/20 p-3">
                <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Owner rooms</p>
                <p className="mt-1 text-zinc-100">{roomNames(topology, selectedOpening.owner_room_ids)}</p>
              </div>
              <div className="rounded-xl bg-black/20 p-3">
                <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Connected rooms</p>
                <p className="mt-1 text-zinc-100">{roomNames(topology, selectedOpening.connected_room_ids)}</p>
              </div>
            </div>
            <p className="mt-3 text-xs text-zinc-500">span {selectedOpening.span.toFixed(2)} · offset {selectedOpening.offset.toFixed(2)}</p>
            <p className="mt-2 text-xs text-amber-300">{formatIssueList(selectedOpening.issues)}</p>
          </div>
        ) : null}

        <div className="rounded-2xl border border-white/6 bg-white/[0.03] p-4">
          <h3 className="text-sm font-semibold uppercase tracking-[0.22em] text-zinc-400">Focus queue</h3>
          <div className="mt-3 space-y-2">
            {focusWalls.length > 0 ? (
              focusWalls.map((wall) => {
                const isSelected = selectedWall?.wall_id === wall.wall_id
                return (
                  <button
                    key={wall.wall_id}
                    type="button"
                    data-testid={`focus-wall-${wall.wall_id}`}
                    onClick={() => onSelectWall(wall.wall_id)}
                    className={isSelected
                      ? 'w-full rounded-xl border border-cyan-400/40 bg-cyan-400/10 px-3 py-3 text-left'
                      : 'w-full rounded-xl border border-white/6 bg-black/20 px-3 py-3 text-left'}
                  >
                    <p className="font-medium text-zinc-100">{roomPairLabel(topology, wall)}</p>
                    <p className="mt-1 text-xs text-sky-300">{formatTraceSupportStatus(wall.trace_support_status)}</p>
                    <p className="mt-1 text-xs text-zinc-500">
                      {formatProvenance(wall.provenance)} · {formatConfidence(wall.confidence)} · {formatBoundaryKind(wall.boundary_kind)}
                    </p>
                    {wall.trace_support_gap != null ? (
                      <p className="mt-1 text-xs text-zinc-500">gap {wall.trace_support_gap.toFixed(3)}</p>
                    ) : null}
                  </button>
                )
              })
            ) : (
              <p className="text-sm text-zinc-500">No walls in the current focus queue.</p>
            )}
          </div>
        </div>

        <div className="rounded-2xl border border-white/6 bg-white/[0.03] p-4">
          <h3 className="text-sm font-semibold uppercase tracking-[0.22em] text-zinc-400">Room seleccionada</h3>

          {selectedRoom ? (
            <div className="mt-3 space-y-4">
              <div>
                <h4 className="text-xl font-semibold text-zinc-50">{selectedRoom.name}</h4>
                <p data-testid="selected-room-id" className="mt-1 text-sm text-zinc-400">{selectedRoom.room_id}</p>
              </div>

              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-xl bg-white/[0.02] p-3">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Category</p>
                  <p className="mt-1 text-zinc-100">{selectedRoom.category}</p>
                </div>
                <div className="rounded-xl bg-white/[0.02] p-3">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Area</p>
                  <p className="mt-1 text-zinc-100">{selectedRoom.area.toFixed(1)} sq in</p>
                </div>
                <div className="rounded-xl bg-white/[0.02] p-3">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Size</p>
                  <p className="mt-1 text-zinc-100">{selectedRoom.width.toFixed(1)} x {selectedRoom.height.toFixed(1)}</p>
                </div>
                <div className="rounded-xl bg-white/[0.02] p-3">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Exterior</p>
                  <p className="mt-1 text-zinc-100">{selectedRoom.is_exterior_touching ? 'Yes' : 'No'}</p>
                </div>
                <div className="rounded-xl bg-white/[0.02] p-3">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Isolation</p>
                  <p className="mt-1 text-zinc-100">{formatIsolationStatus(selectedRoom.isolation_status)}</p>
                </div>
                <div className="rounded-xl bg-white/[0.02] p-3">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Adjacency</p>
                  <p className="mt-1 text-zinc-100">{selectedRoom.adjacent_room_ids.length}</p>
                </div>
                <div className="rounded-xl bg-white/[0.02] p-3">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Owned walls</p>
                  <p className="mt-1 text-zinc-100">{selectedRoom.owned_wall_ids.length}</p>
                </div>
                <div className="rounded-xl bg-white/[0.02] p-3">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Shared walls</p>
                  <p className="mt-1 text-zinc-100">{selectedRoom.shared_wall_ids.length}</p>
                </div>
                <div className="rounded-xl bg-white/[0.02] p-3">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Exterior walls</p>
                  <p className="mt-1 text-zinc-100">{selectedRoom.exterior_wall_ids.length}</p>
                </div>
              </div>

              <div>
                <h4 className="text-sm font-semibold uppercase tracking-[0.22em] text-zinc-400">Supported adjacency</h4>
                <p className="mt-2 text-sm text-zinc-200">{roomNames(topology, selectedRoom.adjacent_room_ids)}</p>
              </div>

              <div>
                <h4 className="text-sm font-semibold uppercase tracking-[0.22em] text-zinc-400">Opening adjacency</h4>
                <p className="mt-2 text-sm text-zinc-200">{roomNames(topology, selectedRoom.opening_adjacent_room_ids ?? [])}</p>
              </div>

              <div>
                <h4 className="text-sm font-semibold uppercase tracking-[0.22em] text-zinc-400">Heuristic adjacency</h4>
                <p className="mt-2 text-sm text-zinc-200">{roomNames(topology, selectedRoom.heuristic_adjacent_room_ids ?? [])}</p>
              </div>

              <div>
                <h4 className="text-sm font-semibold uppercase tracking-[0.22em] text-zinc-400">Connected walls</h4>
                <div className="mt-3 space-y-2">
                  {selectedRoomWalls.length > 0 ? (
                    selectedRoomWalls.map((wall) => (
                      <div key={wall.wall_id} className="rounded-xl border border-white/6 bg-black/20 px-3 py-2">
                        <div className="flex items-center justify-between gap-3 text-sm">
                          <p className="font-medium text-zinc-100">{wall.wall_id}</p>
                          <span className="text-zinc-400">{wall.orientation}</span>
                        </div>
                        <p className="mt-1 text-sm text-zinc-300">{wall.is_exterior ? 'Exterior' : 'Shared'} · {wall.length.toFixed(1)} in</p>
                        <p className="mt-1 text-xs text-zinc-500">{wall.room_ids.join(' / ')}</p>
                        <p className="mt-1 text-xs text-zinc-500">Boundary: {formatBoundaryKind(wall.boundary_kind)} · Owners: {roomNames(topology, wall.owner_room_ids)}</p>
                        <p className="mt-1 text-xs text-sky-300">
                          {formatTraceSupportStatus(wall.trace_support_status)}
                          {wall.trace_support_gap != null ? ` · gap ${wall.trace_support_gap.toFixed(3)}` : ''}
                        </p>
                        <p className="mt-1 text-xs text-zinc-500">
                          Provenance: {formatProvenance(wall.provenance)} · Confidence: {formatConfidence(wall.confidence)}
                        </p>
                        {wall.trace_support_ids.length > 0 ? (
                          <p className="mt-1 text-xs text-zinc-500">{wall.trace_support_ids.join(', ')}</p>
                        ) : null}
                        <p className="mt-1 text-xs text-amber-300">{formatIssueList(wall.issues)}</p>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-zinc-500">No connected walls detected.</p>
                  )}
                </div>
              </div>

              <div>
                <h4 className="text-sm font-semibold uppercase tracking-[0.22em] text-zinc-400">Issues</h4>
                <p className="mt-2 text-sm text-zinc-200">{formatIssueList(selectedRoom.issues)}</p>
              </div>
            </div>
          ) : (
            <div className="mt-3 rounded-2xl border border-dashed border-white/10 bg-white/[0.02] p-4">
              <p className="text-sm text-zinc-300">Click any room in the canvas to inspect its topology details.</p>
            </div>
          )}
        </div>
      </div>
    </aside>
  )
}
