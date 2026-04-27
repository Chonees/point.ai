import { describe, expect, it } from 'vitest'

import { resolveApiBase } from './api'

describe('resolveApiBase', () => {
  it('ignores loopback overrides in dev so Vite proxy handles the API', () => {
    expect(resolveApiBase('http://127.0.0.1:8001', true)).toBe('')
    expect(resolveApiBase('http://localhost:8000', true)).toBe('')
  })

  it('keeps non-loopback URLs and trims whitespace', () => {
    expect(resolveApiBase(' https://pointai-production.up.railway.app\n', false)).toBe(
      'https://pointai-production.up.railway.app',
    )
  })
})
