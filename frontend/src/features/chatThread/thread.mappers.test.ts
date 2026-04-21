import { describe, expect, it } from 'vitest'
import { DEFAULT_VISIBILITY } from '../../types'
import type { PlanData } from '../projects'
import { planToInitialMessages, planToThreadSummary } from './thread.mappers'

function buildPlan(overrides: Partial<PlanData> = {}): PlanData {
  return {
    id: 'plan-1',
    projectId: 'project-1',
    name: 'Fit Dawson',
    imageData: null,
    structure: { rooms: [] },
    scene: {
      annotations2d: [],
      placedItems3d: [],
      floorMaterial: 'hardwood',
      wallMaterial: 'white-paint',
      visibility: DEFAULT_VISIBILITY,
    },
    totalSqft: 2100,
    createdAt: '2026-04-20T10:00:00.000Z',
    updatedAt: '2026-04-20T11:00:00.000Z',
    ...overrides,
  }
}

describe('thread.mappers', () => {
  it('maps a plan into a thread summary with last activity', () => {
    const summary = planToThreadSummary(buildPlan())

    expect(summary.id).toBe('plan-1')
    expect(summary.title).toBe('Fit Dawson')
    expect(summary.lastActivityIso).toBe('2026-04-20T11:00:00.000Z')
  })

  it('creates a starter system transcript from persisted plan data', () => {
    const messages = planToInitialMessages(buildPlan({ imageData: 'data:image/png;base64,abc' }))

    expect(messages[0].role).toBe('system')
    expect(messages[1].role).toBe('assistant')
    expect(messages[1].artifacts[0].kind).toBe('image-source')
  })
})
