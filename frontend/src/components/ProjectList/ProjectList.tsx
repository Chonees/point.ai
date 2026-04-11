import { useMemo } from 'react'
import type { ProjectData, PlanData } from '../../features/projects'
import { ProjectStatsHeader } from '../../features/projects/components/ProjectStatsHeader'
import { ProjectsSidebar } from '../../features/projects/components/ProjectsSidebar'
import { PlansGrid } from '../../features/projects/components/PlansGrid'

interface ProjectListProps {
  projects: ProjectData[]
  loading: boolean
  onCreateProject: (name: string) => Promise<void>
  onDeleteProject: (id: string) => Promise<void>
  onRenameProject: (id: string, name: string) => Promise<void>
  plans: PlanData[]
  plansLoading: boolean
  selectedProjectId: string | null
  onSelectProject: (id: string) => void
  onOpenPlan: (plan: PlanData) => void
  onCreatePlan: (name: string) => Promise<void>
  onDeletePlan: (id: string) => Promise<void>
  onRenamePlan: (id: string, name: string) => Promise<void>
  onSignOut: () => void
  userEmail?: string
}

export function ProjectList({
  projects,
  loading,
  onCreateProject,
  onDeleteProject,
  onRenameProject,
  plans,
  plansLoading,
  selectedProjectId,
  onSelectProject,
  onOpenPlan,
  onCreatePlan,
  onDeletePlan,
  onRenamePlan,
  onSignOut,
  userEmail,
}: ProjectListProps) {
  const selectedProject = projects.find((p) => p.id === selectedProjectId) ?? null
  const totalPlans = useMemo(() => projects.reduce((sum, p) => sum + p.planCount, 0), [projects])

  return (
    <div className="min-h-screen bg-[#090909] text-zinc-100">
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <ProjectStatsHeader
          projects={projects}
          totalPlans={totalPlans}
          userEmail={userEmail}
          onSignOut={onSignOut}
        />

        <div className="grid gap-6 xl:grid-cols-[0.95fr_1.45fr]">
          <ProjectsSidebar
            projects={projects}
            loading={loading}
            selectedProjectId={selectedProjectId}
            onSelectProject={onSelectProject}
            onCreateProject={onCreateProject}
            onDeleteProject={onDeleteProject}
            onRenameProject={onRenameProject}
          />

          <PlansGrid
            project={selectedProject}
            plans={plans}
            plansLoading={plansLoading}
            onOpenPlan={onOpenPlan}
            onCreatePlan={onCreatePlan}
            onDeletePlan={onDeletePlan}
            onRenamePlan={onRenamePlan}
          />
        </div>
      </div>
    </div>
  )
}
