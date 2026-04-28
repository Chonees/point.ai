import { useCallback, useEffect, useState } from 'react'
import { supabase, isSupabaseConfigured } from '../../lib/supabase'
import type { PlanData } from './project.types'
import { rowToPlan } from './project.mappers'

export function usePlanList(projectId: string | null) {
  const [plans, setPlans] = useState<PlanData[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    if (!projectId || !isSupabaseConfigured) {
      setPlans([])
      setLoading(false)
      return
    }
    setLoading(true)
    const { data, error } = await supabase
      .from('plans')
      .select('*')
      .eq('project_id', projectId)
      .order('created_at', { ascending: true })

    if (!error && data) {
      setPlans(data.map(rowToPlan))
    }
    setLoading(false)
  }, [projectId])

  useEffect(() => { refresh() }, [refresh])

  const createPlan = useCallback(async (name: string): Promise<PlanData | null> => {
    if (!projectId || !isSupabaseConfigured) return null
    const { data, error } = await supabase
      .from('plans')
      .insert({
        project_id: projectId,
        name,
        image_data: null,
        structure: null,
        reviewed_opening_annotations: [],
        placed_items_3d: [],
        floor_material: 'hardwood',
        wall_material: 'white-paint',
      })
      .select()
      .single()

    if (error || !data) return null
    const plan = rowToPlan(data)
    setPlans((prev) => [...prev, plan])
    return plan
  }, [projectId])

  const deletePlan = useCallback(async (id: string) => {
    if (!isSupabaseConfigured) return
    const { error } = await supabase.from('plans').delete().eq('id', id)
    if (!error) setPlans((prev) => prev.filter((p) => p.id !== id))
  }, [])

  const renamePlan = useCallback(async (id: string, name: string) => {
    if (!isSupabaseConfigured) return
    await supabase.from('plans').update({ name }).eq('id', id)
    setPlans((prev) => prev.map((p) => p.id === id ? { ...p, name } : p))
  }, [])

  return { plans, loading, refresh, createPlan, deletePlan, renamePlan }
}
