import { useRef } from 'react'
import { UploadIcon } from '../../components/UploadIcon'

interface PlanSourceCardProps {
  planName?: string
  preview: string | null
  dragging: boolean
  onDragOver: (e: React.DragEvent) => void
  onDragLeave: () => void
  onDrop: (e: React.DragEvent) => void
  onFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void
}

export function PlanSourceCard({
  planName,
  preview,
  dragging,
  onDragOver,
  onDragLeave,
  onDrop,
  onFileChange,
}: PlanSourceCardProps) {
  const fileRef = useRef<HTMLInputElement>(null)
  const hasPlan = Boolean(preview)

  return (
    <div className="border-b border-white/6 p-5 sm:p-6 lg:border-b-0 lg:border-r">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.28em] text-zinc-600">Plan source</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-100">
            {planName ?? 'New floor plan'}
          </h2>
        </div>
        <span className="rounded-full border border-white/8 px-3 py-1 text-[10px] uppercase tracking-[0.22em] text-zinc-500">
          {hasPlan ? 'Loaded' : 'Awaiting upload'}
        </span>
      </div>

      <div
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onClick={() => fileRef.current?.click()}
        className={`relative cursor-pointer overflow-hidden rounded-[24px] border transition-all duration-200 ${
          dragging
            ? 'border-white/18 bg-white/[0.05]'
            : 'border-white/6 bg-[#0b0b0b] hover:border-white/12 hover:bg-white/[0.03]'
        }`}
        style={{ minHeight: preview ? 'auto' : '320px' }}
      >
        <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={onFileChange} />

        {preview ? (
          <div className="relative">
            <img src={preview} alt="floor plan" className="max-h-[460px] w-full object-contain" />
            <div className="absolute inset-0 bg-gradient-to-t from-black/55 via-transparent to-transparent opacity-0 transition-opacity hover:opacity-100">
              <div className="absolute bottom-4 left-4 rounded-full border border-white/12 bg-black/35 px-3 py-1.5 text-xs text-zinc-200">
                Click to replace image
              </div>
            </div>
          </div>
        ) : (
          <div className="flex h-[320px] flex-col items-center justify-center px-6 text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-white/8 bg-white/[0.04]">
              <UploadIcon size={22} className="text-zinc-500" />
            </div>
            <p className="text-base font-medium text-zinc-200">Drop a floor plan image</p>
            <p className="mt-2 max-w-sm text-sm leading-6 text-zinc-500">
              Start with PNG or JPG. Once it is loaded, you can generate the DXF and review the resulting preview.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
