import { motion } from 'framer-motion'
import { AnimatePresence } from 'framer-motion'
import { CadWorkspaceCanvas } from './CadWorkspaceCanvas'
import { useCadWorkspace } from './useCadWorkspace'

function formatMeasure(value?: number | null) {
  if (value == null) return '—'
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}

function measurementWidth(result: { bbox: { width: number; height: number } | null; measurements?: { width: number; height: number; source: string } | null }) {
  return result.measurements?.width ?? result.bbox?.width ?? null
}

function measurementHeight(result: { bbox: { width: number; height: number } | null; measurements?: { width: number; height: number; source: string } | null }) {
  return result.measurements?.height ?? result.bbox?.height ?? null
}

function fitVerdict(result: { fit_summary?: { fits_within_buildable_bbox?: boolean | null } | null }) {
  const value = result.fit_summary?.fits_within_buildable_bbox
  if (value == null) return 'pending'
  return value ? 'fits' : 'overflow'
}

export function CadWorkspacePage() {
  const { file, status, statusMsg, result, canExtract, selectFile, extract } = useCadWorkspace()

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-[28px] border border-white/6 bg-zinc-950/80 shadow-[0_0_0_1px_rgba(255,255,255,0.02)]">
        <div className="grid gap-0 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="border-b border-white/6 p-6 lg:border-b-0 lg:border-r">
            <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">CAD intake</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-zinc-100">DWG / DXF side-by-side extractor</h2>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-zinc-400">
              Este workspace está separado del pipeline de imagen. Acá subís un CAD, extraemos el floor plan por un lado y el site plan por el otro, y los mostramos con la misma unidad interna.
            </p>

            <div className="mt-6 rounded-[24px] border border-dashed border-white/10 bg-white/[0.02] p-5">
              <label className="block">
                <span className="text-sm font-medium text-zinc-200">Archivo CAD</span>
                <input
                  aria-label="Archivo CAD"
                  type="file"
                  accept=".dxf,.dwg"
                  className="mt-3 block w-full rounded-2xl border border-white/8 bg-black/20 px-4 py-3 text-sm text-zinc-200 file:mr-4 file:rounded-xl file:border-0 file:bg-white/10 file:px-4 file:py-2 file:text-sm file:text-zinc-200 hover:file:bg-white/15"
                  onChange={(event) => selectFile(event.target.files?.[0] ?? null)}
                />
              </label>
              <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
                <button
                  type="button"
                  onClick={() => { void extract() }}
                  disabled={!canExtract || status === 'loading'}
                  className="rounded-2xl border border-white/10 bg-white/[0.06] px-5 py-3 text-sm font-medium text-zinc-200 transition-colors hover:bg-white/[0.1] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {status === 'loading' ? 'Extrayendo...' : 'Extraer floor + site'}
                </button>
                <p className="text-sm text-zinc-400">
                  {file ? `Archivo listo: ${file.name}` : 'Acepta DWG o DXF.'}
                </p>
              </div>
            </div>
          </div>

          <div className="p-6">
            <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Qué sale de esta fase</p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-[24px] border border-white/6 bg-white/[0.02] p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-zinc-600">Site plan</p>
                <p className="mt-2 text-sm leading-6 text-zinc-300">
                  Lote, buildable area y geometría relevante del implante.
                </p>
              </div>
              <div className="rounded-[24px] border border-white/6 bg-white/[0.02] p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-zinc-600">Floor plan</p>
                <p className="mt-2 text-sm leading-6 text-zinc-300">
                  Paredes, footprint y medidas base que importan para el encaje.
                </p>
              </div>
            </div>
            <div className="mt-4 rounded-[24px] border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-100">
              Por ahora este sistema <strong>solo extrae y normaliza</strong>. No rediseña, no ajusta y no toca la UI de imagen.
            </div>
          </div>
        </div>
      </section>

      <AnimatePresence>
        {statusMsg && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className={`rounded-2xl border px-4 py-3 text-sm ${
              status === 'error'
                ? 'border-red-500/20 bg-red-500/8 text-red-300'
                : 'border-white/6 bg-white/[0.02] text-zinc-300'
            }`}
          >
            {statusMsg}
          </motion.div>
        )}
      </AnimatePresence>

      {result && (
        <>
          <section className="grid gap-4 xl:grid-cols-[0.75fr_0.75fr_1.1fr]">
            <article className="rounded-[28px] border border-white/6 bg-zinc-950/80 p-5">
              <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Source</p>
              <h3 className="mt-2 text-lg font-semibold text-zinc-100">{result.source_name}</h3>
              <dl className="mt-4 space-y-3 text-sm text-zinc-300">
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Format</dt>
                  <dd className="font-medium text-zinc-100">{result.source_format.toUpperCase()}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Canonical unit</dt>
                  <dd className="font-medium text-zinc-100">{result.canonical_unit}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Conversion</dt>
                  <dd className="font-medium text-zinc-100">{result.conversion_status}</dd>
                </div>
              </dl>
            </article>

            <article className="rounded-[28px] border border-white/6 bg-zinc-950/80 p-5">
              <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Floor plan</p>
              <h3 className="mt-2 text-lg font-semibold text-zinc-100">Solo walls + medidas reales</h3>
              <dl className="mt-4 space-y-3 text-sm text-zinc-300">
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Width</dt>
                  <dd className="font-medium text-zinc-100">{formatMeasure(measurementWidth(result.floor_plan))}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Height</dt>
                  <dd className="font-medium text-zinc-100">{formatMeasure(measurementHeight(result.floor_plan))}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Measure source</dt>
                  <dd className="font-medium text-zinc-100">{result.floor_plan.measurements?.source ?? 'geometry'}</dd>
                </div>
              </dl>
            </article>

            <article className="rounded-[28px] border border-white/6 bg-zinc-950/80 p-5">
              <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Site plan</p>
              <h3 className="mt-2 text-lg font-semibold text-zinc-100">Lote y zona construible</h3>
              <dl className="mt-4 grid gap-3 text-sm text-zinc-300 sm:grid-cols-2">
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Width</dt>
                  <dd className="font-medium text-zinc-100">{formatMeasure(measurementWidth(result.site_plan))}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Height</dt>
                  <dd className="font-medium text-zinc-100">{formatMeasure(measurementHeight(result.site_plan))}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Measure source</dt>
                  <dd className="font-medium text-zinc-100">{result.site_plan.measurements?.source ?? 'geometry'}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Gap</dt>
                  <dd className="font-medium text-zinc-100">{formatMeasure(result.side_by_side.gap)}</dd>
                </div>
              </dl>
            </article>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <article className="rounded-[28px] border border-white/6 bg-zinc-950/80 p-5">
              <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Buildable comparison</p>
              <h3 className="mt-2 text-lg font-semibold text-zinc-100">Footprint exterior vs zona construible</h3>
              <dl className="mt-4 grid gap-3 text-sm text-zinc-300 sm:grid-cols-2">
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Buildable width</dt>
                  <dd className="font-medium text-zinc-100">{formatMeasure(result.fit_summary?.buildable_bbox?.width)}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Buildable height</dt>
                  <dd className="font-medium text-zinc-100">{formatMeasure(result.fit_summary?.buildable_bbox?.height)}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Width delta</dt>
                  <dd className="font-medium text-zinc-100">{formatMeasure(result.fit_summary?.width_delta)}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Height delta</dt>
                  <dd className="font-medium text-zinc-100">{formatMeasure(result.fit_summary?.height_delta)}</dd>
                </div>
              </dl>
            </article>

            <article className="rounded-[28px] border border-white/6 bg-zinc-950/80 p-5">
              <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Fit verdict</p>
              <h3 className="mt-2 text-lg font-semibold text-zinc-100">
                {fitVerdict(result) === 'fits'
                  ? 'El footprint entra por bbox en el buildable'
                  : fitVerdict(result) === 'overflow'
                    ? 'El footprint excede el buildable por bbox'
                    : 'Todavía no hay buildable envelope suficiente'}
              </h3>
              <p className="mt-3 text-sm leading-6 text-zinc-400">
                Este chequeo todavía es <span className="font-medium text-zinc-200">bbox vs bbox</span>. Sirve para saber si sobra o falta en ancho/alto antes de pasar al ajuste inteligente o al fit poligonal real.
              </p>
            </article>
          </section>

          <CadWorkspaceCanvas result={result} />

          {result.warnings.length > 0 && (
            <section className="rounded-[28px] border border-amber-500/20 bg-amber-500/10 p-5">
              <p className="text-[11px] uppercase tracking-[0.24em] text-amber-200/70">Warnings</p>
              <ul className="mt-3 space-y-2 text-sm text-amber-50">
                {result.warnings.map((warning) => (
                  <li key={warning}>• {warning}</li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  )
}
