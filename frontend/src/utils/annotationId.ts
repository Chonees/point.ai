/**
 * Generate a stable identifier for a new annotation created in the 2D editor.
 * Falls back to a pseudo-random prefix if crypto.randomUUID isn't available
 * (old browsers, test environment).
 */
export function newAnnotationId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `ann-${Math.random().toString(36).slice(2, 10)}-${Date.now().toString(36)}`
}
