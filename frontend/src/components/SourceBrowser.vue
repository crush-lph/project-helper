<script setup>
import { computed, ref, watch } from 'vue'
import hljs from 'highlight.js'
import DOMPurify from 'dompurify'
import { sortAnnotations } from '../composables/useProjectHelper'

const props = defineProps({
  annotations: { type: Array, default: () => [] },
  annotationError: { type: String, default: '' },
  annotationLoading: { type: Boolean, default: false },
  annotationSaving: { type: Boolean, default: false },
  error: { type: String, default: '' },
  file: { type: Object, default: null },
  fileLoading: { type: Boolean, default: false },
  isReady: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  tree: { type: Array, default: () => [] },
})

const emit = defineEmits(['create-annotation', 'delete-annotation', 'load-file', 'refresh', 'update-annotation'])
const collapsedDirs = ref(new Set())
const sourceRows = computed(() => flattenSourceTree(props.tree))
const annotationDraft = ref({ id: '', line: null, body: '', mode: 'idle' })
const highlightedLine = ref(null)
const lineElements = new Map()

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
const sortedAnnotations = computed(() => sortAnnotations(props.annotations))
const annotatedLineSet = computed(() => new Set(props.annotations.filter(item => item.line).map(item => item.line)))
const annotationCountByLine = computed(() => {
  const counts = new Map()
  for (const item of props.annotations) {
    if (!item.line) continue
    counts.set(item.line, (counts.get(item.line) || 0) + 1)
  }
  return counts
})

// Reset fold state when file changes
watch(
  () => props.file?.path,
  () => {
    foldedLines.value = new Set()
    annotationDraft.value = { id: '', line: null, body: '', mode: 'idle' }
    highlightedLine.value = null
    lineElements.clear()
  },
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

// ---- Source Annotations ----
function startAnnotation(line = null) {
  annotationDraft.value = { id: '', line, body: '', mode: 'create' }
  if (line) {
    jumpToLine(line)
  }
}

function editAnnotation(annotation) {
  annotationDraft.value = {
    id: annotation.id,
    line: annotation.line,
    body: annotation.body,
    mode: 'edit',
  }
  if (annotation.line) {
    jumpToLine(annotation.line)
  }
}

function cancelAnnotationDraft() {
  annotationDraft.value = { id: '', line: null, body: '', mode: 'idle' }
}

function submitAnnotation() {
  const body = annotationDraft.value.body.trim()
  if (!body || !props.file) return
  if (annotationDraft.value.mode === 'edit') {
    const annotation = props.annotations.find((item) => item.id === annotationDraft.value.id)
    if (annotation) emit('update-annotation', annotation, body)
  } else {
    emit('create-annotation', {
      path: props.file.path,
      line: annotationDraft.value.line,
      body,
    })
  }
  cancelAnnotationDraft()
}

function annotationLineLabel(annotation) {
  return annotation.line ? `L${annotation.line}` : '文件'
}

function setLineElement(el, line) {
  if (el) {
    lineElements.set(line, el)
  } else {
    lineElements.delete(line)
  }
}

function jumpToLine(line) {
  highlightedLine.value = line
  const lineElement = lineElements.get(line)
  if (typeof lineElement?.scrollIntoView === 'function') {
    lineElement.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
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
  <section class="source-panel editor-source">
    <p v-if="error" class="error source-error">{{ error }}</p>
    <div v-if="isReady" class="source-browser">
      <div class="source-preview">
        <div v-if="file" class="source-file-head">
          <span class="file-head-main">
            <strong>{{ file.path }}</strong>
          </span>
          <span class="file-actions">
            <small>{{ file.size }} bytes{{ file.truncated ? ' · 已截断' : '' }}</small>
          </span>
        </div>
        <div v-if="file" class="annotation-workbench" aria-label="源码批注">
          <div class="annotation-head">
            <span><MessageSquareText :size="16" />批注</span>
            <small v-if="annotationLoading">加载中...</small>
            <small v-else>{{ annotations.length }} 条</small>
          </div>
          <p v-if="annotationError" class="error annotation-error">{{ annotationError }}</p>
          <form
            v-if="annotationDraft.mode !== 'idle'"
            class="annotation-form"
            @submit.prevent="submitAnnotation"
          >
            <span class="annotation-target">{{ annotationDraft.line ? `L${annotationDraft.line}` : '文件批注' }}</span>
            <textarea
              v-model="annotationDraft.body"
              :disabled="annotationSaving"
              maxlength="4000"
              placeholder="写下这段源码的理解、问题或待验证点"
            />
            <span class="annotation-form-actions">
              <button type="button" class="ghost-action" @click="cancelAnnotationDraft">取消</button>
              <button type="submit" class="solid-action" :disabled="annotationSaving || !annotationDraft.body.trim()">
                {{ annotationDraft.mode === 'edit' ? '保存' : '添加' }}
              </button>
            </span>
          </form>
          <div v-if="sortedAnnotations.length" class="annotation-list">
            <article
              v-for="annotation in sortedAnnotations"
              :key="annotation.id"
              class="annotation-item"
              @click="annotation.line && jumpToLine(annotation.line)"
            >
              <strong>{{ annotationLineLabel(annotation) }}</strong>
              <p>{{ annotation.body }}</p>
              <span class="annotation-actions">
                <button type="button" @click.stop="editAnnotation(annotation)">编辑</button>
                <button type="button" @click.stop="emit('delete-annotation', annotation)">删除</button>
              </span>
            </article>
          </div>
          <p v-else-if="!annotationLoading" class="muted annotation-empty">还没有批注，可以从源码行旁添加。</p>
        </div>
        <div v-if="file" class="source-code" role="code-viewer">
          <div
            v-for="(lineHtml, i) in codeLines"
            :key="i"
            :ref="(el) => setLineElement(el, i + 1)"
            v-show="!isLineHidden(i)"
            :class="[
              'code-line',
              {
                annotated: annotatedLineSet.has(i + 1),
                highlighted: highlightedLine === i + 1,
                'fold-start': foldStartSet.has(i),
                folded: foldedLines.has(i),
              },
            ]"
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
            <button
              type="button"
              class="line-annotation-button"
              :aria-label="annotatedLineSet.has(i + 1) ? `查看或新增第 ${i + 1} 行批注` : `给第 ${i + 1} 行添加批注`"
              @click="startAnnotation(i + 1)"
            >
              <MessageSquareText v-if="annotatedLineSet.has(i + 1)" :size="13" />
              <MessageSquarePlus v-else :size="13" />
              <small v-if="annotationCountByLine.get(i + 1)">{{ annotationCountByLine.get(i + 1) }}</small>
            </button>
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
