import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AuthPanel from './AuthPanel.vue'

const iconStubs = {
  Loader2: true,
  LogIn: true,
}

describe('AuthPanel', () => {
  it('switches auth mode and submits the selected mode', async () => {
    const wrapper = mount(AuthPanel, {
      props: {
        mode: 'login',
        username: '',
        password: '',
      },
      global: { stubs: iconStubs },
    })

    await wrapper.get('button[data-mode="register"]').trigger('click')
    expect(wrapper.emitted('update:mode')?.[0]).toEqual(['register'])

    await wrapper.setProps({ mode: 'register' })
    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('submit')?.[0]).toEqual(['register'])
  })
})
