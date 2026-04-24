import { usePlanList } from '../../hooks/useProject'

export function useThreadList(projectId: string | null) {
  const planList = usePlanList(projectId)

  return {
    threads: planList.plans,
    loading: planList.loading,
    refresh: planList.refresh,
    createThread: planList.createPlan,
    deleteThread: planList.deletePlan,
    renameThread: planList.renamePlan,
  }
}
