import type { AnnotationType } from '../../types'

export interface View { offsetX: number; offsetY: number; scale: number }
export interface SnapState { x: number; y: number; snapped: boolean }
export interface PendingDoor { x1: number; y1: number; x2: number; y2: number; sx: number; sy: number }
export interface PendingLabel { x: number; y: number; sx: number; sy: number }

export interface ToolGroupItem { type: AnnotationType; label: string; hint: string }
export interface ToolGroup { title: string; items: ToolGroupItem[] }
