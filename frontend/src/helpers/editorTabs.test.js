import { describe, expect, it } from 'vitest'
import { closeEditorTab, createInitialTabs, openEditorTab } from './editorTabs'

describe('editor tab helpers', () => {
  it('creates a permanent report tab and default source tab', () => {
    const state = createInitialTabs('frontend/src/App.vue')

    expect(state.activeTab).toBe('frontend/src/App.vue')
    expect(state.tabs).toEqual([
      { id: 'report', title: 'Report', type: 'report', permanent: true },
      { id: 'frontend/src/App.vue', title: 'App.vue', type: 'file', permanent: false },
    ])
  })

  it('opens a file tab once and focuses it', () => {
    const initial = createInitialTabs('frontend/src/App.vue')
    const firstOpen = openEditorTab(initial, 'frontend/src/components/ChatPanel.vue')
    const secondOpen = openEditorTab(firstOpen, 'frontend/src/components/ChatPanel.vue')

    expect(secondOpen.activeTab).toBe('frontend/src/components/ChatPanel.vue')
    expect(secondOpen.tabs.filter((tab) => tab.id === 'frontend/src/components/ChatPanel.vue')).toHaveLength(1)
  })

  it('does not close the permanent report tab', () => {
    const state = createInitialTabs('frontend/src/App.vue')

    expect(closeEditorTab(state, 'report')).toEqual(state)
  })

  it('falls back to report when closing the active file tab', () => {
    const state = createInitialTabs('frontend/src/App.vue')

    expect(closeEditorTab(state, 'frontend/src/App.vue')).toEqual({
      activeTab: 'report',
      tabs: [{ id: 'report', title: 'Report', type: 'report', permanent: true }],
    })
  })
})
