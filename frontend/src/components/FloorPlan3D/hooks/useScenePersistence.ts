import { useEffect } from 'react'
import { FURNITURE, MATERIALS } from '../catalog'
import type { MaterialPreset } from '../catalog'
import type { PlacedFurniture } from '../types'
import type { Annotation } from '../../../types'
import type { PlanScene } from '../../../hooks/useProject'
import type { PlacedItemDB } from '../../../lib/database.types'

export function dbToPlaced(items: PlacedItemDB[]): PlacedFurniture[] {
  return items.map((db) => {
    const catalogItem = FURNITURE.find((f) => f.id === db.itemId)
    if (!catalogItem) return null
    return {
      item: catalogItem,
      x: db.x,
      y: db.y,
      z: db.z,
      rotation: db.rotation,
      scaleW: db.scaleW,
      scaleD: db.scaleD,
      scaleH: db.scaleH ?? 1,
      tintColor: db.tintColor,
    }
  }).filter(Boolean) as PlacedFurniture[]
}

export function placedToDb(items: PlacedFurniture[]): PlacedItemDB[] {
  return items.map((p) => ({
    itemId: p.item.id,
    x: p.x,
    y: p.y,
    z: p.z,
    rotation: p.rotation,
    scaleW: p.scaleW,
    scaleD: p.scaleD,
    scaleH: p.scaleH,
    tintColor: p.tintColor,
  }))
}

export function resolveInitialMaterials(initialScene?: PlanScene): {
  floorMat: MaterialPreset
  wallMat: MaterialPreset
} {
  const floorMat =
    MATERIALS.find((m) => m.id === initialScene?.floorMaterial) ?? MATERIALS[0]
  const wallMat =
    MATERIALS.find((m) => m.id === initialScene?.wallMaterial) ??
    MATERIALS.find((m) => m.category === 'wall') ??
    MATERIALS[0]
  return { floorMat, wallMat }
}

export function useAutoSave({
  placed,
  floorMat,
  wallMat,
  annotations,
  onSceneChange,
}: {
  placed: PlacedFurniture[]
  floorMat: MaterialPreset
  wallMat: MaterialPreset
  annotations: Annotation[]
  onSceneChange?: (scene: PlanScene) => void
}) {
  useEffect(() => {
    if (!onSceneChange) return
    onSceneChange({
      annotations2d: annotations,
      placedItems3d: placedToDb(placed),
      floorMaterial: floorMat.id,
      wallMaterial: wallMat.id,
    })
  }, [placed, floorMat, wallMat]) // eslint-disable-line react-hooks/exhaustive-deps
}
