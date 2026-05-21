<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  activeProjectId: { type: String, default: '' },
  activePath: { type: String, default: '' },
  busyProjectId: { type: String, default: '' },
  projects: { type: Array, default: () => [] },
  sourceLoading: { type: Boolean, default: false },
  tree: { type: Array, default: () => [] },
  user: { type: Object, default: null },
})

const emit = defineEmits(['create-project', 'delete', 'load-file', 'load-project', 'logout', 'toggle-pin'])

const collapsedDirs = ref(new Set())
const switcherOpen = ref(false)

watch(
  () => props.tree,
  () => {
    collapsedDirs.value = new Set()
  },
)

const activeProject = computed(() => props.projects.find((project) => project.id === props.activeProjectId) || null)
const sourceRows = computed(() => flattenSourceTree(props.tree))

function flattenSourceTree(nodes, depth = 0) {
  return nodes.flatMap((node) => {
    const collapsed = node.type === 'directory' && collapsedDirs.value.has(node.path)
    return [
      { ...node, depth, collapsed },
      ...(node.children && !collapsed ? flattenSourceTree(node.children, depth + 1) : []),
    ]
  })
}

function toggleDirectory(path) {
  const next = new Set(collapsedDirs.value)
  if (next.has(path)) next.delete(path)
  else next.add(path)
  collapsedDirs.value = next
}

function handleSourceRow(item) {
  if (item.type === 'directory') {
    toggleDirectory(item.path)
    return
  }
  emit('load-file', item.path)
}

function selectProject(project) {
  switcherOpen.value = false
  emit('load-project', project)
}
</script>

<template>
  <aside class="workspace-explorer">
    <div class="workspace-head">
      <div>
        <strong>Workspace</strong>
        <small>Project source</small>
      </div>
      <button class="icon-button" title="新建项目" aria-label="新建项目" @click="emit('create-project')">
        <Plus :size="17" />
      </button>
    </div>

    <section class="workspace-switcher">
      <button class="workspace-current" @click="switcherOpen = !switcherOpen">
        <span class="workspace-mark"><FolderGit2 :size="16" /></span>
        <span>
          <strong>{{ activeProject?.name || 'New import' }}</strong>
          <small>{{ activeProject?.repo_url || '准备导入新仓库' }}</small>
        </span>
        <ChevronDown :size="16" />
      </button>
      <div v-if="switcherOpen" class="workspace-popover">
        <div class="popover-title">最近项目</div>
        <div
          v-for="project in projects"
          :key="project.id"
          :class="['workspace-option', { active: activeProjectId === project.id }]"
        >
          <button :disabled="busyProjectId === project.id" @click="selectProject(project)">
            <strong>{{ project.name }}</strong>
            <small>{{ project.status }} · {{ project.repo_url }}</small>
          </button>
          <span class="workspace-option-actions">
            <button
              class="mini-icon"
              :title="project.pinned ? '取消置顶' : '置顶'"
              :aria-label="project.pinned ? '取消置顶' : '置顶'"
              @click.stop="emit('toggle-pin', project)"
            >
              <PinOff v-if="project.pinned" :size="14" />
              <Pin v-else :size="14" />
            </button>
            <button class="mini-icon danger" title="删除" aria-label="删除" @click.stop="emit('delete', project)">
              <Trash2 :size="14" />
            </button>
          </span>
        </div>
        <p v-if="!projects.length" class="muted">还没有缓存项目。</p>
      </div>
    </section>

    <section class="explorer-tree">
      <div class="explorer-title">
        <span>Explorer</span>
        <small v-if="sourceLoading">加载中</small>
      </div>
      <button
        v-for="item in sourceRows"
        :key="item.path"
        :class="['explorer-row', item.type, { active: activePath === item.path }]"
        :style="{ paddingLeft: `${10 + item.depth * 16}px` }"
        @click="handleSourceRow(item)"
      >
        <ChevronRight v-if="item.type === 'directory' && item.collapsed" :size="14" />
        <ChevronDown v-else-if="item.type === 'directory'" :size="14" />
        <span v-else class="row-spacer" />
        <Folder v-if="item.type === 'directory'" :size="15" />
        <FileText v-else :size="15" />
        <span>{{ item.name }}</span>
      </button>
      <div v-if="!sourceRows.length" class="explorer-empty">
        <FolderOpen :size="24" />
        <span>{{ sourceLoading ? '正在读取目录...' : '分析完成后显示源码目录。' }}</span>
      </div>
    </section>

    <button class="workspace-user" @click="emit('logout')">
      <span class="user-avatar">{{ user?.username?.slice(0, 2)?.toUpperCase() || 'U' }}</span>
      <span>
        <strong>{{ user?.username || 'User' }}</strong>
        <small>退出登录</small>
      </span>
    </button>
  </aside>
</template>
