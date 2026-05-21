<script setup>
import { computed, ref, watch } from 'vue'
import AuthPanel from './components/AuthPanel.vue'
import ChatPanel from './components/ChatPanel.vue'
import EditorTabBar from './components/EditorTabBar.vue'
import ReportPanel from './components/ReportPanel.vue'
import SourceBrowser from './components/SourceBrowser.vue'
import WorkspaceExplorer from './components/WorkspaceExplorer.vue'
import { useProjectHelper } from './composables/useProjectHelper'
import { closeEditorTab, createInitialTabs, openEditorTab } from './helpers/editorTabs'

const workspace = useProjectHelper()
const isCreateMode = ref(false)
const editorState = ref(createInitialTabs())

const isAnalyzing = computed(() => workspace.loading.value && !workspace.isReady.value)
const isFailed = computed(() => !workspace.loading.value && !!workspace.error.value && !workspace.isReady.value)
const showEditorTabs = computed(() => workspace.isReady.value && !isCreateMode.value && !isAnalyzing.value)
const activeFilePath = computed(() => editorState.value.activeTab === 'report' ? '' : editorState.value.activeTab)
const latestStatus = computed(() => workspace.latestProgress.value?.message || workspace.statusLabel.value)

watch(
  () => workspace.activeProject.value?.id,
  () => {
    const defaultPath = workspace.sourceFile.value?.path || ''
    editorState.value = createInitialTabs(defaultPath)
    isCreateMode.value = false
  },
)

watch(
  () => workspace.sourceFile.value?.path,
  (path) => {
    if (!path || !workspace.isReady.value) return
    editorState.value = openEditorTab(editorState.value, path)
  },
)

function showCreateProject() {
  isCreateMode.value = true
  editorState.value = createInitialTabs()
}

function createProject() {
  isCreateMode.value = false
  workspace.createAndAnalyze()
}

function selectEditorTab(tabId) {
  editorState.value = { ...editorState.value, activeTab: tabId }
}

function closeTab(tabId) {
  editorState.value = closeEditorTab(editorState.value, tabId)
}

function loadFile(path) {
  editorState.value = openEditorTab(editorState.value, path)
  workspace.loadSourceFile(path)
}

function retryAnalysis() {
  workspace.createAndAnalyze()
}
</script>

