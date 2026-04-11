/**
 * Base URL for the backend API.
 * In development, Vite proxy handles /api → localhost:8000.
 * In production, VITE_API_URL points to the Railway backend.
 */
export const API_BASE: string = import.meta.env.VITE_API_URL || ''

/** Prefix a backend path with the API base URL. */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`
}
