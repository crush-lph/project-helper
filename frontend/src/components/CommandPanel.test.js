import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CommandPanel from './CommandPanel.vue'

const iconStubs = {
  Bot: true,
  Code2: true,
  Database: true,
  GitBranch: true,
  Loader2: true,
  Play: true,
  TerminalSquare: true,
}

describe('CommandPanel', () => {
  it('emits model updates and submit from the command form', async () => {
    const wrapper = mount(CommandPanel, {
      props: {
        modelValue: 'https://github.com/example/demo',
        statusLabel: '等待输入',
      },
      global: { stubs: iconStubs },
    })

    await wrapper.get('#repo').setValue('https://github.com/vuejs/core')
    await wrapper.get('#repo').trigger('keydown.enter')
    await wrapper.get('.primary-action').trigger('click')

    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['https://github.com/vuejs/core'])
    expect(wrapper.emitted('submit')).toHaveLength(2)
  })

  it('shows loading state and backend errors', () => {
    const wrapper = mount(CommandPanel, {
      props: {
        error: '分析连接中断',
        loading: true,
        modelValue: 'https://github.com/example/demo',
        statusLabel: '生成报告',
      },
      global: { stubs: iconStubs },
    })

    expect(wrapper.text()).toContain('分析中')
    expect(wrapper.text()).toContain('分析连接中断')
    expect(wrapper.get('.primary-action').attributes('disabled')).toBeDefined()
  })
})
