import type { CatalogInspectorRoom, CatalogInspectorTopology } from './types'

interface CatalogInspectorCanvasProps {
  topology: CatalogInspectorTopology
  selectedRoomId: string | null
  onSelectRoom: (roomId: string) => void
  showIds: boolean
  showAdjacency: boolean
}

function getViewBox(topology: CatalogInspectorTopology) {
  const padding = 24
  const box = topology.footprint_bbox
  return `${box.x1 - padding} ${box.y1 - padding} ${box.width + (padding * 2)} ${box.height + (padding * 2)}`
}

function roomPoints(room: CatalogInspectorRoom) {
  return room.polygon.map((point) => `${point.x},${point.y}`).join(' ')
}

export function CatalogInspectorCanvas({
  topology,
  selectedRoomId,
  onSelectRoom,
  showIds,
  showAdjacency,
}: CatalogInspectorCanvasProps) {
  const roomById = new Map(topology.rooms.map((room) => [room.room_id, room]))
  const roomPairs = new Set<string>()

  return (
    <section className="overflow-hidden rounded-[24px] border border-white/6 bg-zinc-950/80">
      <div className="border-b border-white/6 px-5 py-4">
        <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Canvas</p>
        <h2 className="mt-2 text-lg font-semibold text-zinc-100">Plano real de topology</h2>
        <p className="mt-1 text-sm text-zinc-400">
          Se renderiza la geometría real del seed curado, con rooms, IDs opcionales y relaciones de adyacencia.
        </p>
      </div>

      <div className="p-4">
        <svg
          data-testid="catalog-inspector-canvas"
          role="img"
          aria-label={`${topology.name} catalog inspector canvas`}
          viewBox={getViewBox(topology)}
          className="h-[640px] w-full rounded-[20px] bg-[#050505]"
          preserveAspectRatio="xMidYMid meet"
        >
          <rect
            x={topology.footprint_bbox.x1}
            y={topology.footprint_bbox.y1}
            width={topology.footprint_bbox.width}
            height={topology.footprint_bbox.height}
            fill="rgba(255,255,255,0.02)"
            stroke="rgba(255,255,255,0.10)"
            strokeWidth={2}
          />

          {showAdjacency && topology.rooms.flatMap((room) => room.adjacent_room_ids.map((adjacentRoomId) => {
            const pairKey = [room.room_id, adjacentRoomId].sort().join('::')
            if (roomPairs.has(pairKey)) return null
            roomPairs.add(pairKey)

            const adjacentRoom = roomById.get(adjacentRoomId)
            if (!adjacentRoom) return null

            const isSelected = selectedRoomId === room.room_id || selectedRoomId === adjacentRoomId
            return (
              <line
                key={pairKey}
                data-testid={`adjacency-link-${pairKey}`}
                x1={room.centroid.x}
                y1={room.centroid.y}
                x2={adjacentRoom.centroid.x}
                y2={adjacentRoom.centroid.y}
                stroke={isSelected ? 'rgba(56,189,248,0.95)' : 'rgba(56,189,248,0.45)'}
                strokeWidth={isSelected ? 3 : 2}
                strokeDasharray="10 7"
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
              />
            )
          }))}

          {topology.rooms.map((room) => {
            const isSelected = room.room_id === selectedRoomId
            const isExposed = room.is_exterior_touching
            const polygonFill = isSelected ? 'rgba(56,189,248,0.30)' : 'rgba(24,24,27,0.50)'
            const polygonStroke = isSelected ? '#7dd3fc' : (isExposed ? '#f59e0b' : '#9ca3af')

            return (
              <g
                key={room.room_id}
                data-testid={`room-${room.room_id}`}
                onClick={() => onSelectRoom(room.room_id)}
                className="cursor-pointer"
              >
                <polygon
                  points={roomPoints(room)}
                  fill={polygonFill}
                  stroke={polygonStroke}
                  strokeWidth={isSelected ? 4 : 2.25}
                  strokeLinejoin="round"
                  vectorEffect="non-scaling-stroke"
                />

                <text
                  x={room.centroid.x}
                  y={room.centroid.y - 6}
                  textAnchor="middle"
                  fill="#f8fafc"
                  fontSize={16}
                  fontWeight={700}
                  paintOrder="stroke"
                  stroke="#020617"
                  strokeWidth={4}
                >
                  {room.name}
                </text>

                {showIds && (
                  <text
                    data-testid={`room-id-label-${room.room_id}`}
                    x={room.centroid.x}
                    y={room.centroid.y + 14}
                    textAnchor="middle"
                    fill="#cbd5e1"
                    fontSize={12}
                    fontWeight={600}
                    paintOrder="stroke"
                    stroke="#020617"
                    strokeWidth={3}
                  >
                    {room.room_id}
                  </text>
                )}

                {isExposed && (
                  <circle
                    cx={room.bbox.x2 - 8}
                    cy={room.bbox.y1 + 8}
                    r={4}
                    fill="#f59e0b"
                  />
                )}
              </g>
            )
          })}
        </svg>
      </div>
    </section>
  )
}
