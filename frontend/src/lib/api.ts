/**
 * Base URL for the backend API.
 * In development, Vite proxy handles /api → localhost:8000.
 * In production, VITE_API_URL points to the Railway backend.
 */
function isLoopbackHost(hostname: string): boolean {
  return hostname === '127.0.0.1' || hostname === 'localhost' || hostname === '::1'
}

export function resolveApiBase(apiBase: string | undefined, isDev: boolean): string {
  const trimmed = apiBase?.trim() ?? ''
  if (!trimmed) return ''

  try {
    const url = new URL(trimmed)
    if (isDev && isLoopbackHost(url.hostname)) {
      return ''
    }
  } catch {
    // Fall back to the provided value when it is not a valid absolute URL.
  }

  return trimmed.replace(/\/+$/, '')
}

export const API_BASE: string = resolveApiBase(import.meta.env.VITE_API_URL, import.meta.env.DEV)

/** Prefix a backend path with the API base URL. */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`
}
