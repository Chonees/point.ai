import { useCallback, useEffect, useState } from 'react'
import { supabase, isSupabaseConfigured } from '../../lib/supabase'
import type { ProjectData } from './project.types'

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
