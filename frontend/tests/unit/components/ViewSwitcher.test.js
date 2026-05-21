import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ViewSwitcher from '../../../src/components/ViewSwitcher.vue'

const iconStubs = {
  BookOpen: true,
  FolderOpen: true,
  MessageSquareText: true,
}

describe('ViewSwitcher', () => {
  it('selects enabled tabs and keeps disabled tabs inactive', async () => {
    const wrapper = mount(ViewSwitcher, {
      props: {
        activeView: 'source',
        tabs: [
          { key: 'source', label: '源码', disabled: false },
          { key: 'report', label: '报告', disabled: true },
          { key: 'chat', label: '问答', disabled: false },
        ],
      },
      global: { stubs: iconStubs },
    })

    await wrapper.findAll('.view-tab')[1].trigger('click')
    await wrapper.findAll('.view-tab')[2].trigger('click')

    expect(wrapper.findAll('.view-tab')[1].attributes('disabled')).toBeDefined()
    expect(wrapper.emitted('select')).toEqual([['chat']])
  })
})
