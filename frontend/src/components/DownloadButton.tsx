import { memo, useState } from 'react'
import { DownloadIcon } from './DownloadIcon'

export const DownloadButton = memo(function DownloadButton({ href }: { href: string }) {
  const [name, setName] = useState('')

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="File name..."
          className="flex-1 px-3 py-2 sm:py-1.5 bg-white/[0.04] border border-zinc-800/60 rounded-md
                     text-sm text-zinc-300 placeholder:text-zinc-600 outline-none
                     focus:border-zinc-700 transition-colors"
        />
        <a href={href} download={name.trim() ? `${name.trim()}.dxf` : 'floorplan.dxf'}
          className="inline-flex items-center justify-center gap-2
                     px-4 py-2.5 sm:py-2
                     bg-white/[0.04] border border-zinc-800/60 rounded-md
                     text-sm text-zinc-400
                     hover:bg-white/[0.08] hover:text-zinc-300
                     active:bg-white/[0.12]
                     transition-colors duration-200">
          <DownloadIcon />
          .dxf
        </a>
      </div>
    </div>
  )
})
