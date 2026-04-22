import type { KeyboardEvent } from 'react'

import type {
  CatalogInspectorBoundary,
  CatalogInspectorBoundaryNode,
  CatalogInspectorCadTrace,
  CatalogInspectorOpening,
  CatalogInspectorRoom,
  CatalogInspectorTopology,
  CatalogInspectorWall,
} from './types'

interface CatalogInspectorCanvasProps {
  topology: CatalogInspectorTopology
  visibleWalls: CatalogInspectorWall[]
  selectedRoomId: string | null
  selectedWallId: string | null
  selectedBoundaryId: string | null
  selectedOpeningId: string | null
  onSelectRoom: (roomId: string) => void
  onSelectWall: (wallId: string) => void
  onSelectBoundary: (boundaryId: string) => void
  onSelectOpening: (openingId: string, hostWallId?: string | null) => void
  showIds: boolean
  showAdjacency: boolean
  showWalls: boolean
  showExactBoundaries: boolean
  showRawWallTraces: boolean
  showDoorTraces: boolean
  showWindowTraces: boolean
  showHostedOpenings: boolean
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
  if (wall.trace_support_status === 'unsupported') {
    return isHighlighted ? '#fb7185' : 'rgba(244,63,94,0.82)'
  }
  if (wall.trace_support_status === 'snapped_to_trace') {
    return isHighlighted ? '#fbbf24' : 'rgba(245,158,11,0.82)'
  }
  if (wall.provenance === 'bbox_inferred') {
    return isHighlighted ? '#f97316' : 'rgba(249,115,22,0.78)'
  }
  if (wall.is_exterior) {
    return isHighlighted ? '#22d3ee' : 'rgba(34,211,238,0.72)'
  }
  return isHighlighted ? '#34d399' : 'rgba(52,211,153,0.76)'
}

function wallDashArray(wall: CatalogInspectorWall) {
  if (wall.trace_support_status === 'unsupported') return '8 6'
  if (wall.provenance === 'bbox_inferred') return '12 7'
  return undefined
}

function traceStroke(trace: CatalogInspectorCadTrace, isSelected: boolean) {
  if (isSelected) return 'rgba(248,250,252,0.98)'
  if (trace.trace_kind === 'door') {
    return trace.type === 'polyline' ? 'rgba(244,114,182,0.62)' : 'rgba(232,121,249,0.54)'
  }
  if (trace.trace_kind === 'window') {
    return trace.type === 'polyline' ? 'rgba(99,102,241,0.62)' : 'rgba(129,140,248,0.56)'
  }
  if (trace.type === 'polyline') return 'rgba(148,163,184,0.44)'
  return 'rgba(120,113,108,0.35)'
}

function tracePoints(trace: CatalogInspectorCadTrace) {
  return trace.points.map((point) => `${point.x},${point.y}`).join(' ')
}

function openingStroke(opening: CatalogInspectorOpening, isSelected: boolean) {
  if (opening.opening_kind === 'window') {
    return isSelected ? '#c4b5fd' : 'rgba(129,140,248,0.85)'
  }
  return isSelected ? '#f9a8d4' : 'rgba(232,121,249,0.85)'
}

function boundaryStroke(boundary: CatalogInspectorBoundary, isSelected: boolean) {
  if (boundary.family_role === 'duplicate' || boundary.boundary_kind === 'duplicate') {
    return isSelected ? '#fda4af' : 'rgba(251,113,133,0.58)'
  }
  if (boundary.boundary_kind === 'shared') return isSelected ? '#fde68a' : 'rgba(250,204,21,0.82)'
  if (boundary.boundary_kind === 'exterior') return isSelected ? '#67e8f9' : 'rgba(34,211,238,0.68)'
  if (boundary.boundary_kind === 'support') return isSelected ? '#c4b5fd' : 'rgba(167,139,250,0.72)'
  return isSelected ? '#fca5a5' : 'rgba(248,113,113,0.58)'
}

