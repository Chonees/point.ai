import type {
  CadReviewArtifactData,
  CadReviewExportState,
  CadWorkspaceExtractResult,
} from './contracts'

export function buildCadReviewArtifactData(result: CadWorkspaceExtractResult): CadReviewArtifactData {
  return {
    analysisId: result.analysis_id,
    sourceName: result.source_name,
    canonicalUnit: result.canonical_unit,
    floorPlan: result.floor_plan,
    sitePlan: result.site_plan,
    fitSummary: result.fit_summary ?? null,
    warnings: result.warnings,
    export: buildCadReviewExportState(result),
  }
}

export function buildCadReviewExportState(result: CadWorkspaceExtractResult): CadReviewExportState {
  const fit = result.fit_summary
  const footprintBBox = fit?.footprint_bbox ?? result.floor_plan.bbox ?? null
  const buildableBBox = fit?.buildable_bbox ?? null

  if (!footprintBBox || !buildableBBox) {
    return {
      ready: false,
      reason: 'Falta footprint del floor plan o area construible para exportar el overlay.',
    }
  }

  return {
    ready: true,
    href: `/api/cad-workspace/export-overlay/${result.analysis_id}`,
  }
}
