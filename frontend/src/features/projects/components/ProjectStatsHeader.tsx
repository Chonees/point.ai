import type { ProjectData } from '../project.types'

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

interface ProjectStatsHeaderProps {
  projects: ProjectData[]
  totalPlans: number
  userEmail?: string
  onSignOut: () => void
}

export function ProjectStatsHeader({ projects, totalPlans, userEmail, onSignOut }: ProjectStatsHeaderProps) {
  const recentProject = projects[0] ?? null

  return (
    <header className="mb-6 rounded-[28px] border border-white/6 bg-zinc-950/80 p-5 shadow-[0_0_0_1px_rgba(255,255,255,0.02)] sm:p-6">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.04] text-sm font-semibold text-zinc-100">
              P
            </div>
            <div>
              <h1 className="text-xl font-semibold tracking-tight text-zinc-100">
                Pointe<span className="text-white/30">.ai</span>
              </h1>
              <p className="text-xs uppercase tracking-[0.24em] text-zinc-600">Workspace</p>
            </div>
          </div>
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            <div className="rounded-2xl border border-white/6 bg-white/[0.02] px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Projects</p>
              <p className="mt-2 text-2xl font-semibold tracking-tight text-zinc-100">{projects.length}</p>
            </div>
            <div className="rounded-2xl border border-white/6 bg-white/[0.02] px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Plans</p>
              <p className="mt-2 text-2xl font-semibold tracking-tight text-zinc-100">{totalPlans}</p>
            </div>
            <div className="rounded-2xl border border-white/6 bg-white/[0.02] px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Latest activity</p>
              <p className="mt-2 text-sm font-medium text-zinc-200">
                {recentProject ? `${formatDate(recentProject.updatedAt)} at ${formatTime(recentProject.updatedAt)}` : 'No activity yet'}
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="rounded-2xl border border-white/6 bg-white/[0.02] px-4 py-3 text-right">
            <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Signed in</p>
            <p className="mt-1 text-sm text-zinc-300">{userEmail}</p>
          </div>
          <button
            onClick={onSignOut}
            className="rounded-2xl border border-white/8 bg-zinc-950 px-4 py-3 text-sm text-zinc-300 transition-colors hover:border-white/14 hover:bg-white/[0.03]"
          >
            Sign out
          </button>
        </div>
      </div>
    </header>
  )
}
