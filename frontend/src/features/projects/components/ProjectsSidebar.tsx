import { useState } from 'react'
import type { ProjectData } from '../project.types'

function initials(name: string) {
  return name.split(' ').filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase() ?? '').join('')
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

interface ProjectsSidebarProps {
  projects: ProjectData[]
  loading: boolean
  selectedProjectId: string | null
  onSelectProject: (id: string) => void
  onCreateProject: (name: string) => Promise<void>
  onDeleteProject: (id: string) => Promise<void>
  onRenameProject: (id: string, name: string) => Promise<void>
}

export function ProjectsSidebar({
  projects,
  loading,
  selectedProjectId,
  onSelectProject,
  onCreateProject,
  onDeleteProject,
  onRenameProject,
}: ProjectsSidebarProps) {
  const [newProjectName, setNewProjectName] = useState('')
  const [creating, setCreating] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newProjectName.trim()) return
    setCreating(true)
    await onCreateProject(newProjectName.trim())
    setNewProjectName('')
    setCreating(false)
  }

  const handleRename = async (id: string) => {
    if (!editName.trim()) return
    await onRenameProject(id, editName.trim())
    setEditingId(null)
  }

  return (
    <section className="rounded-[28px] border border-white/6 bg-zinc-950/80 p-5 shadow-[0_0_0_1px_rgba(255,255,255,0.02)] sm:p-6">
      <div className="mb-5 flex items-end justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.28em] text-zinc-600">Projects</p>
          <h2 className="mt-2 text-xl font-semibold tracking-tight text-zinc-100">Your workspace</h2>
        </div>
        <span className="rounded-full border border-white/8 px-3 py-1 text-[10px] uppercase tracking-[0.22em] text-zinc-500">
          {projects.length} active
        </span>
      </div>

      <form onSubmit={handleCreate} className="mb-5 rounded-2xl border border-white/6 bg-white/[0.02] p-3">
        <label className="block">
          <span className="mb-2 block text-[11px] uppercase tracking-[0.22em] text-zinc-600">New project</span>
          <div className="flex gap-2">
            <input
              type="text"
              value={newProjectName}
              onChange={(e) => setNewProjectName(e.target.value)}
              placeholder="Seminole rollout"
              className="flex-1 rounded-2xl border border-white/8 bg-zinc-950 px-4 py-3 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-white/16"
            />
            <button
              type="submit"
              disabled={creating || !newProjectName.trim()}
              className="rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-3 text-sm text-zinc-200 transition-colors hover:bg-white/[0.1] disabled:opacity-40"
            >
              Create
            </button>
          </div>
        </label>
      </form>

      {loading ? (
        <div className="rounded-2xl border border-dashed border-white/6 bg-white/[0.02] px-4 py-12 text-center text-sm text-zinc-500">
          Loading projects...
        </div>
      ) : projects.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-white/6 bg-white/[0.02] px-4 py-12 text-center">
          <p className="text-sm text-zinc-300">No projects yet</p>
          <p className="mt-2 text-xs text-zinc-600">Create your first project to start new AI threads.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {projects.map((project) => {
            const active = selectedProjectId === project.id
            return (
              <article
                key={project.id}
                className={`group rounded-[24px] border px-4 py-4 transition-all ${
                  active
                    ? 'border-white/14 bg-white/[0.06] shadow-[0_0_0_1px_rgba(255,255,255,0.04)]'
                    : 'border-white/6 bg-white/[0.02] hover:border-white/12 hover:bg-white/[0.04]'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <button
                    type="button"
                    aria-label={`Open project ${project.name}`}
                    onClick={() => onSelectProject(project.id)}
                    className="flex min-w-0 flex-1 items-start gap-3 text-left"
                  >
                    <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-white/8 bg-zinc-950 text-xs font-semibold tracking-[0.2em] text-zinc-300">
                      {initials(project.name) || 'PR'}
                    </div>
                    <div className="min-w-0">
                      {editingId === project.id ? (
                        <input
                          autoFocus
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          onBlur={() => handleRename(project.id)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handleRename(project.id)
                            if (e.key === 'Escape') setEditingId(null)
                          }}
                          onClick={(e) => e.stopPropagation()}
                          className="w-full rounded-xl border border-white/10 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none"
                        />
                      ) : (
                        <>
                          <p className="truncate text-base font-medium text-zinc-100">{project.name}</p>
                          <p className="mt-1 text-xs text-zinc-500">
                            {project.planCount} thread{project.planCount !== 1 ? 's' : ''} · Updated {formatDate(project.updatedAt)}
                          </p>
                        </>
                      )}
                    </div>
                  </button>
                  <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                    <button
                      type="button"
                      aria-label={`Rename project ${project.name}`}
                      onClick={() => {
                        setEditingId(project.id)
                        setEditName(project.name)
                      }}
                      className="rounded-xl border border-white/8 px-2.5 py-1.5 text-[11px] text-zinc-400 hover:border-white/14 hover:text-zinc-200"
                    >
                      Rename
                    </button>
                    <button
                      type="button"
                      aria-label={`Delete project ${project.name}`}
                      onClick={() => {
                        if (confirm(`Delete "${project.name}"?`)) onDeleteProject(project.id)
                      }}
                      className="rounded-xl border border-white/8 px-2.5 py-1.5 text-[11px] text-zinc-500 hover:border-red-500/20 hover:bg-red-500/8 hover:text-red-300"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </article>
            )
          })}
        </div>
      )}
    </section>
  )
}
