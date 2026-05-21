export function createInitialTabs(defaultPath = '') {
  const tabs = [{ id: 'report', title: 'Report', type: 'report', permanent: true }]
  if (defaultPath) {
    tabs.push(fileTab(defaultPath))
  }
  return {
    activeTab: defaultPath || 'report',
    tabs,
  }
}

export function openEditorTab(state, path) {
  if (!path) return state
  const exists = state.tabs.some((tab) => tab.id === path)
  return {
    activeTab: path,
    tabs: exists ? state.tabs : [...state.tabs, fileTab(path)],
  }
}

export function closeEditorTab(state, tabId) {
  const targetIndex = state.tabs.findIndex((tab) => tab.id === tabId)
  if (targetIndex < 0 || state.tabs[targetIndex].permanent) return state
  const tabs = state.tabs.filter((tab) => tab.id !== tabId)
  const activeTab = state.activeTab === tabId
    ? tabs[Math.max(0, targetIndex - 1)]?.id || 'report'
    : state.activeTab
  return { activeTab, tabs }
}

export function resolveActiveTab(state) {
  if (state.tabs.some((tab) => tab.id === state.activeTab)) return state.activeTab
  return state.tabs[0]?.id || 'report'
}

function fileTab(path) {
  return {
    id: path,
    title: path.split('/').pop() || path,
    type: 'file',
    permanent: false,
  }
}
