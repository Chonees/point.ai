import { describe, expect, it } from 'vitest'
import { DEFAULT_VISIBILITY } from '../../types'
import type { ThreadData } from '../threads'
import { threadToInitialMessages, threadToThreadSummary } from '../threads'

function buildThread(overrides: Partial<ThreadData> = {}): ThreadData {
  return {
    id: 'thread-1',
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
  it('maps a thread record into a thread summary with last activity', () => {
    const summary = threadToThreadSummary(buildThread())

    expect(summary.id).toBe('thread-1')
    expect(summary.title).toBe('Fit Dawson')
    expect(summary.lastActivityIso).toBe('2026-04-20T11:00:00.000Z')
  })

  it('creates a starter system transcript from persisted thread data', () => {
    const messages = threadToInitialMessages(buildThread({ imageData: 'data:image/png;base64,abc' }))

    expect(messages[0].role).toBe('system')
    expect(messages[1].role).toBe('assistant')
    expect(messages[1].artifacts[0].kind).toBe('image-source')
    expect(messages[1].artifacts[1].kind).toBe('preview')
  })
})
