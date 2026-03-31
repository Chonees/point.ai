import type { AnnotationType } from '../../types'

export const COLORS: Record<AnnotationType, string> = {
  wall: '#ff3333',
  door: '#33ff66',
  window: '#3399ff',
  eraser: '#888888',
}

export const TOOL_DEFS: { type: AnnotationType; label: string; color: string }[] = [
  { type: 'wall', label: 'Wall', color: 'bg-red-900/40 border-red-700/50 text-red-400' },
  { type: 'door', label: 'Door', color: 'bg-green-900/40 border-green-700/50 text-green-400' },
  { type: 'window', label: 'Window', color: 'bg-blue-900/40 border-blue-700/50 text-blue-400' },
  { type: 'eraser', label: 'Eraser', color: 'bg-zinc-700/40 border-zinc-500/50 text-zinc-300' },
]
