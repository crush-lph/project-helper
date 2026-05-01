<script setup>
import { computed, onMounted, ref } from 'vue'
import { marked } from 'marked'
import { useDialog } from 'naive-ui'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'
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

const pipelineSteps = [
  { key: 'connect', label: '建立任务', hint: '创建项目并连接实时通道' },
  { key: 'clone', label: '同步仓库', hint: '克隆或更新 GitHub 代码' },
  { key: 'scan', label: '扫描源码', hint: '识别目录、技术栈和关键文件' },
  { key: 'summarize', label: '生成报告', hint: '整理成新手友好的源码地图' },
  { key: 'done', label: '完成缓存', hint: '保存结果并开放问答' },
]

const stepOrder = pipelineSteps.map((step) => step.key)

const reportHtml = computed(() => marked.parse(activeProject.value?.report || ''))
const isReady = computed(() => activeProject.value?.status === 'ready')
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

async function refreshProjects() {
  const response = await fetch(`${API_BASE}/api/projects`)
  const data = await response.json()
  projects.value = data.projects || []
}

async function createAndAnalyze() {
  loading.value = true
  error.value = ''
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
    streamAnalysis(activeProject.value.id)
  } catch (err) {
    error.value = err.message
    loading.value = false
  }
}

function streamAnalysis(projectId) {
  const events = new EventSource(`${API_BASE}/api/projects/${projectId}/analyze/stream`)
  events.addEventListener('progress', (event) => {
    progress.value.push(JSON.parse(event.data))
  })
  events.addEventListener('cached', (event) => {
    const data = JSON.parse(event.data)
    progress.value.push({ step: 'cache', message: data.message })
  })
  events.addEventListener('done', async () => {
    progress.value.push({ step: 'done', message: '分析完成，报告已保存到本地缓存。' })
    const response = await fetch(`${API_BASE}/api/projects/${projectId}`)
    if (response.ok) {
      activeProject.value = await response.json()
    }
    loading.value = false
    events.close()
    await refreshProjects()
  })
  events.addEventListener('failed', (event) => {
    if (event.data) {
      error.value = JSON.parse(event.data).message
    } else {
      error.value = '分析失败，请确认仓库地址和后端服务状态。'
    }
    progress.value.push({ step: 'failed', message: error.value })
    loading.value = false
    events.close()
  })
  events.onerror = () => {
    if (loading.value) {
      error.value = '分析连接中断，请确认后端服务仍在运行。'
      progress.value.push({ step: 'failed', message: error.value })
      loading.value = false
      events.close()
    }
  }
}

