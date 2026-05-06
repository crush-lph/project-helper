import { computed, onMounted, ref } from 'vue'
import { useDialog } from 'naive-ui'
import { errorMessage, responseDetail } from '../helpers/http'
import { parseSse } from '../helpers/sse'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'

export const pipelineSteps = [
  { key: 'connect', label: '建立任务', hint: '创建项目并连接实时通道' },
  { key: 'clone', label: '同步仓库', hint: '克隆或更新 GitHub 代码' },
  { key: 'scan', label: '扫描源码', hint: '识别目录、技术栈和关键文件' },
  { key: 'summarize', label: '生成报告', hint: '整理成新手友好的源码地图' },
  { key: 'done', label: '完成缓存', hint: '保存结果并开放问答' },
]

const stepOrder = pipelineSteps.map((step) => step.key)

export function useProjectHelper() {
  const dialog = useDialog()
  const repoUrl = ref('https://github.com/fastapi/fastapi')
  const activeProject = ref(null)
  const projects = ref([])
  const progress = ref([])
  const loading = ref(false)
  const error = ref('')
  const question = ref('这个项目的启动流程是什么？')
  const chatMessages = ref([])
  const asking = ref(false)
  const busyProjectId = ref('')
  const sourceTree = ref([])
  const sourceFile = ref(null)
  const sourceLoading = ref(false)
  const sourceFileLoading = ref(false)
  const sourceError = ref('')
  const activeView = ref('source')
  let activeAnalysisStream = null
  let analysisStreamToken = 0
  let sourceTreeRequestToken = 0
  let sourceFileRequestToken = 0

  const isReady = computed(() => activeProject.value?.status === 'ready')
  const workspaceTabs = computed(() => [
    { key: 'source', label: '源码', disabled: !isReady.value },
    { key: 'report', label: '报告', disabled: !activeProject.value?.report },
    { key: 'chat', label: '问答', disabled: !isReady.value },
  ])
  const latestProgress = computed(() => progress.value.at(-1))
  const isCachedRun = computed(() => progress.value.some((item) => item.step === 'cache'))
  const activeStepKey = computed(() => {
    if (isCachedRun.value) return 'done'
    if (isReady.value) return 'done'
    const lastKnownStep = progress.value
      .slice()
      .reverse()
      .find((item) => stepOrder.includes(item.step))
    return lastKnownStep?.step || 'connect'
  })
  const activeStepIndex = computed(() => {
    const index = stepOrder.indexOf(activeStepKey.value)
    return index >= 0 ? index : 0
  })
  const progressPercent = computed(() => {
    if (error.value) return Math.max(8, (activeStepIndex.value / (pipelineSteps.length - 1)) * 100)
    if (isReady.value || activeStepKey.value === 'done') return 100
    return Math.max(8, (activeStepIndex.value / (pipelineSteps.length - 1)) * 100)
  })
  const progressLog = computed(() => progress.value.slice().reverse())
  const statusLabel = computed(() => {
    const status = activeProject.value?.status || 'idle'
    const labels = {
      idle: '等待输入',
      created: '已创建',
      cloning: '克隆中',
      scanning: '扫描中',
      summarizing: '生成报告',
      ready: '已缓存',
      failed: '失败',
    }
    return labels[status] || status
  })

  function stepState(stepKey) {
    if (error.value && stepKey === activeStepKey.value) return 'failed'
    if (isReady.value || activeStepKey.value === 'done') return 'done'
    const current = stepOrder.indexOf(activeStepKey.value)
    const target = stepOrder.indexOf(stepKey)
    if (target < current) return 'done'
    if (target === current && loading.value) return 'active'
    return 'pending'
  }

  function resetSourceBrowser() {
    sourceTreeRequestToken += 1
    sourceFileRequestToken += 1
    sourceTree.value = []
    sourceFile.value = null
    sourceError.value = ''
    sourceLoading.value = false
    sourceFileLoading.value = false
  }

  function closeAnalysisStream() {
    analysisStreamToken += 1
    if (activeAnalysisStream) {
      activeAnalysisStream.close()
      activeAnalysisStream = null
    }
  }

  function selectView(view) {
    const tab = workspaceTabs.value.find((item) => item.key === view)
    if (!tab || tab.disabled) return
    activeView.value = view
  }

  async function fetchSourceTree(projectId = activeProject.value?.id) {
    if (!projectId || !isReady.value) return
    const requestToken = ++sourceTreeRequestToken
    sourceLoading.value = true
    sourceError.value = ''
    try {
      const response = await fetch(`${API_BASE}/api/projects/${projectId}/source/tree`)
      if (!response.ok) {
        throw new Error(await responseDetail(response, '源码目录加载失败'))
      }
      const data = await response.json()
      if (requestToken !== sourceTreeRequestToken || activeProject.value?.id !== projectId) return
      sourceTree.value = data.tree || []
      if (!hasSourcePath(sourceTree.value, sourceFile.value?.path)) {
        sourceFile.value = null
      }
      if (sourceTree.value.length && activeView.value !== 'chat') {
        activeView.value = 'source'
      }
    } catch (err) {
      if (requestToken !== sourceTreeRequestToken || activeProject.value?.id !== projectId) return
      sourceError.value = errorMessage(err, '源码目录加载失败')
    } finally {
      if (requestToken === sourceTreeRequestToken) {
        sourceLoading.value = false
      }
    }
  }

  async function loadSourceFile(path) {
    const projectId = activeProject.value?.id
    if (!projectId || !path || sourceFileLoading.value) return
    const requestToken = ++sourceFileRequestToken
    sourceFileLoading.value = true
    sourceError.value = ''
    try {
      const response = await fetch(`${API_BASE}/api/projects/${projectId}/source/file?path=${encodeURIComponent(path)}`)
      if (!response.ok) {
        throw new Error(await responseDetail(response, '源码文件加载失败'))
      }
      const data = await response.json()
      if (requestToken !== sourceFileRequestToken || activeProject.value?.id !== projectId) return
      sourceFile.value = data
    } catch (err) {
      if (requestToken !== sourceFileRequestToken || activeProject.value?.id !== projectId) return
      sourceError.value = errorMessage(err, '源码文件加载失败')
    } finally {
      if (requestToken === sourceFileRequestToken) {
        sourceFileLoading.value = false
      }
    }
  }

  async function refreshProjects() {
    const response = await fetch(`${API_BASE}/api/projects`)
    const data = await response.json()
    projects.value = data.projects || []
  }

  async function createAndAnalyze() {
    closeAnalysisStream()
    loading.value = true
    error.value = ''
    resetSourceBrowser()
    progress.value = []
    chatMessages.value = []
    try {
      const response = await fetch(`${API_BASE}/api/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_url: repoUrl.value }),
      })
      if (!response.ok) {
        const detail = await response.json()
        throw new Error(detail.detail || '创建项目失败')
      }
      activeProject.value = await response.json()
      progress.value.push({ step: 'connect', message: '已创建项目，正在连接分析流...' })
      activeView.value = 'report'
      streamAnalysis(activeProject.value.id)
    } catch (err) {
      error.value = err.message
      loading.value = false
    }
  }

  function streamAnalysis(projectId) {
    const streamToken = analysisStreamToken
    const events = new EventSource(`${API_BASE}/api/projects/${projectId}/analyze/stream`)
    activeAnalysisStream = events
    const isCurrentStream = () => activeAnalysisStream === events && analysisStreamToken === streamToken && activeProject.value?.id === projectId
    const closeCurrentStream = () => {
      if (activeAnalysisStream === events) {
        activeAnalysisStream = null
      }
      events.close()
    }
    events.addEventListener('progress', (event) => {
      if (!isCurrentStream()) return
      progress.value.push(JSON.parse(event.data))
    })
    events.addEventListener('cached', (event) => {
      if (!isCurrentStream()) return
      const data = JSON.parse(event.data)
      progress.value.push({ step: 'cache', message: data.message })
    })
    events.addEventListener('done', async () => {
      if (!isCurrentStream()) {
        events.close()
        return
      }
      progress.value.push({ step: 'done', message: '分析完成，报告已保存到本地缓存。' })
      loading.value = false
      closeCurrentStream()
      const response = await fetch(`${API_BASE}/api/projects/${projectId}`)
      if (!isCurrentStream() && activeProject.value?.id !== projectId) {
        await refreshProjects()
        return
      }
      if (response.ok) {
        activeProject.value = await response.json()
      }
      await fetchSourceTree(projectId)
      if (!sourceTree.value.length) {
        activeView.value = 'report'
      }
      await refreshProjects()
    })
    events.addEventListener('failed', (event) => {
      if (!isCurrentStream()) {
        events.close()
        return
      }
      error.value = event.data ? JSON.parse(event.data).message : '分析失败，请确认仓库地址和后端服务状态。'
      progress.value.push({ step: 'failed', message: error.value })
      loading.value = false
      closeCurrentStream()
    })
    events.onerror = () => {
      if (loading.value && isCurrentStream()) {
        error.value = '分析连接中断，请确认后端服务仍在运行。'
        progress.value.push({ step: 'failed', message: error.value })
        loading.value = false
        closeCurrentStream()
      }
    }
  }

  async function loadProject(project) {
    closeAnalysisStream()
    loading.value = false
    resetSourceBrowser()
    const response = await fetch(`${API_BASE}/api/projects/${project.id}`)
    activeProject.value = response.ok ? await response.json() : project
    repoUrl.value = activeProject.value.repo_url
    progress.value = [{ step: 'cache', message: '已加载缓存报告。' }]
    chatMessages.value = []
    if (activeProject.value.status === 'ready') {
      await fetchSourceTree(activeProject.value.id)
    } else {
      activeView.value = 'report'
    }
  }

  async function togglePinned(project) {
    if (busyProjectId.value) return
    busyProjectId.value = project.id
    error.value = ''
    try {
      const response = await fetch(`${API_BASE}/api/projects/${project.id}/pin`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pinned: !project.pinned }),
      })
      if (!response.ok) {
        const detail = await response.json()
        throw new Error(detail.detail || '置顶状态更新失败')
      }
      const updatedProject = await response.json()
      if (activeProject.value?.id === updatedProject.id) {
        activeProject.value = { ...activeProject.value, ...updatedProject }
      }
      await refreshProjects()
    } catch (err) {
      error.value = err.message
    } finally {
      busyProjectId.value = ''
    }
  }

  async function performDeleteProject(project) {
    busyProjectId.value = project.id
    error.value = ''
    try {
      const response = await fetch(`${API_BASE}/api/projects/${project.id}`, { method: 'DELETE' })
      if (!response.ok) {
        const detail = await response.json()
        throw new Error(detail.detail || '删除项目失败')
      }
      if (activeProject.value?.id === project.id) {
        activeProject.value = null
        progress.value = []
        chatMessages.value = []
        resetSourceBrowser()
      }
      await refreshProjects()
    } catch (err) {
      error.value = err.message
    } finally {
      busyProjectId.value = ''
    }
  }

  function deleteProject(project) {
    if (busyProjectId.value) return
    dialog.warning({
      title: '删除缓存项目',
      content: `确定删除「${project.name}」的缓存记录和本地仓库副本吗？`,
      positiveText: '删除',
      negativeText: '取消',
      maskClosable: false,
      positiveButtonProps: {
        type: 'error',
        ghost: false,
      },
      negativeButtonProps: {
        ghost: true,
      },
      onPositiveClick: async () => {
        await performDeleteProject(project)
      },
    })
  }

  async function askQuestion() {
    if (!question.value.trim() || !activeProject.value) return
    activeView.value = 'chat'
    asking.value = true
    error.value = ''
    const userText = question.value.trim()
    chatMessages.value.push({ role: 'user', text: userText })
    const assistant = { role: 'assistant', text: '' }
    chatMessages.value.push(assistant)

    try {
      const response = await fetch(`${API_BASE}/api/projects/${activeProject.value.id}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: userText }),
      })
      if (!response.ok) {
        let detail = null
        try {
          detail = await response.json()
        } catch {
          // Ignore non-JSON error bodies and use the generic message below.
        }
        throw new Error(detail?.detail || '问答请求失败，请稍后重试。')
      }
      if (!response.body) {
        throw new Error('问答连接不可用，请稍后重试。')
      }

      await readChatStream(response.body, assistant)
    } catch (err) {
      const message = errorMessage(err, '问答请求失败，请稍后重试。')
      assistant.text += `${assistant.text ? '\n\n' : ''}${message}`
    } finally {
      asking.value = false
    }
  }

  onMounted(refreshProjects)

  return {
    activeProject,
    activeView,
    asking,
    askQuestion,
    busyProjectId,
    chatMessages,
    createAndAnalyze,
    deleteProject,
    error,
    fetchSourceTree,
    isCachedRun,
    isReady,
    latestProgress,
    loadProject,
    loadSourceFile,
    loading,
    pipelineSteps,
    progress,
    progressLog,
    progressPercent,
    projects,
    question,
    repoUrl,
    selectView,
    sourceError,
    sourceFile,
    sourceFileLoading,
    sourceLoading,
    sourceTree,
    statusLabel,
    stepState,
    togglePinned,
    workspaceTabs,
  }
}

function hasSourcePath(nodes, path) {
  if (!path) return false
  return nodes.some((node) => node.path === path || (node.children && hasSourcePath(node.children, path)))
}

async function readChatStream(body, assistant) {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let completed = false
  while (!completed) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''
    for (const frame of frames) {
      const streamDone = handleChatEvent(parseSse(frame), assistant)
      if (streamDone) {
        completed = true
        break
      }
    }
  }

  const tail = `${buffer}${decoder.decode()}`
  if (!completed && tail.trim()) {
    handleChatEvent(parseSse(tail), assistant)
  }
}

function handleChatEvent(event, assistant) {
  if (event.event === 'token') {
    assistant.text += event.data.text || ''
    return false
  }
  if (event.event === 'failed' || event.event === 'error') {
    throw new Error(event.data.message || '问答失败，请稍后重试。')
  }
  return event.event === 'done'
}
