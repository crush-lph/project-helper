import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SourceBrowser from './SourceBrowser.vue'

const iconStubs = {
  ChevronDown: true,
  ChevronRight: true,
  FileText: true,
  FileCode2: true,
  Filter: true,
  FolderOpen: true,
  FolderTree: true,
  Loader2: true,
  MessageSquarePlus: true,
  MessageSquareText: true,
  RefreshCw: true,
  Search: true,
  ScanSearch: true,
}

describe('SourceBrowser', () => {
  it('toggles directory rows without emitting file loads', async () => {
    const wrapper = mount(SourceBrowser, {
      props: {
        isReady: true,
        tree: [
          {
            type: 'directory',
            name: 'src',
            path: 'src',
            children: [{ type: 'file', name: 'main.js', path: 'src/main.js', size: 12 }],
          },
        ],
      },
      global: { stubs: iconStubs },
    })

    expect(wrapper.text()).toContain('main.js')

    await wrapper.get('button[aria-label="折叠 src"]').trigger('click')

    expect(wrapper.text()).not.toContain('main.js')
    expect(wrapper.emitted('load-file')).toBeUndefined()

    await wrapper.get('button[aria-label="展开 src"]').trigger('click')
    await wrapper.get('button[aria-label="查看 src/main.js"]').trigger('click')

    expect(wrapper.emitted('load-file')?.[0]).toEqual(['src/main.js'])
  })

  it('resets collapsed state when a new tree is loaded', async () => {
    const wrapper = mount(SourceBrowser, {
      props: {
        isReady: true,
        tree: [
          {
            type: 'directory',
            name: 'src',
            path: 'src',
            children: [{ type: 'file', name: 'main.js', path: 'src/main.js', size: 12 }],
          },
        ],
      },
      global: { stubs: iconStubs },
    })

    await wrapper.get('button[aria-label="折叠 src"]').trigger('click')
    expect(wrapper.text()).not.toContain('main.js')

    await wrapper.setProps({
      tree: [
        {
          type: 'directory',
          name: 'app',
          path: 'app',
          children: [{ type: 'file', name: 'server.py', path: 'app/server.py', size: 22 }],
        },
      ],
    })

    expect(wrapper.text()).toContain('server.py')
  })

  it('renders source preview with syntax highlighting', () => {
    const wrapper = mount(SourceBrowser, {
      props: {
        isReady: true,
        file: {
          path: 'src/main.js',
          content: 'function hello() { return "world" }',
          size: 35,
          truncated: false,
        },
      },
      global: { stubs: iconStubs },
    })

    expect(wrapper.get('.line-content').html()).toContain('hljs-keyword')
  })

  it('renders annotation markers and emits annotation actions', async () => {
    const wrapper = mount(SourceBrowser, {
      props: {
        isReady: true,
        annotations: [{ id: 'note-1', path: 'src/main.js', line: 1, body: '入口逻辑', created_at: '1' }],
        file: {
          path: 'src/main.js',
          content: 'function hello() {\n  return "world"\n}',
          size: 37,
          truncated: false,
        },
      },
      global: { stubs: iconStubs },
    })

    expect(wrapper.text()).toContain('入口逻辑')
    expect(wrapper.get('button[aria-label="查看或新增第 1 行批注"]').exists()).toBe(true)

    await wrapper.get('button[aria-label="给第 2 行添加批注"]').trigger('click')
    await wrapper.get('textarea').setValue('这里返回结果')
    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('create-annotation')?.[0]).toEqual([
      { path: 'src/main.js', line: 2, body: '这里返回结果' },
    ])

    await wrapper.get('.annotation-actions button').trigger('click')
    await wrapper.get('textarea').setValue('更新批注')
    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('update-annotation')?.[0]).toEqual([
      { id: 'note-1', path: 'src/main.js', line: 1, body: '入口逻辑', created_at: '1' },
      '更新批注',
    ])
  })
})
