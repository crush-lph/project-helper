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

function deferred() {
  let resolve
  const promise = new Promise((done) => {
    resolve = done
  })
  return { promise, resolve }
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

  it('ignores source tree responses after the active project changes', async () => {
    const treeResponse = deferred()
    globalThis.fetch = vi.fn(async (url) => {
      const target = String(url)
      if (target.endsWith('/api/projects/A/source/tree')) {
        return treeResponse.promise
      }
      if (target.endsWith('/api/projects')) {
        return jsonResponse({ projects: [] })
      }
      throw new Error(`Unhandled fetch: ${target}`)
    })
    const workspace = mountComposable()
    workspace.activeProject.value = { id: 'A', repo_url: 'repo-a', status: 'ready' }

    const loading = workspace.fetchSourceTree('A')
    workspace.activeProject.value = { id: 'B', repo_url: 'repo-b', status: 'ready' }
    treeResponse.resolve(jsonResponse({ tree: [{ type: 'file', name: 'a.py', path: 'a.py', size: 1 }] }))
    await loading

    expect(workspace.sourceTree.value).toEqual([])
  })

  it('ignores source file responses after the active project changes', async () => {
    const fileResponse = deferred()
    globalThis.fetch = vi.fn(async (url) => {
      const target = String(url)
      if (target.endsWith('/api/projects/A/source/file?path=a.py')) {
        return fileResponse.promise
      }
      if (target.endsWith('/api/projects')) {
        return jsonResponse({ projects: [] })
      }
      throw new Error(`Unhandled fetch: ${target}`)
    })
    const workspace = mountComposable()
    workspace.activeProject.value = { id: 'A', repo_url: 'repo-a', status: 'ready' }

    const loading = workspace.loadSourceFile('a.py')
    workspace.activeProject.value = { id: 'B', repo_url: 'repo-b', status: 'ready' }
    fileResponse.resolve(jsonResponse({ path: 'a.py', content: 'from A', size: 6, truncated: false }))
    await loading

    expect(workspace.sourceFile.value).toBeNull()
  })
})
