import type {
  CadReviewArtifactData,
  CadReviewExportState,
  CadWorkspaceBBox,
  CadWorkspaceEntity,
  CadWorkspaceExtractResult,
  CadWorkspaceFitSummary,
  CadWorkspacePoint,
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

export function resolveOverlayBBox(review: CadReviewArtifactData): CadWorkspaceBBox | null {
  const fit = review.fitSummary
  const floorBBox = fit?.footprint_bbox ?? review.floorPlan.bbox ?? null
  const buildableBBox = fit?.buildable_bbox ?? null
  if (!floorBBox || !buildableBBox) return null

  const x1 = buildableBBox.x1 + ((buildableBBox.width - floorBBox.width) / 2)
  const y1 = buildableBBox.y1 + ((buildableBBox.height - floorBBox.height) / 2)

  return {
    x1,
    y1,
    x2: x1 + floorBBox.width,
    y2: y1 + floorBBox.height,
    width: floorBBox.width,
    height: floorBBox.height,
  }
}

export function translateEntityPoints(entity: CadWorkspaceEntity, dx: number, dy: number): CadWorkspacePoint[] {
  if (entity.type.toLowerCase() === 'line' && entity.start && entity.end) {
    return [
      { x: entity.start.x + dx, y: entity.start.y + dy },
      { x: entity.end.x + dx, y: entity.end.y + dy },
    ]
  }

  return (entity.points ?? []).map((point) => ({
    x: point.x + dx,
    y: point.y + dy,
  }))
}

export function computeOverlayScene(review: CadReviewArtifactData) {
  const overlayBBox = resolveOverlayBBox(review)
  const floorBBox = review.fitSummary?.footprint_bbox ?? review.floorPlan.bbox ?? null
  const buildableBBox = review.fitSummary?.buildable_bbox ?? null
  const dx = overlayBBox && floorBBox ? overlayBBox.x1 - floorBBox.x1 : 0
  const dy = overlayBBox && floorBBox ? overlayBBox.y1 - floorBBox.y1 : 0

  const sitePolylines = review.sitePlan.entities
    .map((entity) => translateEntityPoints(entity, 0, 0))
    .filter((points) => points.length >= 2)

  const floorPolylines = review.floorPlan.entities
    .map((entity) => translateEntityPoints(entity, dx, dy))
    .filter((points) => points.length >= 2)

  const buildablePolygon = review.fitSummary?.buildable_polygon ?? []
  const allPoints = [
    ...sitePolylines.flat(),
    ...floorPolylines.flat(),
    ...buildablePolygon,
    ...(overlayBBox ? bboxToPoints(overlayBBox) : []),
    ...(buildableBBox ? bboxToPoints(buildableBBox) : []),
  ]

  if (allPoints.length === 0) {
    return {
      overlayBBox,
      buildableBBox,
      buildablePolygon,
      floorPolylines,
      sitePolylines,
      viewBox: '0 0 100 100',
    }
  }

  const minX = Math.min(...allPoints.map((point) => point.x))
  const minY = Math.min(...allPoints.map((point) => point.y))
  const maxX = Math.max(...allPoints.map((point) => point.x))
  const maxY = Math.max(...allPoints.map((point) => point.y))
  const padding = Math.max((maxX - minX) * 0.08, (maxY - minY) * 0.08, 24)

  return {
    overlayBBox,
    buildableBBox,
    buildablePolygon,
    floorPolylines,
    sitePolylines,
    viewBox: `${minX - padding} ${minY - padding} ${(maxX - minX) + (padding * 2)} ${(maxY - minY) + (padding * 2)}`,
  }
}

export function formatArchitecturalMeasure(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return 'N/D'
  return `${formatFeetInches(value)} · ${formatInches(value)} in`
}

export function getFitVerdictText(fit: CadWorkspaceFitSummary | null): string {
  if (!fit) return 'Review sin veredicto'
  if (fit.basis === 'buildable_polygon') {
    return fit.fits_within_buildable_polygon ? 'Entra en poligono construible' : 'No entra en poligono construible'
  }
  if (fit.fits_within_buildable_bbox === true) return 'Entra por bbox'
  if (fit.fits_within_buildable_bbox === false) return 'No entra por bbox'
  return 'Review sin veredicto'
}

function bboxToPoints(bbox: CadWorkspaceBBox): CadWorkspacePoint[] {
  return [
    { x: bbox.x1, y: bbox.y1 },
    { x: bbox.x2, y: bbox.y1 },
    { x: bbox.x2, y: bbox.y2 },
    { x: bbox.x1, y: bbox.y2 },
  ]
}

function formatInches(value: number): string {
  const rounded = Math.round(value * 100) / 100
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(2)
}

function formatFeetInches(value: number): string {
  const absolute = Math.abs(value)
  const feet = Math.floor(absolute / 12)
  const remainder = absolute - (feet * 12)
  const wholeInches = Math.floor(remainder)
  const fraction = remainder - wholeInches
  const eighths = Math.round(fraction * 8)

  const normalizedWholeInches = eighths === 8 ? wholeInches + 1 : wholeInches
  const normalizedEighths = eighths === 8 ? 0 : eighths
  const normalizedFeet = normalizedWholeInches === 12 ? feet + 1 : feet
  const inches = normalizedWholeInches === 12 ? 0 : normalizedWholeInches

  const fractions: Record<number, string> = {
    1: '1/8',
    2: '1/4',
    3: '3/8',
    4: '1/2',
    5: '5/8',
    6: '3/4',
    7: '7/8',
  }
  const fractionLabel = fractions[normalizedEighths]
  if (fractionLabel) return `${normalizedFeet}'-${inches} ${fractionLabel}"`
  return `${normalizedFeet}'-${inches}"`
}
