import { useState } from 'react'
import type { ProjectData, PlanData } from '../project.types'
import { PlanCard } from './PlanCard'

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

interface PlansGridProps {
  project: ProjectData | null
  plans: PlanData[]
  plansLoading: boolean
  onOpenPlan: (plan: PlanData) => void
  onCreatePlan: (name: string) => Promise<void>
  onDeletePlan: (id: string) => Promise<void>
  onRenamePlan: (id: string, name: string) => Promise<void>
}

export function PlansGrid({
  project,
  plans,
  plansLoading,
  onOpenPlan,
  onCreatePlan,
  onDeletePlan,
  onRenamePlan,
}: PlansGridProps) {
  const [newPlanName, setNewPlanName] = useState('')
  const [creating, setCreating] = useState(false)

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newPlanName.trim()) return
    setCreating(true)
    await onCreatePlan(newPlanName.trim())
    setNewPlanName('')
    setCreating(false)
  }

  if (!project) {
    return (
      <section className="rounded-[28px] border border-white/6 bg-zinc-950/80 p-5 shadow-[0_0_0_1px_rgba(255,255,255,0.02)] sm:p-6">
        <div className="flex min-h-[520px] items-center justify-center rounded-[24px] border border-dashed border-white/6 bg-white/[0.02]">
          <div className="max-w-sm text-center">
            <p className="text-xs uppercase tracking-[0.28em] text-zinc-600">No project selected</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-zinc-100">Choose a project</h2>
            <p className="mt-3 text-sm leading-6 text-zinc-500">
              Pick a project on the left to open its threads and continue the chat-based workflow.
            </p>
          </div>
        </div>
      </section>
    )
  }

  return (
    <section className="rounded-[28px] border border-white/6 bg-zinc-950/80 p-5 shadow-[0_0_0_1px_rgba(255,255,255,0.02)] sm:p-6">
      <div className="mb-5 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.28em] text-zinc-600">Project detail</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-100">{project.name}</h2>
          <p className="mt-2 text-sm text-zinc-500">
            {project.planCount} thread{project.planCount !== 1 ? 's' : ''} · Updated {formatDate(project.updatedAt)} at {formatTime(project.updatedAt)}
          </p>
        </div>

        <form onSubmit={handleCreate} className="rounded-2xl border border-white/6 bg-white/[0.02] p-3">
          <label className="block">
            <span className="mb-2 block text-[11px] uppercase tracking-[0.22em] text-zinc-600">New thread</span>
            <div className="flex gap-2">
              <input
                type="text"
                value={newPlanName}
                onChange={(e) => setNewPlanName(e.target.value)}
                placeholder="Fit Dawson"
                className="min-w-[220px] rounded-2xl border border-white/8 bg-zinc-950 px-4 py-3 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-white/16"
              />
              <button
                type="submit"
                aria-label="Add thread"
                disabled={creating || !newPlanName.trim()}
                className="rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-3 text-sm text-zinc-200 transition-colors hover:bg-white/[0.1] disabled:opacity-40"
              >
                Add thread
              </button>
            </div>
          </label>
        </form>
      </div>

      {plansLoading ? (
        <div className="rounded-2xl border border-dashed border-white/6 bg-white/[0.02] px-4 py-12 text-center text-sm text-zinc-500">
          Loading threads...
        </div>
      ) : plans.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-white/6 bg-white/[0.02] px-4 py-16 text-center">
          <p className="text-sm text-zinc-300">No threads in this project yet</p>
          <p className="mt-2 text-xs text-zinc-600">Create a thread to start the AI workflow.</p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {plans.map((plan) => (
            <PlanCard
              key={plan.id}
              plan={plan}
              onOpen={() => onOpenPlan(plan)}
              onDelete={() => { if (confirm(`Delete "${plan.name}"?`)) onDeletePlan(plan.id) }}
              onRename={(name) => onRenamePlan(plan.id, name)}
            />
          ))}
        </div>
      )}
    </section>
  )
}
