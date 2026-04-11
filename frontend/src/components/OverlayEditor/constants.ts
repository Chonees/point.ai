import type { AnnotationType } from '../../types'

export const COLORS: Record<AnnotationType, string> = {
  select: '#ffffff',
  wall: '#ff3333',
  door: '#33ff66',
  window: '#3399ff',
  eraser: '#888888',
  label: '#1a1a1a',
  paint: '#ffffff',
}

// Must match backend ROOM_PALETTE in scale_calibrator.py
export const ROOM_PALETTE: [number, number, number][] = [
  [66, 133, 244],    // Blue
  [219, 68, 55],     // Red
  [244, 180, 0],     // Yellow
  [15, 157, 88],     // Green
  [171, 71, 188],    // Purple
  [255, 112, 67],    // Orange
  [0, 172, 193],     // Teal
  [255, 167, 38],    // Amber
  [121, 85, 72],     // Brown
  [96, 125, 139],    // Blue Grey
  [233, 30, 99],     // Pink
  [0, 150, 136],     // Teal Dark
  [63, 81, 181],     // Indigo
  [205, 220, 57],    // Lime
  [255, 87, 34],     // Deep Orange
]
