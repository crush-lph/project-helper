<script setup>
import { computed, ref, watch } from 'vue'
import hljs from 'highlight.js'
import DOMPurify from 'dompurify'

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

// ---- Code Folding State ----
const foldedLines = ref(new Set())

const codeLines = computed(() => {
  const content = props.file?.content || ''
  const path = props.file?.path || ''
  if (!content) return []
  const highlighted = highlightSource(content, path)
  return splitHighlightedHtml(highlighted)
})

const foldRegions = computed(() => {
  const content = props.file?.content || ''
  const path = props.file?.path || ''
  if (!content) return []
  const lang = languageFromPath(path)
  return detectFoldRegions(content, lang)
})

const foldStartSet = computed(() => new Set(foldRegions.value.map(r => r.startLine)))

// Reset fold state when file changes
watch(
  () => props.file?.path,
  () => { foldedLines.value = new Set() },
)

function toggleFold(lineIndex) {
  const next = new Set(foldedLines.value)
  if (next.has(lineIndex)) next.delete(lineIndex)
  else next.add(lineIndex)
  foldedLines.value = next
}

function isLineHidden(lineIndex) {
  for (const start of foldedLines.value) {
    const region = foldRegions.value.find(r => r.startLine === start)
    if (region && lineIndex > region.startLine && lineIndex <= region.endLine) return true
  }
  return false
}

// ---- Directory Tree ----
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

// ---- Syntax Highlighting ----
function highlightSource(content, path) {
  const language = languageFromPath(path)
  const highlighted = language
    ? hljs.highlight(content, { language, ignoreIllegals: true }).value
    : hljs.highlightAuto(content).value
  return DOMPurify.sanitize(highlighted)
}

function languageFromPath(path) {
  const extension = path.split('.').pop()?.toLowerCase()
  const languages = {
    cjs: 'javascript',
    css: 'css',
    html: 'xml',
    js: 'javascript',
    json: 'json',
    jsx: 'javascript',
    md: 'markdown',
    mjs: 'javascript',
    py: 'python',
    sh: 'bash',
    ts: 'typescript',
    tsx: 'typescript',
    vue: 'xml',
    yml: 'yaml',
    yaml: 'yaml',
  }
  const language = languages[extension]
  return language && hljs.getLanguage(language) ? language : ''
}

// ---- Tag-Aware Line Splitting ----
// highlight.js may produce <span> tags that cross line boundaries.
// This splitter closes open tags at end of each line and re-opens them at start of next.
function splitHighlightedHtml(html) {
  const rawLines = html.split('\n')
  const result = []
  const openTags = [] // stack of "<span class='...'>" strings

  for (const rawLine of rawLines) {
    let line = ''

    // Re-open any tags that were open from previous lines
    for (const tag of openTags) {
      line += tag
    }

    // Process the raw line character by character (token-level)
    let i = 0
    while (i < rawLine.length) {
      // Check for opening tag
      if (rawLine[i] === '<' && rawLine[i + 1] === 's') {
        const closeIdx = rawLine.indexOf('>', i)
        if (closeIdx !== -1) {
          const tag = rawLine.substring(i, closeIdx + 1)
          openTags.push(tag)
          line += tag
          i = closeIdx + 1
          continue
        }
      }
      // Check for closing tag
      if (rawLine[i] === '<' && rawLine[i + 1] === '/' && rawLine[i + 2] === 's') {
        const closeIdx = rawLine.indexOf('>', i)
        if (closeIdx !== -1) {
          openTags.pop()
          line += rawLine.substring(i, closeIdx + 1)
          i = closeIdx + 1
          continue
        }
      }
      line += rawLine[i]
      i++
    }

    // Close all open tags at end of line
    for (let j = openTags.length - 1; j >= 0; j--) {
      line += '</span>'
    }

    result.push(line)
  }

  return result
}

// ---- Fold Region Detection ----
function detectFoldRegions(code, language) {
  const lines = code.split('\n')
  const indentLangs = new Set(['python', 'yaml'])
  if (indentLangs.has(language)) {
    return detectIndentFolds(lines)
  }
  return detectBraceFolds(lines)
}

// Indentation-based folding (Python, YAML)
function detectIndentFolds(lines) {
  const regions = []
  const stack = [] // { indent, lineIndex }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    if (line.trim() === '') continue
    const indent = line.search(/\S/)

    // Pop stack entries with >= indent (those blocks have ended)
    while (stack.length > 0 && stack[stack.length - 1].indent >= indent) {
      const entry = stack.pop()
      entry.endLine = i - 1
      if (entry.endLine > entry.startLine) {
        regions.push({ startLine: entry.startLine, endLine: entry.endLine })
      }
    }

    stack.push({ indent, startLine: i })
  }

  // Close remaining entries
  while (stack.length > 0) {
    const entry = stack.pop()
    entry.endLine = lines.length - 1
    if (entry.endLine > entry.startLine) {
      regions.push({ startLine: entry.startLine, endLine: entry.endLine })
    }
  }

  return regions
}

// Brace-based folding (JS, TS, JSON, CSS, etc.)
function detectBraceFolds(lines) {
  const regions = []
  const stack = [] // line index of the opening brace's line

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    // Skip lines that are only whitespace or comments
    const stripped = line.replace(/\/\/.*$/, '').replace(/\/\*.*?\*\//g, '')

    for (let j = 0; j < stripped.length; j++) {
      const ch = stripped[j]
      if (ch === '{') {
        stack.push(i)
      } else if (ch === '}') {
        const startLine = stack.pop()
        if (startLine !== undefined && i > startLine) {
          regions.push({ startLine, endLine: i })
        }
      }
    }
  }

  return regions
}
</script>

<template>
  <section class="source-panel">
    <div class="panel-title">
      <span><ScanSearch :size="20" />源码浏览</span>
      <button v-if="isReady" class="panel-action" :disabled="loading" @click="emit('refresh')">
        <Loader2 v-if="loading" class="spin" :size="16" />
        <RefreshCw v-else :size="16" />
        <span>{{ loading ? '加载中' : '刷新目录' }}</span>
      </button>
    </div>
    <p v-if="error" class="error source-error">{{ error }}</p>
    <div v-if="isReady" class="source-browser">
      <div class="source-tree" aria-label="源码目录树">
        <div class="source-tree-head">
          <span class="tool-chip"><FolderTree :size="16" />目录树</span>
          <span class="tool-chip"><Filter :size="16" />文本源码</span>
        </div>
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
          <span class="file-head-main">
            <span class="file-icon"><FileCode2 :size="18" /></span>
            <strong>{{ file.path }}</strong>
          </span>
          <span class="file-actions">
            <small>{{ file.size }} bytes{{ file.truncated ? ' · 已截断' : '' }}</small>
          </span>
        </div>
        <div v-if="file" class="source-code" role="code-viewer">
          <div
            v-for="(lineHtml, i) in codeLines"
            :key="i"
            v-show="!isLineHidden(i)"
            :class="['code-line', { 'fold-start': foldStartSet.has(i), 'folded': foldedLines.has(i) }]"
          >
            <span
              v-if="foldStartSet.has(i)"
              class="fold-gutter"
              role="button"
              :aria-label="foldedLines.has(i) ? '展开' : '折叠'"
              @click.stop="toggleFold(i)"
            >
              <ChevronRight v-if="foldedLines.has(i)" :size="12" />
              <ChevronDown v-else :size="12" />
            </span>
            <span v-else class="fold-gutter" />
            <span class="line-number">{{ i + 1 }}</span>
            <span class="line-content" v-html="lineHtml" />
          </div>
        </div>
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
