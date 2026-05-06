import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ProjectSidebar from './ProjectSidebar.vue'

const iconStubs = {
  Activity: true,
  Blocks: true,
  CheckCircle2: true,
  FolderGit2: true,
  Pin: true,
  PinOff: true,
  Trash2: true,
  Zap: true,
}

const projects = [
  { id: 'a', name: 'alpha', repo_url: 'https://github.com/example/alpha', status: 'ready', pinned: true },
  { id: 'b', name: 'beta', repo_url: 'https://github.com/example/beta', status: 'scanning', pinned: false },
]

describe('ProjectSidebar', () => {
  it('emits load, toggle-pin, and delete actions for projects', async () => {
    const wrapper = mount(ProjectSidebar, {
      props: {
        activeProjectId: 'a',
        projects,
      },
      global: { stubs: iconStubs },
    })

    await wrapper.findAll('.project-load')[1].trigger('click')
    await wrapper.get('button[aria-label="取消置顶"]').trigger('click')
    await wrapper.get('button[aria-label="删除"]').trigger('click')

    expect(wrapper.emitted('load')?.[0]).toEqual([projects[1]])
    expect(wrapper.emitted('toggle-pin')?.[0]).toEqual([projects[0]])
    expect(wrapper.emitted('delete')?.[0]).toEqual([projects[0]])
  })

  it('disables actions for the busy project', () => {
    const wrapper = mount(ProjectSidebar, {
      props: {
        busyProjectId: 'a',
        projects,
      },
      global: { stubs: iconStubs },
    })

    expect(wrapper.findAll('.project-load')[0].attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[aria-label="取消置顶"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[aria-label="删除"]').attributes('disabled')).toBeDefined()
  })
})
