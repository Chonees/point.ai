import { useCallback, useEffect, useRef, useState } from 'react'
import { supabase, isSupabaseConfigured } from '../../lib/supabase'
import type { PlanScene } from './project.types'

export function usePlanSave(planId: string | null) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [saving, setSaving] = useState(false)
  const [lastSaved, setLastSaved] = useState<Date | null>(null)

  const save = useCallback(async (updates: {
    name?: string
    imageData?: string | null
    structure?: Record<string, unknown> | null
    scene?: PlanScene
  }) => {
    if (!planId || !isSupabaseConfigured) return

    const dbUpdate: Record<string, unknown> = {}
    if (updates.name !== undefined) dbUpdate.name = updates.name
    if (updates.imageData !== undefined) dbUpdate.image_data = updates.imageData
    if (updates.structure !== undefined) dbUpdate.structure = updates.structure
    if (updates.scene) {
      dbUpdate.annotations_2d = updates.scene.annotations2d
      dbUpdate.placed_items_3d = updates.scene.placedItems3d
      dbUpdate.floor_material = updates.scene.floorMaterial
      dbUpdate.wall_material = updates.scene.wallMaterial
    }

    setSaving(true)
    await supabase.from('plans').update(dbUpdate).eq('id', planId)
    setSaving(false)
    setLastSaved(new Date())
  }, [planId])

  const debouncedSave = useCallback((updates: Parameters<typeof save>[0]) => {
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => save(updates), 2000)
  }, [save])

  const saveNow = useCallback((updates: Parameters<typeof save>[0]) => {
    if (timerRef.current) clearTimeout(timerRef.current)
    return save(updates)
  }, [save])

  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current)
  }, [])

  return { saving, lastSaved, debouncedSave, saveNow }
}

export const useProjectSave = usePlanSave
