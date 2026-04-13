import { useCallback, useEffect, useRef, useState } from 'react'
import { supabase, isSupabaseConfigured } from '../../lib/supabase'
import type { PlanScene } from './project.types'

type PlanUpdates = {
  name?: string
  imageData?: string | null
  structure?: Record<string, unknown> | null
  scene?: PlanScene
  totalSqft?: number | null
}

export function usePlanSave(planId: string | null) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pendingRef = useRef<PlanUpdates>({})
  const [saving, setSaving] = useState(false)
  const [lastSaved, setLastSaved] = useState<Date | null>(null)

  const save = useCallback(async (updates: PlanUpdates) => {
    if (!planId || !isSupabaseConfigured) return
    if (Object.keys(updates).length === 0) return

    const dbUpdate: Record<string, unknown> = {}
    if (updates.name !== undefined) dbUpdate.name = updates.name
    if (updates.imageData !== undefined) dbUpdate.image_data = updates.imageData
    if (updates.structure !== undefined) dbUpdate.structure = updates.structure
    if (updates.totalSqft !== undefined) dbUpdate.total_sqft = updates.totalSqft
    if (updates.scene) {
      dbUpdate.annotations_2d = updates.scene.annotations2d
      dbUpdate.placed_items_3d = updates.scene.placedItems3d
      dbUpdate.floor_material = updates.scene.floorMaterial
      dbUpdate.wall_material = updates.scene.wallMaterial
      dbUpdate.editor_visibility = updates.scene.visibility
    }

    setSaving(true)
    const { error } = await supabase.from('plans').update(dbUpdate).eq('id', planId)
    setSaving(false)
    if (error) {
      console.error('[usePlanSave] failed:', error)
      return
    }
    setLastSaved(new Date())
  }, [planId])

  /** Accumulate partial updates; flush all at once after 2s of inactivity. */
  const debouncedSave = useCallback((updates: PlanUpdates) => {
    pendingRef.current = { ...pendingRef.current, ...updates }
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      const merged = pendingRef.current
      pendingRef.current = {}
      save(merged)
    }, 2000)
  }, [save])

  const saveNow = useCallback((updates: PlanUpdates) => {
    if (timerRef.current) clearTimeout(timerRef.current)
    const merged = { ...pendingRef.current, ...updates }
    pendingRef.current = {}
    return save(merged)
  }, [save])

  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current)
  }, [])

  return { saving, lastSaved, debouncedSave, saveNow }
}

export const useProjectSave = usePlanSave
