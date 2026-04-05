import { useCallback, useEffect, useRef, useState } from 'react'
import { supabase, isSupabaseConfigured } from '../lib/supabase'
import type { PlanRow, PlacedItemDB } from '../lib/database.types'
import type { Annotation } from '../types'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface ProjectData {
  id: string
  name: string
  createdAt: string
  updatedAt: string
  planCount: number
}

export interface PlanScene {
  annotations2d: Annotation[]
  placedItems3d: PlacedItemDB[]
  floorMaterial: string
  wallMaterial: string
}

// Keep this alias for App.tsx compatibility
export type ProjectScene = PlanScene

export interface PlanData {
  id: string
  projectId: string
  name: string
  imageData: string | null
  structure: Record<string, unknown> | null
  scene: PlanScene
  createdAt: string
  updatedAt: string
}

function rowToPlan(row: PlanRow): PlanData {
  return {
    id: row.id,
    projectId: row.project_id,
    name: row.name,
    imageData: row.image_data,
    structure: row.structure,
    scene: {
      annotations2d: row.annotations_2d ?? [],
      placedItems3d: row.placed_items_3d ?? [],
      floorMaterial: row.floor_material,
      wallMaterial: row.wall_material,
    },
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  }
}

/* ------------------------------------------------------------------ */
/*  useProjectList — top-level projects                                */
/* ------------------------------------------------------------------ */

export function useProjectList(userId: string | undefined) {
  const [projects, setProjects] = useState<ProjectData[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    if (!userId || !isSupabaseConfigured) {
      setProjects([])
      setLoading(false)
      return
    }
    setLoading(true)
    // Get projects with plan count
    const { data, error } = await supabase
      .from('projects')
      .select('*, plans(count)')
      .eq('user_id', userId)
      .order('updated_at', { ascending: false })

    if (!error && data) {
      setProjects(data.map((row: any) => ({
        id: row.id,
        name: row.name,
        createdAt: row.created_at,
        updatedAt: row.updated_at,
        planCount: row.plans?.[0]?.count ?? 0,
      })))
    }
    setLoading(false)
  }, [userId])

  useEffect(() => { refresh() }, [refresh])

  const createProject = useCallback(async (name: string): Promise<ProjectData | null> => {
    if (!userId || !isSupabaseConfigured) return null
    const { data, error } = await supabase
      .from('projects')
      .insert({ user_id: userId, name })
      .select()
      .single()

    if (error || !data) return null
    const project: ProjectData = {
      id: data.id, name: data.name,
      createdAt: data.created_at, updatedAt: data.updated_at,
      planCount: 0,
    }
    setProjects((prev) => [project, ...prev])
    return project
  }, [userId])

  const deleteProject = useCallback(async (id: string) => {
    if (!isSupabaseConfigured) return
    const { error } = await supabase.from('projects').delete().eq('id', id)
    if (!error) setProjects((prev) => prev.filter((p) => p.id !== id))
  }, [])

  const renameProject = useCallback(async (id: string, name: string) => {
    if (!isSupabaseConfigured) return
    await supabase.from('projects').update({ name }).eq('id', id)
    setProjects((prev) => prev.map((p) => p.id === id ? { ...p, name } : p))
  }, [])

  return { projects, loading, refresh, createProject, deleteProject, renameProject }
}

/* ------------------------------------------------------------------ */
/*  usePlanList — plans within a project                               */
/* ------------------------------------------------------------------ */

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
        annotations_2d: [],
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

/* ------------------------------------------------------------------ */
/*  usePlanSave — auto-save a single plan                              */
/* ------------------------------------------------------------------ */

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

// Legacy alias
export const useProjectSave = usePlanSave
