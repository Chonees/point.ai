import { motion } from 'framer-motion'
import type { Status } from '../../types'
import { Spinner } from '../../components/Spinner'

interface PlanMetadataCardProps {
  status: Status
  hasPlan: boolean
  onGenerate: () => void
}

export function PlanMetadataCard({
  status,
  hasPlan,
  onGenerate,
}: PlanMetadataCardProps) {
  return (
    <div className="p-5 sm:p-6">
      <div className="space-y-4">
        <div className="rounded-[24px] border border-white/6 bg-white/[0.02] p-4">
          <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Plan metadata</p>
          <p className="mt-4 text-sm leading-6 text-zinc-400">
            Upload a plan image, generate the structural DXF, then review the preview before downloading.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-1">
          <div className="rounded-[22px] border border-white/6 bg-white/[0.02] px-4 py-3">
            <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Status</p>
            <p className="mt-2 text-sm font-medium text-zinc-200">
              {status === 'done' ? 'Ready' : status === 'loading' ? 'Processing' : status === 'error' ? 'Needs attention' : 'Idle'}
            </p>
          </div>
        </div>

        <div className="rounded-[24px] border border-white/6 bg-white/[0.02] p-4">
          <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Actions</p>
          <motion.button
            whileTap={{ scale: 0.98 }}
            onClick={onGenerate}
            disabled={status === 'loading' || !hasPlan}
            className="mt-4 w-full rounded-2xl border border-white/10 bg-white/[0.06] py-3 text-sm font-medium text-zinc-200 transition-all duration-200 hover:bg-white/[0.1] disabled:cursor-not-allowed disabled:opacity-30"
          >
            {status === 'loading'
              ? <span className="flex items-center justify-center gap-2"><Spinner />Processing...</span>
              : 'Generate DXF'}
          </motion.button>
          <p className="mt-3 text-xs leading-5 text-zinc-500">
            Generate refreshes the preview and downloadable DXF from the detected structure.
          </p>
        </div>
      </div>
    </div>
  )
}
