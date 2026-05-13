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

  it('loads annotations for the active source file and ignores stale annotation responses', async () => {
    const annotationResponse = deferred()
    globalThis.fetch = vi.fn(async (url) => {
      const target = String(url)
      if (target.endsWith('/api/projects/A/source/annotations?path=a.py')) {
        return annotationResponse.promise
      }
      if (target.endsWith('/api/projects')) {
        return jsonResponse({ projects: [] })
      }
      throw new Error(`Unhandled fetch: ${target}`)
    })
    const workspace = mountComposable()
    workspace.activeProject.value = { id: 'A', repo_url: 'repo-a', status: 'ready' }
    workspace.sourceFile.value = { path: 'a.py', content: 'from A', size: 6, truncated: false }

    const loading = workspace.fetchSourceAnnotations('a.py', 'A')
    workspace.sourceFile.value = { path: 'b.py', content: 'from B', size: 6, truncated: false }
    annotationResponse.resolve(jsonResponse({ annotations: [{ id: 'note-1', path: 'a.py', line: 1, body: 'stale' }] }))
    await loading

    expect(workspace.sourceAnnotations.value).toEqual([])
  })

  it('creates, updates, and deletes source annotations in state', async () => {
    globalThis.fetch = vi.fn(async (url, options = {}) => {
      const target = String(url)
      if (options.method === 'POST' && target.endsWith('/api/projects/A/source/annotations')) {
        return jsonResponse({ id: 'note-1', project_id: 'A', path: 'a.py', line: 1, body: 'first', created_at: '1' })
      }
      if (options.method === 'PATCH' && target.endsWith('/api/projects/A/source/annotations/note-1')) {
        return jsonResponse({ id: 'note-1', project_id: 'A', path: 'a.py', line: 1, body: 'updated', created_at: '1' })
      }
      if (options.method === 'DELETE' && target.endsWith('/api/projects/A/source/annotations/note-1')) {
        return { ok: true }
      }
      if (target.endsWith('/api/projects')) {
        return jsonResponse({ projects: [] })
      }
      throw new Error(`Unhandled fetch: ${target}`)
    })
    const workspace = mountComposable()
    workspace.activeProject.value = { id: 'A', repo_url: 'repo-a', status: 'ready' }
    workspace.sourceFile.value = { path: 'a.py', content: 'from A', size: 6, truncated: false }

    await workspace.createSourceAnnotation({ path: 'a.py', line: 1, body: 'first' })

    expect(workspace.sourceAnnotations.value).toHaveLength(1)
    expect(workspace.sourceAnnotations.value[0].body).toBe('first')

    await workspace.updateSourceAnnotation(workspace.sourceAnnotations.value[0], 'updated')

    expect(workspace.sourceAnnotations.value[0].body).toBe('updated')

    await workspace.deleteSourceAnnotation(workspace.sourceAnnotations.value[0])

    expect(workspace.sourceAnnotations.value).toEqual([])
  })

  it('aborts an in-flight chat stream when the user stops the answer', async () => {
    let chatSignal
    globalThis.fetch = vi.fn(async (url, options = {}) => {
      const target = String(url)
      if (options.method === 'POST' && target.endsWith('/api/projects/A/chat/stream')) {
        chatSignal = options.signal
        return new Promise((resolve, reject) => {
          options.signal.addEventListener('abort', () => {
            reject(Object.assign(new Error('Aborted'), { name: 'AbortError' }))
          })
        })
      }
      if (target.endsWith('/api/projects')) {
        return jsonResponse({ projects: [] })
      }
      throw new Error(`Unhandled fetch: ${target}`)
    })
    const workspace = mountComposable()
    workspace.activeProject.value = { id: 'A', repo_url: 'repo-a', status: 'ready' }
    workspace.question.value = '从哪里开始阅读？'

    const asking = workspace.askQuestion()
    workspace.stopQuestion()
    await asking

    expect(chatSignal.aborted).toBe(true)
    expect(workspace.asking.value).toBe(false)
    expect(workspace.chatMessages.value.at(-1).text).toBe('已中止回答。')
  })
})
