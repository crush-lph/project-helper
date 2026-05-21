import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WorkspaceExplorer from './WorkspaceExplorer.vue'

const iconStubs = {
  ChevronDown: true,
  ChevronRight: true,
  FileText: true,
  Folder: true,
  FolderGit2: true,
  FolderOpen: true,
  Pin: true,
  PinOff: true,
  Plus: true,
  Trash2: true,
}

describe('WorkspaceExplorer', () => {
  it('toggles directory rows without emitting file loads', async () => {
    const wrapper = mount(WorkspaceExplorer, {
      props: {
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

    await wrapper.get('.explorer-row.directory').trigger('click')

    expect(wrapper.text()).not.toContain('main.js')
    expect(wrapper.emitted('load-file')).toBeUndefined()

    await wrapper.get('.explorer-row.directory').trigger('click')
    await wrapper.findAll('.explorer-row.file')[0].trigger('click')

    expect(wrapper.emitted('load-file')?.[0]).toEqual(['src/main.js'])
  })

  it('resets collapsed state when a new tree is loaded', async () => {
    const wrapper = mount(WorkspaceExplorer, {
      props: {
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

    await wrapper.get('.explorer-row.directory').trigger('click')
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
})
