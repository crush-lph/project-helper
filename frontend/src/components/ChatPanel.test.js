import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ChatPanel from './ChatPanel.vue'

const iconStubs = {
  Bot: true,
  CircleStop: true,
  Loader2: true,
  MessageSquareText: true,
}

describe('ChatPanel', () => {
  it('emits ask when the ready form is submitted', async () => {
    const wrapper = mount(ChatPanel, {
      props: {
        isReady: true,
        modelValue: '从哪里开始读？',
      },
      global: { stubs: iconStubs },
    })

    await wrapper.get('input').trigger('keydown.enter')
    await wrapper.get('button').trigger('click')

    expect(wrapper.emitted('ask')).toHaveLength(2)
  })

  it('shows a stop action while an answer is streaming', async () => {
    const wrapper = mount(ChatPanel, {
      props: {
        asking: true,
        isReady: true,
        messages: [{ role: 'assistant', text: '正在分析' }],
      },
      global: { stubs: iconStubs },
    })

    await wrapper.get('button.stop-answer').trigger('click')

    expect(wrapper.text()).toContain('中止')
    expect(wrapper.get('button.stop-answer').attributes('disabled')).toBeUndefined()
    expect(wrapper.emitted('stop')).toHaveLength(1)
  })
})
