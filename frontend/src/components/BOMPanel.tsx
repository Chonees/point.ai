import { memo, useState } from 'react'
import type { BOMData } from '../types'

export const BOMPanel = memo(function BOMPanel({ bom, structure }: { bom: BOMData; structure: Record<string, unknown> }) {
  const [expanded, setExpanded] = useState(false)
  const s = bom.summary

  const downloadCSV = async () => {
    const res = await fetch('/api/v2/bom-csv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ structure }),
    })
    if (!res.ok) return
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'bom.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="bg-zinc-900/50 border border-zinc-800/40 rounded-lg overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2.5 flex items-center justify-between">
        <span className="text-[11px] font-medium text-zinc-400 tracking-wide">Bill of Materials</span>
        <button
          onClick={downloadCSV}
          className="text-[9px] px-2 py-0.5 rounded bg-zinc-800/60 border border-zinc-700/40
                     text-zinc-500 hover:text-zinc-300 hover:bg-zinc-700/60 cursor-pointer transition-colors"
        >
          CSV
        </button>
      </div>

      {/* Summary grid */}
      <div className="grid grid-cols-4 gap-px bg-zinc-800/30 border-t border-zinc-800/40">
        <SumCell label="Walls" value={`${s.total_wall_length_ft} ft`} />
        <SumCell label="Area" value={`${s.total_wall_area_sqft} ft²`} />
        <SumCell label="Doors" value={String(s.total_doors)} />
        <SumCell label="Windows" value={String(s.total_windows)} />
      </div>

      {/* Expandable material breakdown */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-3 py-1.5 text-[9px] text-zinc-600 hover:text-zinc-400
                   border-t border-zinc-800/40 cursor-pointer transition-colors text-left"
      >
        {expanded ? '▾' : '▸'} Material breakdown
      </button>

      {expanded && (
        <div className="px-3 pb-2.5 space-y-1">
          {bom.materials.map((m, i) => (
            <div key={i} className="flex justify-between text-[10px]">
              <span className="text-zinc-500">{m.item}</span>
              <span className="text-zinc-400 font-mono">{m.qty} {m.unit}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
})

function SumCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-zinc-900/80 px-2.5 py-2 text-center">
      <p className="text-[11px] font-light text-zinc-300">{value}</p>
      <p className="text-[8px] text-zinc-600 mt-0.5">{label}</p>
    </div>
  )
}
