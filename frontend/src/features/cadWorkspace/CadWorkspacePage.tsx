import { AnimatePresence, motion } from 'framer-motion'
import { CadWorkspaceCanvas } from './CadWorkspaceCanvas'
import { useCadWorkspace } from './useCadWorkspace'

function formatMeasure(value?: number | null) {
  if (value == null) return '—'
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}

function formatFeetInches(value?: number | null) {
  if (value == null) return '—'
  const sign = value < 0 ? '-' : ''
  const absolute = Math.abs(value)
  let feet = Math.floor(absolute / 12)
  let remainder = absolute - (feet * 12)
  let wholeInches = Math.floor(remainder)
  let fraction = remainder - wholeInches
  let eighths = Math.round(fraction * 8)

  if (eighths === 8) {
    wholeInches += 1
    eighths = 0
  }
  if (wholeInches === 12) {
    feet += 1
    wholeInches = 0
  }

  const fractionMap: Record<number, string> = {
    1: '1/8',
    2: '1/4',
    3: '3/8',
    4: '1/2',
    5: '5/8',
    6: '3/4',
    7: '7/8',
  }
  const fractionText = fractionMap[eighths]
  if (fractionText) {
    return `${sign}${feet}'-${wholeInches} ${fractionText}"`
  }
  return `${sign}${feet}'-${wholeInches}"`
}

function formatArchitecturalMeasure(value?: number | null) {
  if (value == null) return '—'
  return `${formatFeetInches(value)} · ${formatMeasure(value)} in`
}

function measurementWidth(result: { bbox: { width: number; height: number } | null; measurements?: { width: number; height: number; source: string } | null }) {
  return result.measurements?.width ?? result.bbox?.width ?? null
}

function measurementHeight(result: { bbox: { width: number; height: number } | null; measurements?: { width: number; height: number; source: string } | null }) {
  return result.measurements?.height ?? result.bbox?.height ?? null
}

function fitVerdict(result: { fit_summary?: { fits_within_buildable_bbox?: boolean | null; fits_within_buildable_polygon?: boolean | null } | null }) {
  const value = result.fit_summary?.fits_within_buildable_polygon ?? result.fit_summary?.fits_within_buildable_bbox
  if (value == null) return 'pending'
  return value ? 'fits' : 'overflow'
}

function deltaCopy(value: number | null | undefined, axisLabel: string) {
  if (value == null) return `Sin delta de ${axisLabel}`
  if (Math.abs(value) < 0.001) return `Calza justo en ${axisLabel}`
  if (value > 0) return `Sobra ${formatFeetInches(value)} de ${axisLabel}`
  return `Falta ${formatFeetInches(Math.abs(value))} de ${axisLabel}`
}

