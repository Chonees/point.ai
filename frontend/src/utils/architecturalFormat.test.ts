import { describe, it, expect } from 'vitest'
import { inchesToFeetInches, parseArchitectural } from './architecturalFormat'

describe('inchesToFeetInches', () => {
  it('formats whole feet', () => {
    expect(inchesToFeetInches(120)).toBe('10\'-0"')
  })

  it('formats feet + inches', () => {
    expect(inchesToFeetInches(98)).toBe('8\'-2"')
  })

  it('rounds inches, rolling over at 12', () => {
    expect(inchesToFeetInches(95.6)).toBe('8\'-0"') // 95.6 → 7'11.6" → rounds 11.6→12 → 8'0"
  })

  it('handles zero', () => {
    expect(inchesToFeetInches(0)).toBe('0\'-0"')
  })
})

describe('parseArchitectural', () => {
  it('parses feet-inches with dash', () => {
    expect(parseArchitectural("10'-0\"")).toBe(120)
    expect(parseArchitectural("8'-4\"")).toBe(100)
  })

  it('parses feet-inches without dash', () => {
    expect(parseArchitectural("8'4\"")).toBe(100)
    expect(parseArchitectural("8' 4\"")).toBe(100)
  })

  it('parses feet only', () => {
    expect(parseArchitectural("8'")).toBe(96)
  })

  it('parses inches only with symbol', () => {
    expect(parseArchitectural('100"')).toBe(100)
  })

  it('parses bare number as inches', () => {
    expect(parseArchitectural('100')).toBe(100)
    expect(parseArchitectural('100.5')).toBe(100.5)
  })

  it('parses decimal feet', () => {
    expect(parseArchitectural("8.5'")).toBe(102)
  })

  it('returns null for unparseable input', () => {
    expect(parseArchitectural('')).toBeNull()
    expect(parseArchitectural('hello')).toBeNull()
    expect(parseArchitectural('LIVING 10ft')).toBeNull()
  })

  it('roundtrips through inchesToFeetInches', () => {
    const v = 142
    const text = inchesToFeetInches(v)
    expect(parseArchitectural(text)).toBe(v)
  })
})
