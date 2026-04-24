import { useEffect, useState } from 'react'

import type { CatalogInspectorTopology } from './types'

type InspectorState =
  | { status: 'loading' }
  | {
    status: 'ready'
    topology: CatalogInspectorTopology
    CatalogInspectorPage: typeof import('./CatalogInspectorPage').CatalogInspectorPage
  }

export function SeminoleTopologyInspectorEntry() {
  const [state, setState] = useState<InspectorState>({ status: 'loading' })

  useEffect(() => {
    let cancelled = false

    void Promise.all([
      import('./catalogInspector.fixture.json'),
      import('./CatalogInspectorPage'),
    ]).then(([fixtureModule, pageModule]) => {
      if (cancelled) return

      setState({
        status: 'ready',
        topology: fixtureModule.default as CatalogInspectorTopology,
        CatalogInspectorPage: pageModule.CatalogInspectorPage,
      })
    })

    return () => {
      cancelled = true
    }
  }, [])

  if (state.status === 'loading') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-700 border-t-zinc-400" />
      </div>
    )
  }

  const { CatalogInspectorPage, topology } = state
  return <CatalogInspectorPage topology={topology} />
}