export function CadWorkspacePage() {
  const { file, status, statusMsg, result, canExtract, selectFile, extract } = useCadWorkspace()
  const verdict = result ? fitVerdict(result) : 'pending'
  const overlayDownloadUrl = result ? `/api/cad-workspace/export-overlay/${result.analysis_id}` : null

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-[28px] border border-white/6 bg-zinc-950/80 shadow-[0_0_0_1px_rgba(255,255,255,0.02)]">
        <div className="grid gap-0 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="border-b border-white/6 p-6 lg:border-b-0 lg:border-r">
            <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">CAD intake</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-zinc-100">DWG / DXF overlay extractor</h2>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-zinc-400">
              Este workspace está separado del pipeline de imagen. Acá subís un CAD, extraemos el floor plan por un lado y el site plan por el otro, normalizamos la unidad y te mostramos el footprint del plano sobre el área construible.
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
                  Solo walls, footprint y medidas base que importan para el encaje.
                </p>
              </div>
            </div>
            <div className="mt-4 rounded-[24px] border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-100">
              Por ahora este sistema <strong>solo extrae, superpone y normaliza</strong>. No rediseña ni ajusta ambientes.
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
          <section className="grid gap-4 xl:grid-cols-[0.7fr_0.9fr_0.9fr]">
            <article className="rounded-[28px] border border-white/6 bg-zinc-950/80 p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Source</p>
                  <h3 className="mt-2 text-lg font-semibold text-zinc-100">{result.source_name}</h3>
                </div>
                {overlayDownloadUrl && (
                  <a
                    href={overlayDownloadUrl}
                    className="inline-flex rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-2 text-sm font-medium text-zinc-100 transition-colors hover:bg-white/[0.1]"
                  >
                    Descargar DXF overlay
                  </a>
                )}
              </div>
              <dl className="mt-4 space-y-3 text-sm text-zinc-300">
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Format</dt>
                  <dd className="font-medium text-zinc-100">{result.source_format.toUpperCase()}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Unidad común</dt>
                  <dd className="font-medium text-zinc-100">
                    {result.canonical_unit} <span className="text-zinc-500">(1'-0" = 12 in)</span>
                  </dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Conversion</dt>
                  <dd className="font-medium text-zinc-100">{result.conversion_status}</dd>
                </div>
              </dl>
            </article>

            <article className="rounded-[28px] border border-white/6 bg-zinc-950/80 p-5">
              <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Footprint del plano</p>
              <h3 className="mt-2 text-lg font-semibold text-zinc-100">Solo walls + medidas reales</h3>
              <dl className="mt-4 space-y-3 text-sm text-zinc-300">
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Width</dt>
                  <dd className="font-medium text-zinc-100">{formatArchitecturalMeasure(measurementWidth(result.floor_plan))}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Height</dt>
                  <dd className="font-medium text-zinc-100">{formatArchitecturalMeasure(measurementHeight(result.floor_plan))}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Measure source</dt>
                  <dd className="font-medium text-zinc-100">{result.floor_plan.measurements?.source ?? 'geometry'}</dd>
                </div>
              </dl>
            </article>

            <article className="rounded-[28px] border border-white/6 bg-zinc-950/80 p-5">
              <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Área construible</p>
              <h3 className="mt-2 text-lg font-semibold text-zinc-100">La medida útil para saber si entra</h3>
              <dl className="mt-4 space-y-3 text-sm text-zinc-300">
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Width</dt>
                  <dd className="font-medium text-zinc-100">{formatArchitecturalMeasure(result.fit_summary?.buildable_bbox?.width)}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Height</dt>
                  <dd className="font-medium text-zinc-100">{formatArchitecturalMeasure(result.fit_summary?.buildable_bbox?.height)}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Measure source</dt>
                  <dd className="font-medium text-zinc-100">{result.fit_summary?.buildable_bbox ? 'buildable_bbox' : (result.site_plan.measurements?.source ?? 'geometry')}</dd>
                </div>
              </dl>
            </article>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <article className="rounded-[28px] border border-white/6 bg-zinc-950/80 p-5">
              <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Resultado de encaje</p>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-medium uppercase tracking-[0.18em] ${
                  verdict === 'fits'
                    ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
                    : verdict === 'overflow'
                      ? 'border-red-400/30 bg-red-400/10 text-red-200'
                      : 'border-amber-400/30 bg-amber-400/10 text-amber-100'
                }`}>
                  {verdict === 'fits' ? 'Sí entra en polígono construible' : verdict === 'overflow' ? 'No entra en polígono construible' : 'Sin polígono construible claro'}
                </span>
                <span className="text-sm text-zinc-500">base: {result.fit_summary?.basis ?? 'unavailable'}</span>
              </div>
              <dl className="mt-4 space-y-3 text-sm text-zinc-300">
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Ancho</dt>
                  <dd className="font-medium text-zinc-100">{deltaCopy(result.fit_summary?.width_delta, 'ancho')}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-zinc-500">Alto</dt>
                  <dd className="font-medium text-zinc-100">{deltaCopy(result.fit_summary?.height_delta, 'alto')}</dd>
                </div>
              </dl>
            </article>

            <article className="rounded-[28px] border border-white/6 bg-zinc-950/80 p-5">
              <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Cómo leer esto</p>
              <h3 className="mt-2 text-lg font-semibold text-zinc-100">Overlay primero, ajuste después</h3>
              <p className="mt-3 text-sm leading-6 text-zinc-400">
                Point.ai compara el <span className="font-medium text-zinc-200">footprint exterior del plano</span> contra el <span className="font-medium text-zinc-200">polígono construible real</span> en la misma unidad común y los superpone para que se vea rápido dónde sobra o falta.
              </p>
              <p className="mt-3 text-sm leading-6 text-zinc-400">
                Si existe polígono construible, el veredicto ya no sale del rectángulo envolvente sino de chequeo geométrico contra esa forma. El delta ancho/alto sigue siendo una ayuda secundaria.
              </p>
              <p className="mt-3 text-sm leading-6 text-zinc-500">
                El botón de descarga baja un DXF con el site y el floor overlay ya puestos en la misma unidad interna para seguir revisándolo en CAD.
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