async function loadProject(project) {
  const response = await fetch(`${API_BASE}/api/projects/${project.id}`)
  activeProject.value = response.ok ? await response.json() : project
  repoUrl.value = activeProject.value.repo_url
  progress.value = [{ step: 'cache', message: '已加载缓存报告。' }]
  chatMessages.value = []
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
  asking.value = true
  const userText = question.value.trim()
  chatMessages.value.push({ role: 'user', text: userText })
  const assistant = { role: 'assistant', text: '' }
  chatMessages.value.push(assistant)

  const response = await fetch(`${API_BASE}/api/projects/${activeProject.value.id}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: userText }),
  })
  if (!response.ok || !response.body) {
    assistant.text = '问答请求失败，请稍后重试。'
    asking.value = false
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''
    for (const frame of frames) {
      const event = parseSse(frame)
      if (event.event === 'token') {
        assistant.text += event.data.text
      }
      if (event.event === 'error') {
        assistant.text += `\n${event.data.message}`
      }
    }
  }
  asking.value = false
}

function parseSse(frame) {
  const lines = frame.split('\n')
  const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim()
  const dataText = lines.find((line) => line.startsWith('data:'))?.slice(5).trim() || '{}'
  return { event, data: JSON.parse(dataText) }
}

onMounted(refreshProjects)
</script>

<template>
  <main class="shell">
    <section class="hero">
      <div class="hero-copy">
        <div class="brand-row">
          <span class="brand-mark"><Code2 :size="24" /></span>
          <span>project-helper</span>
        </div>
        <h1>把开源项目讲到新手也能顺着读懂</h1>
        <p>输入 GitHub 仓库，自动克隆、扫描、生成完整源码地图，并让 Agent 带着工具回答你的代码问题。</p>
      </div>
      <div class="command-panel">
        <label for="repo">GitHub 仓库地址</label>
        <div class="repo-form">
          <input id="repo" v-model="repoUrl" placeholder="https://github.com/owner/repo" @keydown.enter="createAndAnalyze" />
          <button :disabled="loading" @click="createAndAnalyze">
            <Loader2 v-if="loading" class="spin" :size="18" />
            <Play v-else :size="18" />
            <span>{{ loading ? '分析中' : '开始分析' }}</span>
          </button>
        </div>
        <div class="status-strip">
          <span><Database :size="16" /> SQLite 缓存</span>
          <span><TerminalSquare :size="16" /> SSE 实时进度</span>
          <span><Bot :size="16" /> LangChain Agent</span>
        </div>
        <p v-if="error" class="error">{{ error }}</p>
      </div>
    </section>

    <section class="workspace">
      <aside class="sidebar">
        <div class="panel-title">
          <FolderGit2 :size="18" />
          <span>已分析项目</span>
        </div>
        <div
          v-for="project in projects"
          :key="project.id"
          :class="['project-item', { active: activeProject?.id === project.id, pinned: project.pinned }]"
        >
          <button class="project-load" :disabled="busyProjectId === project.id" @click="loadProject(project)">
            <span class="project-name-row">
              <Pin v-if="project.pinned" :size="14" />
              <strong>{{ project.name }}</strong>
            </span>
            <small>{{ project.status }} · {{ project.repo_url }}</small>
          </button>
          <div class="project-actions" aria-label="项目操作">
            <button
              class="icon-button"
              :title="project.pinned ? '取消置顶' : '置顶'"
              :aria-label="project.pinned ? '取消置顶' : '置顶'"
              :disabled="busyProjectId === project.id"
              @click="togglePinned(project)"
            >
              <PinOff v-if="project.pinned" :size="16" />
              <Pin v-else :size="16" />
            </button>
            <button
              class="icon-button danger"
              title="删除"
              aria-label="删除"
              :disabled="busyProjectId === project.id"
              @click="deleteProject(project)"
            >
              <Trash2 :size="16" />
            </button>
          </div>
        </div>
        <p v-if="!projects.length" class="muted">还没有缓存项目。</p>
      </aside>

      <section class="main-grid">
        <div class="progress-panel">
          <div class="metric">
            <span>当前状态</span>
            <strong>{{ statusLabel }}</strong>
            <small>{{ latestProgress?.message || '等待任务开始' }}</small>
          </div>
          <div class="progress-workbench">
            <div class="progress-track" aria-label="分析进度">
              <span :style="{ width: `${progressPercent}%` }"></span>
            </div>
            <div class="step-map">
              <div v-for="step in pipelineSteps" :key="step.key" :class="['stage', stepState(step.key)]">
                <span class="stage-dot">
                  <CheckCircle2 v-if="stepState(step.key) === 'done'" :size="15" />
                  <Loader2 v-else-if="stepState(step.key) === 'active'" class="spin" :size="15" />
                  <span v-else></span>
                </span>
                <span class="stage-copy">
                  <strong>{{ step.label }}</strong>
                  <small>{{ step.hint }}</small>
                </span>
              </div>
            </div>
            <div v-if="progress.length" class="event-stream">
              <div class="stream-head">
                <span>{{ isCachedRun ? '缓存命中' : '实时输出' }}</span>
                <small>{{ progress.length }} 条事件</small>
              </div>
              <div class="stream-list">
                <div v-for="(item, index) in progressLog" :key="`${item.step}-${index}`" :class="['stream-item', item.step]">
                  <span class="stream-badge">{{ item.step }}</span>
                  <span>{{ item.message }}</span>
                </div>
              </div>
            </div>
            <div v-else class="step quiet">
              <Sparkles :size="17" />
              <span>输入仓库地址后，克隆、扫描、生成报告的实时状态会显示在这里。</span>
            </div>
          </div>
        </div>

        <article class="report-panel">
          <div class="panel-title">
            <BookOpen :size="18" />
            <span>源码分析报告</span>
          </div>
          <div v-if="activeProject?.report" class="markdown-body" v-html="reportHtml"></div>
          <div v-else class="empty-state">
            <Search :size="42" />
            <h2>等待一份源码地图</h2>
            <p>报告会覆盖项目概述、技术栈、目录结构、核心模块、数据流、设计模式和阅读路线。</p>
          </div>
        </article>

        <section class="chat-panel">
          <div class="panel-title">
            <MessageSquareText :size="18" />
            <span>源码问答</span>
          </div>
          <div class="chat-log">
            <div v-for="(message, index) in chatMessages" :key="index" :class="['message', message.role]">
              <div v-if="message.role === 'assistant'" class="markdown-body compact" v-html="marked.parse(message.text || '思考中...')"></div>
              <p v-else>{{ message.text }}</p>
            </div>
            <p v-if="!chatMessages.length" class="muted">报告生成后，可以问：“这个项目的启动流程是什么？”、“核心模块怎么协作？”</p>
          </div>
          <div class="ask-form">
            <input v-model="question" :disabled="!isReady || asking" @keydown.enter="askQuestion" />
            <button :disabled="!isReady || asking" @click="askQuestion">
              <Loader2 v-if="asking" class="spin" :size="18" />
              <Bot v-else :size="18" />
              <span>{{ asking ? '回答中' : '提问' }}</span>
            </button>
          </div>
        </section>
      </section>
    </section>
  </main>
</template>
