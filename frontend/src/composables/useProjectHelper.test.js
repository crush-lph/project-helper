import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useProjectHelper } from './useProjectHelper'

vi.mock('naive-ui', () => ({
  useDialog: () => ({ warning: vi.fn() }),
}))

class FakeEventSource {
  static instances = []

  constructor(url) {
    this.url = url
    this.closed = false
    this.listeners = {}
    FakeEventSource.instances.push(this)
  }

  addEventListener(event, callback) {
    this.listeners[event] = callback
  }

  close() {
    this.closed = true
  }

  emit(event, data = '{}') {
    this.listeners[event]?.({ data })
  }
}

function jsonResponse(data, ok = true) {
  return {
    ok,
    json: vi.fn().mockResolvedValue(data),
  }
}

function mountComposable() {
  let workspace
  mount({
    template: '<div />',
    setup() {
      workspace = useProjectHelper()
      return {}
    },
  })
  return workspace
}

describe('useProjectHelper', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    globalThis.EventSource = FakeEventSource
    globalThis.fetch = vi.fn(async (url, options = {}) => {
      const target = String(url)
      if (options.method === 'POST' && target.endsWith('/api/projects')) {
        return jsonResponse({ id: 'A', repo_url: 'repo-a', status: 'created' })
      }
      if (target.endsWith('/api/projects/A')) {
        return jsonResponse({ id: 'A', repo_url: 'repo-a', status: 'ready', report: 'Report A' })
      }
      if (target.endsWith('/api/projects/B/source/tree')) {
        return jsonResponse({ tree: [{ type: 'file', name: 'b.py', path: 'b.py', size: 3 }] })
      }
      if (target.endsWith('/api/projects/B')) {
        return jsonResponse({ id: 'B', repo_url: 'repo-b', status: 'ready', report: 'Report B' })
      }
      if (target.endsWith('/api/projects')) {
        return jsonResponse({ projects: [] })
      }
      throw new Error(`Unhandled fetch: ${target}`)
    })
  })

  it('ignores stale analysis events after the user switches projects', async () => {
    const workspace = mountComposable()

    await workspace.createAndAnalyze()
    const stream = FakeEventSource.instances[0]

    await workspace.loadProject({ id: 'B', repo_url: 'repo-b', status: 'ready' })
    stream.emit('done')

    expect(stream.closed).toBe(true)
    expect(workspace.activeProject.value.id).toBe('B')
    expect(workspace.activeProject.value.report).toBe('Report B')
    expect(globalThis.fetch).not.toHaveBeenCalledWith('http://127.0.0.1:8000/api/projects/A')
  })
})
