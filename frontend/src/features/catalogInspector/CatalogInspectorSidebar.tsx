import type { CatalogInspectorRoom, CatalogInspectorTopology } from './types'

interface CatalogInspectorSidebarProps {
  topology: CatalogInspectorTopology
  selectedRoom: CatalogInspectorRoom | null
}

function formatIssueList(issues: string[]) {
  if (issues.length === 0) return 'No issues'
  return issues.join(', ')
}

export function CatalogInspectorSidebar({ topology, selectedRoom }: CatalogInspectorSidebarProps) {
  return (
    <aside className="rounded-[24px] border border-white/6 bg-zinc-950/80 p-5">
      <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Inspector</p>
      <h2 className="mt-2 text-lg font-semibold text-zinc-100">Room seleccionado</h2>

      {selectedRoom ? (
        <div className="mt-5 space-y-5">
          <div className="rounded-2xl border border-white/6 bg-white/[0.03] p-4">
            <h3 className="text-xl font-semibold text-zinc-50">{selectedRoom.name}</h3>
            <p className="mt-1 text-sm text-zinc-400">{selectedRoom.room_id}</p>
            <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
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
                <p className="mt-1 text-zinc-100">{selectedRoom.width.toFixed(1)} × {selectedRoom.height.toFixed(1)}</p>
              </div>
              <div className="rounded-xl bg-white/[0.02] p-3">
                <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Exterior</p>
                <p className="mt-1 text-zinc-100">{selectedRoom.is_exterior_touching ? 'Yes' : 'No'}</p>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-white/6 bg-white/[0.03] p-4">
            <h3 className="text-sm font-semibold uppercase tracking-[0.22em] text-zinc-400">Adjacent rooms</h3>
            <div className="mt-3 space-y-2">
              {selectedRoom.adjacent_room_ids.length > 0 ? (
                selectedRoom.adjacent_room_ids.map((adjacentRoomId) => {
                  const adjacentRoom = topology.rooms.find((room) => room.room_id === adjacentRoomId)
                  return (
                    <div key={adjacentRoomId} className="rounded-xl border border-white/6 bg-black/20 px-3 py-2">
                      <p className="font-medium text-zinc-100">{adjacentRoom?.name ?? adjacentRoomId}</p>
                      <p className="text-sm text-zinc-400">{adjacentRoomId}</p>
                    </div>
                  )
                })
              ) : (
                <p className="text-sm text-zinc-500">No adjacent rooms detected.</p>
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-white/6 bg-white/[0.03] p-4">
            <h3 className="text-sm font-semibold uppercase tracking-[0.22em] text-zinc-400">Issues</h3>
            <p className="mt-2 text-sm text-zinc-200">{formatIssueList(selectedRoom.issues)}</p>
          </div>
        </div>
      ) : (
        <div className="mt-5 rounded-2xl border border-dashed border-white/10 bg-white/[0.02] p-5">
          <p className="text-sm text-zinc-300">Click any room in the canvas to inspect its topology details.</p>
          <div className="mt-4 space-y-3 text-sm">
            <div className="flex items-center justify-between rounded-xl bg-black/20 px-3 py-2">
              <span className="text-zinc-500">Rooms</span>
              <span className="text-zinc-100">{topology.rooms.length}</span>
            </div>
            <div className="flex items-center justify-between rounded-xl bg-black/20 px-3 py-2">
              <span className="text-zinc-500">Topology status</span>
              <span className="text-zinc-100">{topology.topology_readiness.status}</span>
            </div>
          </div>
        </div>
      )}
    </aside>
  )
}
