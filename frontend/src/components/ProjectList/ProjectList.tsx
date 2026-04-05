import { useState } from 'react'
import type { ProjectData, PlanData } from '../../hooks/useProject'

interface ProjectListProps {
  projects: ProjectData[]
  loading: boolean
  // Project actions
  onCreateProject: (name: string) => Promise<void>
  onDeleteProject: (id: string) => Promise<void>
  onRenameProject: (id: string, name: string) => Promise<void>
  // Plan actions
  plans: PlanData[]
  plansLoading: boolean
  selectedProjectId: string | null
  onSelectProject: (id: string) => void
  onOpenPlan: (plan: PlanData) => void
  onCreatePlan: (name: string) => Promise<void>
  onDeletePlan: (id: string) => Promise<void>
  onRenamePlan: (id: string, name: string) => Promise<void>
  // Auth
  onSignOut: () => void
  userEmail?: string
}

export function ProjectList({
  projects, loading,
  onCreateProject, onDeleteProject, onRenameProject,
  plans, plansLoading, selectedProjectId,
  onSelectProject, onOpenPlan, onCreatePlan, onDeletePlan, onRenamePlan,
  onSignOut, userEmail,
}: ProjectListProps) {
  const [newProjectName, setNewProjectName] = useState('')
  const [newPlanName, setNewPlanName] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [creating, setCreating] = useState(false)

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newProjectName.trim()) return
    setCreating(true)
    await onCreateProject(newProjectName.trim())
    setNewProjectName('')
    setCreating(false)
  }

  const handleCreatePlan = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newPlanName.trim()) return
    setCreating(true)
    await onCreatePlan(newPlanName.trim())
    setNewPlanName('')
    setCreating(false)
  }

  const handleRename = async (id: string, isProject: boolean) => {
    if (!editName.trim()) return
    if (isProject) await onRenameProject(id, editName.trim())
    else await onRenamePlan(id, editName.trim())
    setEditingId(null)
  }

  const formatDate = (iso: string) => {
    const d = new Date(iso)
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) +
      ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-12">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-zinc-100">
            Pointe<span className="text-white/30">.ai</span>
          </h1>
          <p className="mt-1 text-xs text-zinc-600">{userEmail}</p>
        </div>
        <button
          onClick={onSignOut}
          className="cursor-pointer rounded-md border border-zinc-800 px-3 py-1.5 text-xs text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
        >
          Sign out
        </button>
      </div>

      <div className="flex gap-6">
        {/* Left: Projects */}
        <div className="w-1/2">
          <p className="mb-3 text-[11px] font-medium uppercase tracking-wider text-zinc-600">Projects</p>

          <form onSubmit={handleCreateProject} className="mb-4 flex gap-2">
            <input
              type="text"
              value={newProjectName}
              onChange={(e) => setNewProjectName(e.target.value)}
              placeholder="New project..."
              className="flex-1 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-zinc-600"
            />
            <button
              type="submit"
              disabled={creating || !newProjectName.trim()}
              className="cursor-pointer rounded-lg bg-white/[0.06] border border-zinc-800/60 px-4 py-2 text-sm text-zinc-400 hover:bg-white/[0.09] hover:text-zinc-300 disabled:opacity-40"
            >
              +
            </button>
          </form>

          {loading ? (
            <div className="py-10 text-center text-sm text-zinc-600">Loading...</div>
          ) : projects.length === 0 ? (
            <div className="py-10 text-center text-sm text-zinc-700">No projects yet</div>
          ) : (
            <div className="space-y-1">
              {projects.map((project) => (
                <div
                  key={project.id}
                  onClick={() => onSelectProject(project.id)}
                  className={`group flex cursor-pointer items-center justify-between rounded-lg border px-3 py-2.5 transition-colors ${
                    selectedProjectId === project.id
                      ? 'border-zinc-700 bg-zinc-800/60'
                      : 'border-zinc-800/40 hover:border-zinc-700/60 hover:bg-zinc-900/50'
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    {editingId === `p-${project.id}` ? (
                      <input
                        autoFocus
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        onBlur={() => handleRename(project.id, true)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleRename(project.id, true)
                          if (e.key === 'Escape') setEditingId(null)
                        }}
                        onClick={(e) => e.stopPropagation()}
                        className="w-full rounded border border-zinc-600 bg-zinc-800 px-2 py-0.5 text-sm text-zinc-200 outline-none"
                      />
                    ) : (
                      <>
                        <p className="truncate text-sm text-zinc-300">{project.name}</p>
                        <p className="text-[10px] text-zinc-600">
                          {project.planCount} plan{project.planCount !== 1 ? 's' : ''}
                          {' · '}{formatDate(project.updatedAt)}
                        </p>
                      </>
                    )}
                  </div>
                  <div className="ml-2 flex gap-1 opacity-0 group-hover:opacity-100">
                    <button
                      onClick={(e) => { e.stopPropagation(); setEditingId(`p-${project.id}`); setEditName(project.name) }}
                      className="cursor-pointer rounded px-1.5 py-0.5 text-[9px] text-zinc-600 hover:bg-zinc-700 hover:text-zinc-300"
                    >
                      Rename
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); if (confirm(`Delete "${project.name}"?`)) onDeleteProject(project.id) }}
                      className="cursor-pointer rounded px-1.5 py-0.5 text-[9px] text-zinc-600 hover:bg-red-900/40 hover:text-red-400"
                    >
                      Del
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right: Plans within selected project */}
        <div className="w-1/2">
          {selectedProjectId ? (
            <>
              <p className="mb-3 text-[11px] font-medium uppercase tracking-wider text-zinc-600">Floor Plans</p>

              <form onSubmit={handleCreatePlan} className="mb-4 flex gap-2">
                <input
                  type="text"
                  value={newPlanName}
                  onChange={(e) => setNewPlanName(e.target.value)}
                  placeholder="New plan..."
                  className="flex-1 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-zinc-600"
                />
                <button
                  type="submit"
                  disabled={creating || !newPlanName.trim()}
                  className="cursor-pointer rounded-lg bg-white/[0.06] border border-zinc-800/60 px-4 py-2 text-sm text-zinc-400 hover:bg-white/[0.09] hover:text-zinc-300 disabled:opacity-40"
                >
                  +
                </button>
              </form>

              {plansLoading ? (
                <div className="py-10 text-center text-sm text-zinc-600">Loading...</div>
              ) : plans.length === 0 ? (
                <div className="py-10 text-center text-sm text-zinc-700">
                  No plans yet. Create one to start editing.
                </div>
              ) : (
                <div className="space-y-1">
                  {plans.map((plan) => (
                    <div
                      key={plan.id}
                      onClick={() => onOpenPlan(plan)}
                      className="group flex cursor-pointer items-center justify-between rounded-lg border border-zinc-800/40 px-3 py-2.5 transition-colors hover:border-zinc-700/60 hover:bg-zinc-900/50"
                    >
                      <div className="flex-1 min-w-0">
                        {editingId === `l-${plan.id}` ? (
                          <input
                            autoFocus
                            value={editName}
                            onChange={(e) => setEditName(e.target.value)}
                            onBlur={() => handleRename(plan.id, false)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') handleRename(plan.id, false)
                              if (e.key === 'Escape') setEditingId(null)
                            }}
                            onClick={(e) => e.stopPropagation()}
                            className="w-full rounded border border-zinc-600 bg-zinc-800 px-2 py-0.5 text-sm text-zinc-200 outline-none"
                          />
                        ) : (
                          <>
                            <p className="truncate text-sm text-zinc-300">{plan.name}</p>
                            <p className="text-[10px] text-zinc-600">
                              {plan.scene.annotations2d.length} annotations
                              {' · '}{plan.scene.placedItems3d.length} items
                              {' · '}{formatDate(plan.updatedAt)}
                            </p>
                          </>
                        )}
                      </div>
                      <div className="ml-2 flex gap-1 opacity-0 group-hover:opacity-100">
                        <button
                          onClick={(e) => { e.stopPropagation(); setEditingId(`l-${plan.id}`); setEditName(plan.name) }}
                          className="cursor-pointer rounded px-1.5 py-0.5 text-[9px] text-zinc-600 hover:bg-zinc-700 hover:text-zinc-300"
                        >
                          Rename
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); if (confirm(`Delete "${plan.name}"?`)) onDeletePlan(plan.id) }}
                          className="cursor-pointer rounded px-1.5 py-0.5 text-[9px] text-zinc-600 hover:bg-red-900/40 hover:text-red-400"
                        >
                          Del
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="flex h-full items-center justify-center py-20">
              <p className="text-sm text-zinc-700">Select a project to see its plans</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
