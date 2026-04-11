import { motion } from 'framer-motion'
import type { Status } from '../../types'
import { Spinner } from '../../components/Spinner'

interface PlanMetadataCardProps {
  totalSqft: string
  onTotalSqftChange: (value: string) => void
  labelCount: number
  computedRoomCount: number
  status: Status
  hasPlan: boolean
  onGenerate: () => void
}

export function PlanMetadataCard({
  totalSqft,
  onTotalSqftChange,
  labelCount,
  computedRoomCount,
  status,
  hasPlan,
  onGenerate,
}: PlanMetadataCardProps) {
  return (
    <div className="p-5 sm:p-6">
      <div className="space-y-4">
        <div className="rounded-[24px] border border-white/6 bg-white/[0.02] p-4">
          <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Plan metadata</p>
          <label className="mt-4 block">
            <span className="mb-2 block text-sm font-medium text-zinc-300">Total area</span>
            <input
              type="number"
              placeholder="Enter total SQ FT"
              value={totalSqft}
              onChange={(e) => onTotalSqftChange(e.target.value)}
              className="w-full rounded-2xl border border-white/8 bg-zinc-950 px-4 py-3 text-sm text-zinc-200 placeholder-zinc-600 outline-none transition-colors focus:border-white/16"
            />
          </label>
          <p className="mt-3 text-xs leading-5 text-zinc-500">
            {totalSqft
              ? `Scale calibration will use ${totalSqft} sq ft for the full plan.`
              : 'Optional, but recommended when you want computed room square footage.'}
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-[22px] border border-white/6 bg-white/[0.02] px-4 py-3">
            <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Labels</p>
            <p className="mt-2 text-xl font-semibold tracking-tight text-zinc-100">{labelCount}</p>
          </div>
          <div className="rounded-[22px] border border-white/6 bg-white/[0.02] px-4 py-3">
            <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-600">Computed rooms</p>
            <p className="mt-2 text-xl font-semibold tracking-tight text-zinc-100">{computedRoomCount}</p>
          </div>
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
            Generate updates the preview, recomputes room labels and refreshes the downloadable DXF.
          </p>
        </div>
      </div>
    </div>
  )
}