function boundaryNodeFill(node: CatalogInspectorBoundaryNode, isSelected: boolean) {
  if (isSelected) return '#f8fafc'
  if (node.node_kind === 'opening_cut') return '#f9a8d4'
  if (node.node_kind === 'tee') return '#fcd34d'
  return '#94a3b8'
}

export function CatalogInspectorCanvas({
  topology,
  visibleWalls,
  selectedRoomId,
  selectedWallId,
  selectedBoundaryId,
  selectedOpeningId,
  onSelectRoom,
  onSelectWall,
  onSelectBoundary,
  onSelectOpening,
  showIds,
  showAdjacency,
  showWalls,
  showExactBoundaries,
  showRawWallTraces,
  showDoorTraces,
  showWindowTraces,
  showHostedOpenings,
}: CatalogInspectorCanvasProps) {
  const roomById = new Map(topology.rooms.map((room) => [room.room_id, room]))
  const roomPairs = new Set<string>()
  const cadTraces = topology.cad_traces ?? []
  const boundaries = topology.boundaries ?? []
  const boundaryNodes = topology.boundary_nodes ?? []
  const visibleOpenings = topology.openings ?? []
  const selectedWall = visibleWalls.find((wall) => wall.wall_id === selectedWallId) ?? null
  const selectedBoundary = boundaries.find((boundary) => boundary.boundary_id === selectedBoundaryId) ?? null
  const selectedOpening = visibleOpenings.find((opening) => opening.opening_id === selectedOpeningId) ?? null
  const selectedTraceIds = new Set([...(selectedWall?.trace_support_ids ?? []), ...(selectedOpening?.trace_ids ?? [])])
  const selectedBoundaryNodeIds = new Set(
    selectedBoundary ? [selectedBoundary.start_node_id, selectedBoundary.end_node_id] : [],
  )
  const visibleTraces = cadTraces.filter((trace) => {
    if (trace.trace_kind === 'wall') return showRawWallTraces
    if (trace.trace_kind === 'door') return showDoorTraces
    if (trace.trace_kind === 'window') return showWindowTraces
    return false
  })

  const handleRoomKeyDown = (event: KeyboardEvent<SVGGElement>, roomId: string) => {
    if (event.key !== 'Enter' && event.key !== ' ') return
    event.preventDefault()
    onSelectRoom(roomId)
  }

  const handleWallKeyDown = (event: KeyboardEvent<SVGLineElement>, wallId: string) => {
    if (event.key !== 'Enter' && event.key !== ' ') return
    event.preventDefault()
    onSelectWall(wallId)
  }

  return (
    <section className="overflow-hidden rounded-[24px] border border-white/6 bg-zinc-950/80">
      <div className="border-b border-white/6 px-5 py-4">
        <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Canvas</p>
        <h2 className="mt-2 text-lg font-semibold text-zinc-100">Plano real de topology + wall graph</h2>
        <p className="mt-1 text-sm text-zinc-400">
          Se renderiza la geometría real del seed curado, con rooms, IDs opcionales, relaciones, boundaries y trazas CAD separadas por walls, doors y windows para comparar fidelidad.
        </p>
        <p className="mt-2 text-xs text-zinc-500">
          Verde/cian = exactas. Ámbar = snapped a traza real. Rojo = sin soporte real. Gris = walls crudas. Fucsia = doors. Índigo = windows.
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

          {visibleTraces.map((trace) => {
            const isSelectedTrace = selectedTraceIds.has(trace.trace_id)
            const traceTestId = `raw-${trace.trace_kind}-trace-${trace.trace_id}`
            if (trace.points.length >= 2) {
              return (
                <polyline
                  key={trace.trace_id}
                  data-testid={traceTestId}
                  points={tracePoints(trace)}
                  fill="none"
                  stroke={traceStroke(trace, isSelectedTrace)}
                  strokeWidth={isSelectedTrace ? 2.4 : 1.25}
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
                  data-testid={traceTestId}
                  x1={trace.start.x}
                  y1={trace.start.y}
                  x2={trace.end.x}
                  y2={trace.end.y}
                  stroke={traceStroke(trace, isSelectedTrace)}
                  strokeWidth={isSelectedTrace ? 2.2 : 1.1}
                  strokeLinecap="round"
                  vectorEffect="non-scaling-stroke"
                />
              )
            }

            return null
          })}

          {showWalls && visibleWalls.map((wall) => {
            const isWallSelected = wall.wall_id === selectedWallId
            const isRoomHighlighted = !!selectedRoomId && wall.room_ids.includes(selectedRoomId)
            const isHighlighted = isWallSelected || isRoomHighlighted
            return (
              <line
                key={wall.wall_id}
                data-testid={`wall-${wall.wall_id}`}
                role="button"
                tabIndex={0}
                aria-label={`Select wall ${wall.wall_id}`}
                x1={wall.start.x}
                y1={wall.start.y}
                x2={wall.end.x}
                y2={wall.end.y}
                stroke={wallStroke(wall, isHighlighted)}
                strokeWidth={isWallSelected ? 6 : isHighlighted ? 5 : (wall.provenance === 'bbox_inferred' ? 3 : 2.5)}
                strokeDasharray={wallDashArray(wall)}
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
                onClick={() => onSelectWall(wall.wall_id)}
                onKeyDown={(event) => handleWallKeyDown(event, wall.wall_id)}
              />
            )
          })}

          {showExactBoundaries && boundaries.map((boundary) => {
            const isSelected = boundary.boundary_id === selectedBoundaryId
            return (
              <line
                key={boundary.boundary_id}
                data-testid={`boundary-${boundary.boundary_id}`}
                role="button"
                tabIndex={0}
                aria-label={`Select boundary ${boundary.boundary_id}`}
                x1={boundary.start.x}
                y1={boundary.start.y}
                x2={boundary.end.x}
                y2={boundary.end.y}
                stroke={boundaryStroke(boundary, isSelected)}
                strokeWidth={isSelected ? 4.5 : 2}
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
                onClick={() => onSelectBoundary(boundary.boundary_id)}
                onKeyDown={(event) => {
                  if (event.key !== 'Enter' && event.key !== ' ') return
                  event.preventDefault()
                  onSelectBoundary(boundary.boundary_id)
                }}
              />
            )
          })}

          {showExactBoundaries && boundaryNodes.map((node) => {
            const isSelected = selectedBoundaryNodeIds.has(node.node_id)
            return (
              <circle
                key={node.node_id}
                data-testid={`boundary-node-${node.node_id}`}
                cx={node.point.x}
                cy={node.point.y}
                r={isSelected ? 3.6 : 2.2}
                fill={boundaryNodeFill(node, isSelected)}
                opacity={isSelected ? 1 : 0.82}
              />
            )
          })}

          {showHostedOpenings && visibleOpenings.map((opening) => {
            const isSelected = opening.opening_id === selectedOpeningId
            return (
              <line
                key={opening.opening_id}
                data-testid={`opening-${opening.opening_id}`}
                role="button"
                tabIndex={0}
                aria-label={`Select opening ${opening.opening_id}`}
                x1={opening.start.x}
                y1={opening.start.y}
                x2={opening.end.x}
                y2={opening.end.y}
                stroke={openingStroke(opening, isSelected)}
                strokeWidth={isSelected ? 7 : 4}
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
                onClick={() => onSelectOpening(opening.opening_id, opening.host_wall_id)}
                onKeyDown={(event) => {
                  if (event.key !== 'Enter' && event.key !== ' ') return
                  event.preventDefault()
                  onSelectOpening(opening.opening_id, opening.host_wall_id)
                }}
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
                onClick={() => onSelectRoom(room.room_id)}
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

