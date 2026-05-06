<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  error: { type: String, default: '' },
  file: { type: Object, default: null },
  fileLoading: { type: Boolean, default: false },
  isReady: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  tree: { type: Array, default: () => [] },
})

const emit = defineEmits(['load-file', 'refresh'])
const collapsedDirs = ref(new Set())
const sourceRows = computed(() => flattenSourceTree(props.tree))

watch(
  () => props.tree,
  () => {
    collapsedDirs.value = new Set()
  },
)

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
  if (next.has(path)) {
    next.delete(path)
  } else {
    next.add(path)
  }
  collapsedDirs.value = next
}

function handleRowClick(item) {
  if (item.type === 'directory') {
    toggleDirectory(item.path)
    return
  }
  emit('load-file', item.path)
}
</script>

<template>
  <section class="source-panel">
    <div class="panel-title">
      <FolderOpen :size="18" />
      <span>源码浏览</span>
      <button v-if="isReady" class="panel-action" :disabled="loading" @click="emit('refresh')">
        <Loader2 v-if="loading" class="spin" :size="16" />
        <FolderOpen v-else :size="16" />
        <span>{{ loading ? '加载中' : '刷新目录' }}</span>
      </button>
    </div>
    <p v-if="error" class="error source-error">{{ error }}</p>
    <div v-if="isReady" class="source-browser">
      <div class="source-tree" aria-label="源码目录树">
        <button
          v-for="item in sourceRows"
          :key="item.path"
          :class="['source-row', item.type, { active: file?.path === item.path, collapsed: item.collapsed }]"
          :disabled="item.type === 'file' && fileLoading"
          :aria-expanded="item.type === 'directory' ? String(!item.collapsed) : undefined"
          :aria-label="item.type === 'directory' ? `${item.collapsed ? '展开' : '折叠'} ${item.path}` : `查看 ${item.path}`"
          :style="{ paddingLeft: `${12 + item.depth * 18}px` }"
          @click="handleRowClick(item)"
        >
          <span class="source-toggle">
            <ChevronRight v-if="item.type === 'directory' && item.collapsed" :size="14" />
            <ChevronDown v-else-if="item.type === 'directory'" :size="14" />
          </span>
          <FolderOpen v-if="item.type === 'directory'" class="source-kind-icon" :size="15" />
          <FileText v-else class="source-kind-icon" :size="15" />
          <span>{{ item.name }}</span>
        </button>
        <p v-if="!sourceRows.length && !loading" class="muted source-empty">暂无可预览源码文件。</p>
        <p v-if="loading" class="muted source-empty">正在读取目录...</p>
      </div>
      <div class="source-preview">
        <div v-if="file" class="source-file-head">
          <strong>{{ file.path }}</strong>
          <small>{{ file.size }} bytes{{ file.truncated ? ' · 已截断' : '' }}</small>
        </div>
        <pre v-if="file" class="source-code"><code>{{ file.content }}</code></pre>
        <div v-else class="source-placeholder">
          <Search :size="34" />
          <span>{{ fileLoading ? '正在读取文件...' : '选择一个文件查看源码' }}</span>
        </div>
      </div>
    </div>
    <div v-else class="source-placeholder locked">
      <FolderOpen :size="34" />
      <span>项目分析完成后可查看源码目录。</span>
    </div>
  </section>
</template>
