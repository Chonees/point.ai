/**
 * Architectural format helpers — mirrors backend/measurement/calibration.py's
 * `inches_to_feet_inches` and `_fmt_inches` (same rounding rules).
 *
 * Example: 98 → 8'-2"
 */

/** Format a length in inches as feet-inches (e.g. 98 → "8'-2\""). */
export function inchesToFeetInches(inches: number): string {
  const feet = Math.floor(inches / 12)
  let remaining = Math.round(inches - feet * 12)
  let outFeet = feet
  if (remaining === 12) {
    outFeet += 1
    remaining = 0
  }
  return `${outFeet}'-${remaining}"`
}

/** Format pixels → architectural given inches-per-pixel. */
export function pixelsToArchitectural(pixels: number, scaleIpp: number): string {
  if (!scaleIpp || scaleIpp <= 0) return `${Math.round(pixels)} px`
  return inchesToFeetInches(pixels * scaleIpp)
}

/**
 * Parse an architectural length back into inches. Accepts multiple formats:
 *   8'-4"     → 100
 *   8'4"      → 100
 *   8' 4"     → 100
 *   8'        → 96
 *   100"      → 100
 *   100       → 100  (bare number treated as inches)
 *   8.5'      → 102
 *
 * Returns null when the string can't be parsed — callers should treat that
 * as "don't recalibrate".
 */
export function parseArchitectural(text: string): number | null {
  if (!text) return null
  const trimmed = text.trim()
  if (!trimmed) return null

  // Normalize — drop quotes/dashes, keep digits and punctuation that matter.
  // Supported separators between feet and inches: "-", " ", "", and nothing.
  const feetInchesRe = /^([+-]?\d*\.?\d+)\s*'(?:\s*-\s*|\s+)?(\d*\.?\d+)?\s*"?$/
  const m = trimmed.match(feetInchesRe)
  if (m) {
    const feet = parseFloat(m[1])
    const inches = m[2] ? parseFloat(m[2]) : 0
    if (Number.isFinite(feet) && Number.isFinite(inches)) {
      return feet * 12 + inches
    }
  }

  // Inches-only with the inch symbol: 100"
  const inchesRe = /^([+-]?\d*\.?\d+)\s*"$/
  const mi = trimmed.match(inchesRe)
  if (mi) {
    const inches = parseFloat(mi[1])
    return Number.isFinite(inches) ? inches : null
  }

  // Bare number → inches
  const bare = parseFloat(trimmed)
  if (Number.isFinite(bare) && /^\d*\.?\d+$/.test(trimmed)) return bare

  return null
}
