import type { KeyboardEvent } from 'react'

import type {
  CatalogInspectorRoom,
  CatalogInspectorTopology,
  CatalogInspectorWall,
  CatalogInspectorWallTrace,
} from './types'

interface CatalogInspectorCanvasProps {
  topology: CatalogInspectorTopology
  selectedRoomId: string | null
  onSelectRoom: (roomId: string) => void
  showIds: boolean
  showAdjacency: boolean
  showWalls: boolean
  showRawTraces: boolean
}

function getViewBox(topology: CatalogInspectorTopology) {
  const padding = 24
  const box = topology.footprint_bbox
  return `${box.x1 - padding} ${box.y1 - padding} ${box.width + (padding * 2)} ${box.height + (padding * 2)}`
}

function roomPoints(room: CatalogInspectorRoom) {
  return room.polygon.map((point) => `${point.x},${point.y}`).join(' ')
}

function wallStroke(wall: CatalogInspectorWall, isHighlighted: boolean) {
  if (wall.issues.includes('inferred_from_bbox')) {
    return isHighlighted ? '#f97316' : 'rgba(249,115,22,0.78)'
  }
  if (wall.is_exterior) {
    return isHighlighted ? '#22d3ee' : 'rgba(34,211,238,0.72)'
  }
  return isHighlighted ? '#34d399' : 'rgba(52,211,153,0.76)'
}

function traceStroke(trace: CatalogInspectorWallTrace) {
  if (trace.type === 'polyline') return 'rgba(148,163,184,0.44)'
  return 'rgba(120,113,108,0.35)'
}

function tracePoints(trace: CatalogInspectorWallTrace) {
  return trace.points.map((point) => `${point.x},${point.y}`).join(' ')
}

export function CatalogInspectorCanvas({
  topology,
  selectedRoomId,
  onSelectRoom,
  showIds,
  showAdjacency,
  showWalls,
  showRawTraces,
}: CatalogInspectorCanvasProps) {
  const roomById = new Map(topology.rooms.map((room) => [room.room_id, room]))
  const roomPairs = new Set<string>()
  const rawTraces = topology.wall_traces ?? []

  const selectRoom = (roomId: string) => {
    onSelectRoom(roomId)
  }

  const handleRoomKeyDown = (event: KeyboardEvent<SVGGElement>, roomId: string) => {
    if (event.key !== 'Enter' && event.key !== ' ') return
    event.preventDefault()
    onSelectRoom(roomId)
  }

  return (
    <section className="overflow-hidden rounded-[24px] border border-white/6 bg-zinc-950/80">
      <div className="border-b border-white/6 px-5 py-4">
        <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Canvas</p>
        <h2 className="mt-2 text-lg font-semibold text-zinc-100">Plano real de topology + wall graph</h2>
        <p className="mt-1 text-sm text-zinc-400">
          Se renderiza la geometr?a real del seed curado, con rooms, IDs opcionales, relaciones, boundaries exactas o inferidas y trazas crudas del CAD para comparar fidelidad.
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

          {showRawTraces && rawTraces.map((trace) => {
            if (trace.points.length >= 2) {
              return (
                <polyline
                  key={trace.trace_id}
                  data-testid={`raw-trace-${trace.trace_id}`}
                  points={tracePoints(trace)}
                  fill="none"
                  stroke={traceStroke(trace)}
                  strokeWidth={1.25}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  vectorEffect="non-scaling-stroke"
                />
              )
            }

            if (trace.start && trace.end) {
              return (
                <line
                  key={trace.trace_id}
                  data-testid={`raw-trace-${trace.trace_id}`}
                  x1={trace.start.x}
                  y1={trace.start.y}
                  x2={trace.end.x}
                  y2={trace.end.y}
                  stroke={traceStroke(trace)}
                  strokeWidth={1.1}
                  strokeLinecap="round"
                  vectorEffect="non-scaling-stroke"
                />
              )
            }

            return null
          })}

          {showWalls && topology.walls.map((wall) => {
            const isHighlighted = !!selectedRoomId && wall.room_ids.includes(selectedRoomId)
            return (
              <line
                key={wall.wall_id}
                data-testid={`wall-${wall.wall_id}`}
                x1={wall.start.x}
                y1={wall.start.y}
                x2={wall.end.x}
                y2={wall.end.y}
                stroke={wallStroke(wall, isHighlighted)}
                strokeWidth={isHighlighted ? 5 : (wall.issues.includes('inferred_from_bbox') ? 3 : 2.5)}
                strokeDasharray={wall.issues.includes('inferred_from_bbox') ? '12 7' : undefined}
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
              />
            )
          })}

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
                role="button"
                tabIndex={0}
                aria-label={`Select ${room.name}`}
                aria-pressed={isSelected}
                onClick={() => selectRoom(room.room_id)}
                onKeyDown={(event) => handleRoomKeyDown(event, room.room_id)}
                className="cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 focus-visible:ring-offset-2 focus-visible:ring-offset-black"
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
