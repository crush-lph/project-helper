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