<template>
  <AuthPanel
    v-if="!workspace.isAuthenticated.value"
    v-model:mode="workspace.authMode.value"
    v-model:password="workspace.authPassword.value"
    v-model:username="workspace.authUsername.value"
    :error="workspace.authError.value"
    :loading="workspace.authLoading.value"
    @submit="workspace.authenticate"
  />
  <main v-else class="ide-shell">
    <nav class="ide-rail" aria-label="主导航">
      <span class="ide-brand">P</span>
      <button class="rail-icon" title="新建项目" aria-label="新建项目" @click="showCreateProject">
        <Plus :size="18" />
      </button>
      <span class="rail-icon active"><PanelsTopLeft :size="18" /></span>
      <span class="rail-icon"><Search :size="18" /></span>
      <span class="rail-spacer" />
      <button class="rail-icon" title="退出登录" @click="workspace.logout">
        <LogOut :size="17" />
      </button>
    </nav>

    <WorkspaceExplorer
        :active-project-id="workspace.activeProject.value?.id"
        :active-path="activeFilePath"
        :busy-project-id="workspace.busyProjectId.value"
        :projects="workspace.projects.value"
        :source-loading="workspace.sourceLoading.value"
        :tree="workspace.sourceTree.value"
        :user="workspace.authUser.value"
        @create-project="showCreateProject"
        @delete="workspace.deleteProject"
        @load-file="loadFile"
        @load-project="workspace.loadProject"
        @logout="workspace.logout"
        @toggle-pin="workspace.togglePinned"
      />

    <section class="ide-main">
      <header class="ide-topbar">
        <label class="repo-command">
          <span>GitHub</span>
          <input
            v-model="workspace.repoUrl.value"
            :disabled="workspace.loading.value"
            placeholder="https://github.com/owner/repo"
            @keydown.enter="createProject"
          />
        </label>
        <button v-if="!isCreateMode" class="ide-primary" @click="showCreateProject">新建项目</button>
        <button v-else class="ide-primary" :disabled="workspace.loading.value" @click="createProject">
          {{ workspace.loading.value ? '分析中' : '开始分析' }}
        </button>
      </header>

      <EditorTabBar
        v-if="showEditorTabs"
        :active-tab="editorState.activeTab"
        :tabs="editorState.tabs"
        @close="closeTab"
        @select="selectEditorTab"
      />

      <section class="editor-surface">
        <section v-if="isCreateMode" class="import-workspace">
          <div class="import-card">
            <h1>导入一个 GitHub 仓库</h1>
            <p>粘贴仓库地址，project-helper 会生成源码索引、学习报告和项目专属 Agent。</p>
            <div class="import-input">
              <input v-model="workspace.repoUrl.value" placeholder="https://github.com/owner/repo" @keydown.enter="createProject" />
              <button :disabled="workspace.loading.value" @click="createProject">开始分析</button>
            </div>
            <div class="example-row">
              <button @click="workspace.repoUrl.value = 'https://github.com/vuejs/core'">https://github.com/vuejs/core</button>
              <button @click="workspace.repoUrl.value = 'https://github.com/fastapi/fastapi'">https://github.com/fastapi/fastapi</button>
              <button @click="workspace.repoUrl.value = 'https://github.com/vercel/next.js'">https://github.com/vercel/next.js</button>
            </div>
            <p v-if="workspace.error.value" class="error">{{ workspace.error.value }}</p>
          </div>
        </section>

        <section v-else-if="isAnalyzing" class="analysis-workspace">
          <article class="analysis-card">
            <header>
              <div>
                <h1>正在分析项目</h1>
                <p>源码和报告生成前，中间区域只展示必要状态。完成后会打开 Report 和默认源码页签。</p>
              </div>
              <strong>{{ Math.round(workspace.progressPercent.value) }}%</strong>
            </header>
            <div class="analysis-meter"><span :style="{ width: `${workspace.progressPercent.value}%` }" /></div>
            <div class="analysis-steps">
              <div
                v-for="step in workspace.pipelineSteps"
                :key="step.key"
                :class="['analysis-step', workspace.stepState(step.key)]"
              >
                <span>{{ workspace.stepState(step.key) === 'done' ? '✓' : workspace.stepState(step.key) === 'active' ? '•' : '○' }}</span>
                <div>
                  <strong>{{ step.label }}</strong>
                  <small>{{ step.hint }}</small>
                </div>
              </div>
            </div>
            <p class="muted">{{ latestStatus }}</p>
          </article>
        </section>

        <template v-else-if="workspace.isReady.value">
        <SourceBrowser
          v-show="editorState.activeTab !== 'report'"
          :annotation-error="workspace.sourceAnnotationError.value"
          :annotation-loading="workspace.sourceAnnotationLoading.value"
          :annotation-saving="workspace.sourceAnnotationSaving.value"
          :annotations="workspace.sourceAnnotations.value"
          :error="workspace.sourceError.value"
          :file="workspace.sourceFile.value"
          :file-loading="workspace.sourceFileLoading.value"
          :is-ready="workspace.isReady.value"
          :loading="workspace.sourceLoading.value"
          :tree="workspace.sourceTree.value"
          @create-annotation="workspace.createSourceAnnotation"
          @delete-annotation="workspace.deleteSourceAnnotation"
          @load-file="workspace.loadSourceFile"
          @refresh="workspace.fetchSourceTree"
          @update-annotation="workspace.updateSourceAnnotation"
        />

        <ReportPanel
          v-show="editorState.activeTab === 'report'"
          :project="workspace.activeProject.value"
        />
        </template>

        <section v-else-if="isFailed" class="failed-workspace">
          <div class="failed-card">
            <h1>分析失败</h1>
            <p>{{ workspace.error.value }}</p>
            <div class="failed-actions">
              <button class="ide-primary" @click="retryAnalysis">重试分析</button>
              <button class="ide-secondary" @click="showCreateProject">返回导入</button>
            </div>
          </div>
        </section>

        <section v-else class="empty-editor-state">
          <FileSearch :size="40" />
          <h1>选择或导入一个项目</h1>
          <p>从左侧选择缓存项目，或创建一个新的 GitHub 仓库分析任务。</p>
          <button class="ide-primary" @click="showCreateProject">导入仓库</button>
        </section>
      </section>
    </section>

    <ChatPanel
      v-model="workspace.question.value"
      class="ide-agent"
      :asking="workspace.asking.value"
      :is-ready="workspace.isReady.value"
      :messages="workspace.chatMessages.value"
      :source-tree="workspace.sourceTree.value"
      :referenced-files="workspace.referencedFiles.value"
      @ask="workspace.askQuestion"
      @stop="workspace.stopQuestion"
      @update:referenced-files="(files) => workspace.referencedFiles.value = files"
    />
  </main>
</template>
